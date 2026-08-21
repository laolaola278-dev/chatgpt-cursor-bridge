"""Session domain objects for the persistent agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SessionStatus(str, Enum):
    CREATE = "CREATE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


@dataclass
class Session:
    id: str
    project: str
    status: SessionStatus
    created_at: str
    updated_at: str
    workflow_id: str | None = None
    stage_id: str | None = None
    approval_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "workflowId": self.workflow_id,
            "stageId": self.stage_id,
            "approvalId": self.approval_id,
            "history": list(self.history),
        }

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
