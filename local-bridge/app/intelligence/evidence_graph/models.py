from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import ensure_project, ids, sanitize_metadata, sanitize_text, utc_now


class EvidenceRelation(str, Enum):
    OBSERVED_FROM = "OBSERVED_FROM"
    SIMILAR_TO = "SIMILAR_TO"
    CORRELATED_WITH = "CORRELATED_WITH"
    PREDICTS = "PREDICTS"
    SUPPORTS = "SUPPORTS"
    RECOMMENDS = "RECOMMENDS"
    DECIDED_BY = "DECIDED_BY"
    RESULTED_IN = "RESULTED_IN"
    LEARNED_FROM = "LEARNED_FROM"


@dataclass(frozen=True)
class EvidenceGraphNode:
    node_id: str
    node_type: str
    project_id: str
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "node_id", sanitize_text(self.node_id, limit=240))
        object.__setattr__(self, "node_type", sanitize_text(self.node_type, limit=80).upper())
        object.__setattr__(self, "label", sanitize_text(self.label, limit=500))
        object.__setattr__(self, "metadata", sanitize_metadata(self.metadata))

    def as_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "nodeId": self.node_id, "node_type": self.node_type, "nodeType": self.node_type, "project_id": self.project_id, "projectId": self.project_id, "label": self.label, "metadata": self.metadata, "readOnly": True}


@dataclass(frozen=True)
class EvidenceGraphEdge:
    edge_id: str
    project_id: str
    source_id: str
    target_id: str
    relation: EvidenceRelation | str
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "source_id", sanitize_text(self.source_id, limit=240))
        object.__setattr__(self, "target_id", sanitize_text(self.target_id, limit=240))
        value = self.relation.value if isinstance(self.relation, EvidenceRelation) else str(self.relation).upper()
        object.__setattr__(self, "relation", value)
        object.__setattr__(self, "evidence", ids(self.evidence))

    @property
    def relationship(self) -> str:
        return str(self.relation)

    def as_dict(self) -> dict[str, Any]:
        return {"edge_id": self.edge_id, "edgeId": self.edge_id, "project_id": self.project_id, "projectId": self.project_id, "source_id": self.source_id, "sourceId": self.source_id, "target_id": self.target_id, "targetId": self.target_id, "relation": self.relation, "relationship": self.relation, "evidence": self.evidence, "readOnly": True}


@dataclass(frozen=True)
class EvidenceGraph:
    project_id: str
    nodes: list[EvidenceGraphNode] = field(default_factory=list)
    edges: list[EvidenceGraphEdge] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "projectId": self.project_id, "nodes": [item.as_dict() for item in self.nodes], "edges": [item.as_dict() for item in self.edges], "nodeCount": len(self.nodes), "edgeCount": len(self.edges), "created_at": self.created_at, "createdAt": self.created_at, "readOnly": True}
