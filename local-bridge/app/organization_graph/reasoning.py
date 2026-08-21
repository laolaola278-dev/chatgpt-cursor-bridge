"""Organization Graph reasoning engine (Phase 23).

Read-only traversal and analysis over the organization graph: ancestors,
descendants, owner lookup, impact analysis over non-hierarchical edges and
cycle detection. Missing nodes raise ResourceNotFound (404). Nothing here can
execute actions or modify source code.
"""

from __future__ import annotations

from typing import Any

from app.security.validator import ResourceNotFound

from .models import EdgeType, PARENT_TYPE_CHAIN
from .storage import OrganizationGraphStorage


class GraphReasoningEngine:
    def __init__(self, storage: OrganizationGraphStorage) -> None:
        self.storage = storage

    def get_node_or_404(self, node_id: str):
        node = self.storage.get_node(node_id)
        if node is None:
            raise ResourceNotFound(f"Graph node '{node_id}' was not found")
        return node

    def get_ancestors(self, node_id: str) -> list[dict[str, Any]]:
        """Nearest-first ancestor chain (parent, grandparent, ...)."""
        self.get_node_or_404(node_id)
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        current = self.storage.get_node(node_id)
        while current is not None and current.parent_id:
            if current.parent_id in seen:
                break
            seen.add(current.parent_id)
            parent = self.storage.get_node(current.parent_id)
            if parent is None:
                break
            output.append(parent.as_dict())
            current = parent
        return output

    def get_descendants(self, node_id: str) -> list[dict[str, Any]]:
        """All descendants (any depth) via parent_id, breadth-first."""
        self.get_node_or_404(node_id)
        output: list[dict[str, Any]] = []
        frontier = [node_id]
        seen: set[str] = set()
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            for child in self.storage.children(current):
                output.append(child.as_dict())
                frontier.append(child.id)
        return output

    def get_descendants_by_type(self, node_id: str, entity_type: str) -> list[dict[str, Any]]:
        entity_type = (entity_type or "").strip().upper()
        return [item for item in self.get_descendants(node_id) if str(item["type"]).upper() == entity_type]

    def find_owner(self, node_id: str) -> dict[str, Any]:
        """Nearest owning team; falls back to the company; None when unknown."""
        node = self.get_node_or_404(node_id)
        if node.type == "COMPANY":
            return {"node": node.id, "owner": node.as_dict(), "role": "company"}
        for ancestor in self.get_ancestors(node_id):
            if ancestor["type"] == "TEAM":
                return {"node": node.id, "owner": ancestor, "role": "team"}
        for ancestor in self.get_ancestors(node_id):
            if ancestor["type"] == "COMPANY":
                return {"node": node.id, "owner": ancestor, "role": "company"}
        return {"node": node.id, "owner": None, "role": "unknown"}

    def impact_analysis(self, node_id: str) -> dict[str, Any]:
        """Impacted nodes via non-hierarchical edges.

        Direction-aware traversal: IMPACTS / CAUSED_BY follow source->target,
        DEPENDS_ON follows target->source (a depends on b means changes to b
        affect a), RELATED_TO is undirected.
        """
        self.get_node_or_404(node_id)
        edges = self.storage.list_edges()
        adjacency: dict[str, set[str]] = {}
        for edge in edges:
            if edge.source == edge.target:
                continue
            relation = edge.relation
            if relation is EdgeType.IMPACTS:
                # source changes -> target affected
                adjacency.setdefault(edge.source, set()).add(edge.target)
            elif relation is EdgeType.CAUSED_BY:
                # source caused by target: changes to target affect source
                adjacency.setdefault(edge.target, set()).add(edge.source)
            elif relation is EdgeType.DEPENDS_ON:
                # source depends on target: changes to target affect source
                adjacency.setdefault(edge.target, set()).add(edge.source)
            else:  # RELATED_TO: undirected
                adjacency.setdefault(edge.source, set()).add(edge.target)
                adjacency.setdefault(edge.target, set()).add(edge.source)

        direct: set[str] = set(adjacency.get(node_id, set()))
        transitive: set[str] = set()
        frontier = list(direct)
        seen: set[str] = {node_id, *direct}
        while frontier:
            current = frontier.pop(0)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    transitive.add(neighbor)
                    frontier.append(neighbor)
        impacted = [
            self.storage.get_node(item).as_dict()
            for item in sorted(direct | transitive)
            if self.storage.get_node(item) is not None
        ]
        return {
            "node": node_id,
            "direct": [self.storage.get_node(item).as_dict() for item in sorted(direct) if self.storage.get_node(item)],
            "transitive": [self.storage.get_node(item).as_dict() for item in sorted(transitive) if self.storage.get_node(item)],
            "impacted": impacted,
            "edgeCount": len(edges),
            "readOnly": True,
        }

    def detect_cycles(self) -> list[list[str]]:
        """Detect directed cycles over non-hierarchical edges (Johnson-lite DFS)."""
        edges = self.storage.list_edges()
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            if edge.source != edge.target:
                adjacency.setdefault(edge.source, []).append(edge.target)
        cycles: list[list[str]] = []
        visited: set[str] = set()
        stack: list[str] = []
        on_stack: set[str] = set()
        seen_cycles: set[tuple[str, ...]] = set()

        def dfs(node: str) -> None:
            visited.add(node)
            stack.append(node)
            on_stack.add(node)
            for neighbor in adjacency.get(node, []):
                if neighbor in on_stack:
                    start = stack.index(neighbor)
                    cycle = stack[start:] + [neighbor]
                    key = tuple(cycle)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        cycles.append(cycle)
                elif neighbor not in visited:
                    dfs(neighbor)
            stack.pop()
            on_stack.discard(node)

        for node in sorted(adjacency):
            if node not in visited:
                dfs(node)
        return [cycle for cycle in cycles if len(cycle) > 2]


def expected_parent_type(entity_type: str) -> str | None:
    return PARENT_TYPE_CHAIN.get((entity_type or "").upper())
