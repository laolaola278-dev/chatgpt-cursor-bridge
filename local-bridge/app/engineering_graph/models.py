from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class GraphNode:
    id: str
    type: str
    project: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "project": self.project, "label": self.label, "metadata": self.metadata, "createdAt": self.created_at}


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    project: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "relation": self.relation, "project": self.project, "metadata": self.metadata, "createdAt": self.created_at}


@dataclass
class EngineeringGraph:
    project: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    generated_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {"project": self.project, "nodes": [node.as_dict() for node in self.nodes], "edges": [edge.as_dict() for edge in self.edges], "generatedAt": self.generated_at, "readOnly": True}
