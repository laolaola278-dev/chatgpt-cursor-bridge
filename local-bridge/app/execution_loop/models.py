from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoopStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    PROPOSAL_READY = "PROPOSAL_READY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RECOVERED = "RECOVERED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


@dataclass
class ExecutionLoop:
    id: str
    project: str
    plan_id: str
    workflow_id: str | None
    task_ids: list[str]
    proposal_id: str | None = None
    result_id: str | None = None
    approval_id: str | None = None
    status: LoopStatus = LoopStatus.CREATED
    verification: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    rollback: dict[str, Any] = field(default_factory=dict)
    memory_proposal_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    history: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "planId": self.plan_id,
            "workflowId": self.workflow_id,
            "taskIds": self.task_ids,
            "proposalId": self.proposal_id,
            "resultId": self.result_id,
            "approvalId": self.approval_id,
            "status": self.status.value,
            "verification": self.verification,
            "quality": self.quality,
            "rollback": self.rollback,
            "memoryProposalId": self.memory_proposal_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "history": self.history,
            "readOnly": True,
        }
