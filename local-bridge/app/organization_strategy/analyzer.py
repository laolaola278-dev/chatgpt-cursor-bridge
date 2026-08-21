"""Cross-Project Impact Analysis (Phase 24).

Walks the organization graph (Phase 23 storage: hierarchy via parent_id plus
non-hierarchical edges) from a source node and derives which projects, teams
and services are affected, the dependency paths between them and an
impact/risk summary. Pure read-only analysis: it never modifies the graph,
any project or memory.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from app.organization_graph.models import EdgeType
from app.organization_graph.storage import OrganizationGraphStorage
from app.security.validator import ResourceNotFound

from .models import OrganizationImpactReport


class OrganizationImpactAnalyzer:
    def __init__(self, graph: OrganizationGraphStorage) -> None:
        self.graph = graph

    def analyze(self, source_node: str) -> OrganizationImpactReport:
        node = self.graph.get_node(source_node)
        if node is None:
            raise ResourceNotFound(f"Graph node '{source_node}' was not found")

        nodes = {item.id: item for item in self.graph.list_nodes()}
        edges = self.graph.list_edges()

        # Organization-level impact is a blast-radius analysis: every edge is
        # traversable in both directions (a change at a shared repository can
        # affect both dependents and dependencies). The Phase 23 graph impact
        # engine keeps its direction-aware semantics untouched.
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            if edge.source == edge.target:
                continue
            adjacency.setdefault(edge.source, set()).add(edge.target)
            adjacency.setdefault(edge.target, set()).add(edge.source)

        # Direct + transitive affected node ids.
        direct = set(adjacency.get(source_node, set()))
        transitive: set[str] = set()
        frontier = deque(direct)
        seen: set[str] = {source_node, *direct}
        while frontier:
            current = frontier.popleft()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    transitive.add(neighbor)
                    frontier.append(neighbor)

        affected_ids = direct | transitive
        affected = [nodes[item] for item in affected_ids if item in nodes]

        projects = sorted({self._ancestor_of_type(item, "PROJECT", nodes) for item in affected_ids} - {""})
        teams = sorted({self._ancestor_of_type(item, "TEAM", nodes) for item in affected_ids} - {""})
        services = sorted({item.name for item in affected if item.type == "SERVICE"})

        dependency_paths = self._dependency_paths(source_node, affected_ids, nodes)

        # Incident risk: INCIDENT nodes hanging off affected projects.
        incident_count = sum(
            1 for item in affected if item.type == "INCIDENT" or item.type == "ARCHITECTURE_DECISION"
        )
        blocking: list[str] = []
        if incident_count >= 2:
            blocking.append("multiple_affected_nodes_with_incidents")
        if len(projects) >= 3:
            blocking.append("cross_project_blast_radius")

        # Deterministic score from real topology.
        impact_score = min(
            100,
            len(affected) * 8 + len(projects) * 12 + len(services) * 6 + len(dependency_paths) * 5,
        )
        risk_level = "high" if impact_score >= 70 else "medium" if impact_score >= 35 else "low"
        confidence = min(0.95, 0.35 + 0.1 * len(affected) + 0.08 * len(dependency_paths))

        return OrganizationImpactReport(
            source_node=source_node,
            affected_projects=projects,
            affected_teams=teams,
            affected_services=services,
            dependency_paths=dependency_paths,
            risk_level=risk_level,
            impact_score=impact_score,
            confidence=confidence,
            blocking_issues=blocking,
        )

    def _ancestor_of_type(self, node_id: str, entity_type: str, nodes: dict[str, Any]) -> str:
        current = nodes.get(node_id)
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.type == entity_type:
                return current.name
            current = nodes.get(current.parent_id) if current.parent_id else None
        return ""

    def _dependency_paths(
        self, source: str, affected: set[str], nodes: dict[str, Any]
    ) -> list[list[str]]:
        """Shortest paths from source to each affected node over DEPENDS_ON
        edges (traversed in both directions: shared dependencies expose both
        dependents and dependencies)."""
        depends: dict[str, list[str]] = {}
        for edge in self.graph.list_edges():
            if edge.relation is EdgeType.DEPENDS_ON:
                depends.setdefault(edge.source, []).append(edge.target)
                depends.setdefault(edge.target, []).append(edge.source)
        paths: list[list[str]] = []
        for target in sorted(affected):
            path = self._shortest_path(source, target, depends)
            if path:
                paths.append([nodes[item].name for item in path])
        return paths

    @staticmethod
    def _shortest_path(source: str, target: str, adjacency: dict[str, list[str]]) -> list[str]:
        if source == target:
            return []
        queue: deque[tuple[str, list[str]]] = deque([(source, [source])])
        seen = {source}
        while queue:
            current, path = queue.popleft()
            for neighbor in adjacency.get(current, []):
                if neighbor == target:
                    return path + [neighbor]
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return []
