"""Organization Risk Propagation Engine (Phase 24).

Given a risk signal on one graph node (severity + likelihood), walks the
organization graph along hierarchy and non-hierarchical edges and reports how
the risk propagates to other projects, teams and services, with a decayed
severity per hop. Analysis only: it never blocks execution and never writes
to the graph, projects or memory.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from app.organization_graph.storage import OrganizationGraphStorage
from app.security.validator import ResourceNotFound, ValidationFailed

from .models import OrganizationRiskReport

_SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}
_LIKELIHOOD_ORDER = {"low": 1, "medium": 2, "high": 3}
_DECAY = 0.8
_HOP_THRESHOLD = 2.0  # severity score below this is ignored


def _validate_level(value: str, field: str) -> str:
    cleaned = (value or "low").strip().lower()
    if cleaned not in _SEVERITY_ORDER:
        raise ValidationFailed(f"Invalid {field}; expected low|medium|high")
    return cleaned


class OrganizationRiskEngine:
    def __init__(self, graph: OrganizationGraphStorage) -> None:
        self.graph = graph

    def propagate(
        self,
        source: str,
        *,
        severity: str = "medium",
        likelihood: str = "medium",
    ) -> OrganizationRiskReport:
        node = self.graph.get_node(source)
        if node is None:
            raise ResourceNotFound(f"Graph node '{source}' was not found")
        severity = _validate_level(severity, "severity")
        likelihood = _validate_level(likelihood, "likelihood")

        nodes = {item.id: item for item in self.graph.list_nodes()}
        edges = self.graph.list_edges()
        # Propagation is a blast-radius walk: a risk at a shared service or
        # repository reaches both its dependents and its dependencies, so every
        # edge is traversable in both directions with per-hop severity decay.
        adjacency: dict[str, list[tuple[str, str]]] = {}
        for edge in edges:
            if edge.source == edge.target:
                continue
            adjacency.setdefault(edge.source, []).append((edge.target, edge.relation.value))
            adjacency.setdefault(edge.target, []).append((edge.source, edge.relation.value))

        seed = float(_SEVERITY_ORDER[severity])
        visited: dict[str, float] = {source: seed}
        queue: deque[tuple[str, float, list[str]]] = deque([(source, seed, [source])])
        propagation: list[dict[str, Any]] = []
        while queue:
            current, score, path = queue.popleft()
            for neighbor, relation in adjacency.get(current, []):
                propagated = score * _DECAY
                if propagated < _HOP_THRESHOLD:
                    continue
                if propagated > visited.get(neighbor, 0.0):
                    visited[neighbor] = propagated
                    new_path = path + [neighbor]
                    propagation.append(
                        {
                            "node": neighbor,
                            "via": relation,
                            "severity": self._level_for(propagated),
                            "path": [nodes[item].name for item in new_path if item in nodes],
                        }
                    )
                    queue.append((neighbor, propagated, new_path))

        affected_nodes = [
            {
                "id": node_id,
                "name": nodes[node_id].name,
                "type": nodes[node_id].type,
                "severity": self._level_for(score),
            }
            for node_id, score in sorted(visited.items(), key=lambda item: item[1], reverse=True)
            if node_id != source and node_id in nodes
        ]

        projects = sorted({self._ancestor_of_type(item["id"], "PROJECT", nodes) for item in affected_nodes} - {""})
        teams = sorted({self._ancestor_of_type(item["id"], "TEAM", nodes) for item in affected_nodes} - {""})
        services = sorted({item["name"] for item in affected_nodes if item["type"] == "SERVICE"})

        worst = max((item["severity"] for item in affected_nodes), default="low", key=lambda value: _SEVERITY_ORDER[value])
        impact = "high" if worst == "high" or len(projects) >= 3 else "medium" if worst == "medium" or projects else "low"
        confidence = min(0.95, 0.4 + 0.08 * len(affected_nodes) + 0.1 * (1 if len(projects) else 0))

        recommendations: list[str] = []
        if impact == "high":
            recommendations.append("Gate cross-project changes touching the affected services until the risk is reviewed")
        if projects:
            recommendations.append(f"Notify owners of affected project(s): {', '.join(projects[:3])}")
        if worst == "high" or severity == "high":
            recommendations.append("Require human approval for any change in the propagation path")
        if not affected_nodes:
            recommendations.append("Risk is contained to the source node; no propagation observed")

        return OrganizationRiskReport(
            source=source,
            severity=severity,
            likelihood=likelihood,
            propagation_path=propagation,
            affected_nodes=affected_nodes,
            affected_projects=projects,
            affected_teams=teams,
            affected_services=services,
            impact=impact,
            confidence=confidence,
            recommendations=recommendations,
        )

    @staticmethod
    def _level_for(score: float) -> str:
        if score >= 2.5:
            return "high"
        if score >= 1.8:
            return "medium"
        return "low"

    def _ancestor_of_type(self, node_id: str, entity_type: str, nodes: dict[str, Any]) -> str:
        current = nodes.get(node_id)
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.type == entity_type:
                return current.name
            current = nodes.get(current.parent_id) if current.parent_id else None
        return ""
