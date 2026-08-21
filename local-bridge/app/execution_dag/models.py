from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DagStatus(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DependencyType(str, Enum):
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    REQUIRES_REVIEW = "requires_review"


@dataclass(frozen=True)
class DagEdge:
    source_loop: str
    target_loop: str
    dependency_type: DependencyType = DependencyType.DEPENDS_ON

    def as_dict(self) -> dict[str, Any]:
        return {"sourceLoop": self.source_loop, "targetLoop": self.target_loop, "dependencyType": self.dependency_type.value}


@dataclass
class ExecutionDag:
    id: str
    project: str
    loop_ids: list[str]
    edges: list[DagEdge] = field(default_factory=list)
    status: DagStatus = DagStatus.CREATED
    created_at: str = ""
    updated_at: str = ""
    history: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "loopIds": self.loop_ids,
            "edges": [edge.as_dict() for edge in self.edges],
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "history": self.history,
            "readOnly": True,
        }
