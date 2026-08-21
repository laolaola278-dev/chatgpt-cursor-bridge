"""Data contracts for multi-agent collaboration.

These records contain coordination metadata only. They never contain shell
commands, tool grants, or implicit approval decisions.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentTeamStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class AgentTeam:
    id: str
    workflow_id: str
    members: list[str]
    leader: str
    status: AgentTeamStatus
    created_at: str
    updated_at: str
    history: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def create(cls, *, workflow_id: str, members: list[str], leader: str) -> "AgentTeam":
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        return cls(
            id=f"team_{secrets.token_hex(8)}", workflow_id=workflow_id,
            members=list(dict.fromkeys(members)), leader=leader,
            status=AgentTeamStatus.CREATED, created_at=now, updated_at=now,
            history=[{"from": "", "to": AgentTeamStatus.CREATED.value, "at": now}],
        )

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "workflowId": self.workflow_id, "members": list(self.members), "leader": self.leader, "status": self.status.value, "createdAt": self.created_at, "updatedAt": self.updated_at, "history": list(self.history)}


class CollaborationMessageType(str, Enum):
    DISCUSS = "DISCUSS"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    REQUEST_CONTEXT = "REQUEST_CONTEXT"
    SUGGEST_FIX = "SUGGEST_FIX"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class CollaborationMessage:
    message_id: str
    message_type: CollaborationMessageType
    sender: str
    receiver: str
    task_id: str
    workflow_id: str
    context: str
    timestamp: str

    @classmethod
    def create(cls, *, message_type: CollaborationMessageType | str, sender: str, receiver: str, task_id: str, workflow_id: str, context: str) -> "CollaborationMessage":
        clean = (context or "").strip()
        if not sender or not receiver or sender == receiver:
            raise ValueError("Collaboration message endpoints must be distinct")
        if not task_id or not workflow_id or not clean or len(clean) > 4000:
            raise ValueError("Collaboration message requires bounded task, workflow and context")
        return cls(f"cmsg_{secrets.token_hex(8)}", CollaborationMessageType(message_type), sender, receiver, task_id, workflow_id, clean, datetime.now(timezone.utc).isoformat(timespec="milliseconds"))

    def as_dict(self) -> dict[str, Any]:
        return {"messageId": self.message_id, "type": self.message_type.value, "sender": self.sender, "receiver": self.receiver, "taskId": self.task_id, "workflowId": self.workflow_id, "context": self.context, "timestamp": self.timestamp}


@dataclass
class ConflictRecord:
    id: str
    workflow_id: str
    task_id: str
    agents: list[str]
    issue: str
    options: list[str]
    resolution: str | None
    status: str
    created_at: str
    resolved_at: str | None = None

    @classmethod
    def create(cls, *, workflow_id: str, task_id: str, agents: list[str], issue: str, options: list[str]) -> "ConflictRecord":
        if len(agents) < 2 or not issue.strip() or len(options) < 2:
            raise ValueError("A conflict needs two agents, an issue and at least two options")
        return cls(f"conf_{secrets.token_hex(8)}", workflow_id, task_id, list(dict.fromkeys(agents)), issue.strip(), list(options), None, "OPEN", datetime.now(timezone.utc).isoformat(timespec="milliseconds"))

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "workflowId": self.workflow_id, "taskId": self.task_id, "agents": list(self.agents), "issue": self.issue, "options": list(self.options), "resolution": self.resolution, "status": self.status, "createdAt": self.created_at, "resolvedAt": self.resolved_at}
