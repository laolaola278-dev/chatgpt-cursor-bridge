"""Domain models for isolated Phase 9 agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    PLANNER = "PLANNER"
    ARCHITECT = "ARCHITECT"
    CODER = "CODER"
    TESTER = "TESTER"
    REVIEWER = "REVIEWER"


class AgentStatus(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


ROLE_PERMISSIONS: dict[AgentRole, frozenset[str]] = {
    AgentRole.PLANNER: frozenset({"context_read", "model_route", "workflow_propose"}),
    AgentRole.ARCHITECT: frozenset({"context_read", "model_route", "workflow_propose"}),
    AgentRole.CODER: frozenset({"context_read", "model_route", "change_propose", "test_propose"}),
    AgentRole.TESTER: frozenset({"context_read", "model_route", "test_propose", "test_read"}),
    AgentRole.REVIEWER: frozenset({"context_read", "model_route", "review", "risk_assessment"}),
}


@dataclass
class Agent:
    id: str
    project: str
    session_id: str
    role: AgentRole
    model_id: str
    memory_scope: str
    permissions: list[str]
    status: AgentStatus
    created_at: str
    updated_at: str
    workflow_id: str | None = None
    stage_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "sessionId": self.session_id,
            "role": self.role.value,
            "modelId": self.model_id,
            "memoryScope": self.memory_scope,
            "permissions": list(self.permissions),
            "status": self.status.value,
            "workflowId": self.workflow_id,
            "stageId": self.stage_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "history": list(self.history),
        }

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
