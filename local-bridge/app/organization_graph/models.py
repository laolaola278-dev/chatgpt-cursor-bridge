"""Organization Graph models (Phase 23).

Adds a reasoning layer on top of the organization graph: non-hierarchical
edges (RELATED_TO / IMPACTS / CAUSED_BY / DEPENDS_ON), a strict parent-type
chain for hierarchy, and versioned snapshots. All analysis is read-only; every
user-visible write flows through the ApprovalStore.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Strict hierarchy: child type -> parent type. Used by reasoning (find_owner,
# hierarchy) and kept compatible with pre-existing entities (the chain is not
# enforced retroactively; parent_id remains the source of truth).
PARENT_TYPE_CHAIN: dict[str, str] = {
    "TEAM": "COMPANY",
    "PROJECT": "TEAM",
    "SERVICE": "PROJECT",
    "REPOSITORY": "PROJECT",
    "ARCHITECTURE_DECISION": "PROJECT",
    "INCIDENT": "PROJECT",
}


class EdgeType(str, Enum):
    """Non-hierarchical edge relations between graph nodes.

    Phase 23 defines the four engineering relations; Phase 24 adds the
    organization-strategy relations (INFLUENCES / AFFECTS / RECOMMENDS /
    EVALUATED_BY / IMPLEMENTED_BY / SUPERSEDES). Values are additive so
    pre-existing databases keep reading. Hierarchy stays expressed only
    through parent_id - no relation is ever hierarchical.
    """

    RELATED_TO = "RELATED_TO"
    IMPACTS = "IMPACTS"
    CAUSED_BY = "CAUSED_BY"
    DEPENDS_ON = "DEPENDS_ON"
    INFLUENCES = "INFLUENCES"
    AFFECTS = "AFFECTS"
    RECOMMENDS = "RECOMMENDS"
    EVALUATED_BY = "EVALUATED_BY"
    IMPLEMENTED_BY = "IMPLEMENTED_BY"
    SUPERSEDES = "SUPERSEDES"


@dataclass
class GraphNode:
    id: str
    type: str
    name: str
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    @classmethod
    def from_entity(cls, entity: dict[str, Any]) -> "GraphNode":
        """Import a Phase 22 OrgEntity payload (camelCase) into a graph node."""
        parent_id = entity.get("parentId") or entity.get("parent_id")
        metadata = entity.get("metadata") or {}
        return cls(
            id=str(entity.get("id", "")),
            type=str(entity.get("type", "")).upper(),
            name=str(entity.get("name", "")),
            parent_id=str(parent_id) if parent_id else None,
            metadata=metadata,
            created_at=str(entity.get("createdAt") or entity.get("created_at") or _now()),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "parentId": self.parent_id,
            "metadata": self.metadata,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrgEdge:
    source: str
    target: str
    relation: EdgeType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    @property
    def is_hierarchy(self) -> bool:
        """Hierarchy is expressed through parent_id; edge relations are never hierarchical."""
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "isHierarchy": self.is_hierarchy,
            "metadata": self.metadata,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class GraphSnapshot:
    id: str
    checksum: str
    node_count: int
    edge_count: int
    graph_json: str
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "checksum": self.checksum,
            "nodeCount": self.node_count,
            "edgeCount": self.edge_count,
            "graphSize": len(self.graph_json),
            "createdAt": self.created_at,
            "readOnly": True,
        }


def canonical_graph_json(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Deterministic JSON serialization used for snapshot checksums.

    Nodes are ordered by id and edges by (source, target, relation) so that
    semantically identical graphs always produce the same checksum regardless
    of insertion order.
    """
    ordered_nodes = sorted(nodes, key=lambda n: str(n.get("id", "")))
    ordered_edges = sorted(
        edges,
        key=lambda e: (str(e.get("source", "")), str(e.get("target", "")), str(e.get("relation", ""))),
    )
    graph = {"nodes": ordered_nodes, "edges": ordered_edges}
    return json.dumps(graph, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def checksum_of(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
