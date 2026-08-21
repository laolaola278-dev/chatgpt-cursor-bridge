"""Task queue models."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class Task:
    id: str
    workflow_id: str
    stage_id: str
    agent_id: str
    priority: int
    status: TaskStatus
    context: dict[str, Any]
    created_at: str
    updated_at: str

    @classmethod
    def create(cls, *, workflow_id: str, stage_id: str, agent_id: str, priority: int, context: dict[str, Any]) -> "Task":
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        return cls(f"task_{secrets.token_hex(8)}", workflow_id, stage_id, agent_id, priority, TaskStatus.PENDING, dict(context), now, now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflowId": self.workflow_id,
            "stageId": self.stage_id,
            "agentId": self.agent_id,
            "priority": self.priority,
            "status": self.status.value,
            "context": self.context,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
