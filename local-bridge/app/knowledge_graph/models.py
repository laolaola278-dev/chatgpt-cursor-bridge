from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    node_type: str
    label: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.node_id, "type": self.node_type, "label": self.label, "metadata": self.metadata}


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "relation": self.relation}
