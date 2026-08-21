"""Runtime lifecycle contracts."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RuntimeState(str, Enum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_FEEDBACK = "WAITING_FEEDBACK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"


@dataclass
class AgentRuntime:
    id: str
    agent_id: str
    session_id: str
    workflow_id: str
    stage_id: str
    state: RuntimeState
    created_at: str
    updated_at: str
    history: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def create(cls, *, agent_id: str, session_id: str, workflow_id: str, stage_id: str) -> "AgentRuntime":
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        return cls(f"rt_{secrets.token_hex(8)}", agent_id, session_id, workflow_id, stage_id, RuntimeState.CREATED, now, now, [{"from": "", "to": RuntimeState.CREATED.value, "at": now}])

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "agentId": self.agent_id, "sessionId": self.session_id, "workflowId": self.workflow_id, "stageId": self.stage_id, "state": self.state.value, "createdAt": self.created_at, "updatedAt": self.updated_at, "history": self.history}


@dataclass(frozen=True)
class ExecutionProposal:
    proposal_id: str
    task_id: str
    runtime_id: str
    agent_id: str
    workflow_id: str
    stage_id: str
    action: str
    risk: str
    reason: str
    requires_approval: bool = True

    @classmethod
    def for_task(cls, task: Any, runtime_id: str) -> "ExecutionProposal":
        return cls(f"proposal_{secrets.token_hex(8)}", task.id, runtime_id, task.agent_id, task.workflow_id, task.stage_id, str(task.context.get("action", "agent.task")), str(task.context.get("risk", "medium")), "Scheduler generated proposal; explicit approval is still required")

    def as_dict(self) -> dict[str, Any]:
        return {"proposalId": self.proposal_id, "taskId": self.task_id, "runtimeId": self.runtime_id, "agentId": self.agent_id, "workflowId": self.workflow_id, "stageId": self.stage_id, "action": self.action, "risk": self.risk, "reason": self.reason, "requiresApproval": self.requires_approval}
