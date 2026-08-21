"""Organization Context Injection (Phase 23).

Builds a stable, read-only context bundle for a graph node so AI agents can
reason about ownership, hierarchy, related architecture and incidents without
touching the graph itself. The output shape is stable: node / owner /
hierarchy / related_architecture / incidents / ancestorChain / readOnly.
"""

from __future__ import annotations

from typing import Any

from .reasoning import GraphReasoningEngine
from .storage import OrganizationGraphStorage


class OrganizationContextBuilder:
    def __init__(self, storage: OrganizationGraphStorage) -> None:
        self.storage = storage
        self.reasoning = GraphReasoningEngine(storage)

    def build_context(self, node_id: str) -> dict[str, Any]:
        node = self.reasoning.get_node_or_404(node_id)
        ancestors = self.reasoning.get_ancestors(node_id)
        owner = self.reasoning.find_owner(node_id)["owner"]

        hierarchy = [item for item in ancestors] + [node.as_dict()]
        ancestor_chain = [item["name"] for item in reversed(ancestors)] + [node.name]

        related = self._related_architecture(node_id)
        incidents = self.reasoning.get_descendants_by_type(node_id, "INCIDENT")
        if node.type == "INCIDENT":
            incidents = [node.as_dict()] + incidents

        return {
            "node": node.as_dict(),
            "owner": owner,
            "hierarchy": hierarchy,
            "related_architecture": related,
            "incidents": incidents,
            "ancestorChain": ancestor_chain,
            "readOnly": True,
        }

    def build_strategy_context(self, node_id: str, **strategy_signals: Any) -> dict[str, Any]:
        """Phase 24 extension: node context plus organization-strategy signals.

        The base build_context() shape is preserved and enriched with optional
        strategy-layer signals (organization_health, active_risks,
        cross_project_impacts, active_strategies, pending_decisions,
        technical_debt, architecture_drift, recommendations). Missing signals
        default to empty values; readOnly stays True. Never writes anything.
        """
        context = self.build_context(node_id)
        context["organization_health"] = strategy_signals.get("organization_health") or []
        context["active_risks"] = strategy_signals.get("active_risks") or []
        context["cross_project_impacts"] = strategy_signals.get("cross_project_impacts") or []
        context["active_strategies"] = strategy_signals.get("active_strategies") or []
        context["pending_decisions"] = strategy_signals.get("pending_decisions") or []
        context["technical_debt"] = strategy_signals.get("technical_debt") or {}
        context["architecture_drift"] = strategy_signals.get("architecture_drift") or {}
        context["recommendations"] = strategy_signals.get("recommendations") or []
        context["readOnly"] = True
        return context

    def _related_architecture(self, node_id: str) -> list[dict[str, Any]]:
        """Architecture-related nodes reachable through graph edges."""
        edges = self.storage.list_edges()
        neighbors: set[str] = set()
        related_edges: list[dict[str, Any]] = []
        for edge in edges:
            if edge.source == node_id:
                neighbors.add(edge.target)
                related_edges.append(edge.as_dict())
            elif edge.target == node_id:
                neighbors.add(edge.source)
                related_edges.append(edge.as_dict())
        nodes = [
            node.as_dict()
            for node_id_item in sorted(neighbors)
            if (node := self.storage.get_node(node_id_item)) is not None
        ]
        return {"nodes": nodes, "edges": related_edges, "count": len(nodes)}
