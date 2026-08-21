from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionTaskStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class ExecutionProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class ExecutionTask:
    id: str
    workflow_id: str | None
    plan_id: str | None
    project: str
    title: str
    task_type: str
    files: list[str]
    dependencies: list[str]
    risk: str
    risk_score: int
    status: ExecutionTaskStatus = ExecutionTaskStatus.PROPOSED
    created_at: str = ""
    updated_at: str = ""
    verification: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflowId": self.workflow_id,
            "planId": self.plan_id,
            "project": self.project,
            "title": self.title,
            "type": self.task_type,
            "files": self.files,
            "dependencies": self.dependencies,
            "risk": self.risk,
            "riskScore": self.risk_score,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "verification": self.verification,
            "readOnly": True,
        }


@dataclass(frozen=True)
class ExecutionOperation:
    operation_type: str
    path: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.operation_type, "path": self.path, "reason": self.reason}


@dataclass
class ExecutionProposal:
    id: str
    task_id: str
    project: str
    workflow_id: str | None
    operations: list[ExecutionOperation]
    estimated_changes: int
    risk_score: int
    status: ExecutionProposalStatus = ExecutionProposalStatus.PROPOSED
    approval_id: str | None = None
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "taskId": self.task_id,
            "project": self.project,
            "workflowId": self.workflow_id,
            "operations": [operation.as_dict() for operation in self.operations],
            "estimatedChanges": self.estimated_changes,
            "riskScore": self.risk_score,
            "status": self.status.value,
            "approvalId": self.approval_id,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class ExecutionResult:
    id: str
    proposal_id: str
    task_id: str
    project: str
    files_changed: list[str]
    diff_summary: dict[str, Any]
    duration_ms: int
    errors: list[str]
    verification: dict[str, Any]
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "proposalId": self.proposal_id,
            "taskId": self.task_id,
            "project": self.project,
            "filesChanged": self.files_changed,
            "diffSummary": self.diff_summary,
            "durationMs": self.duration_ms,
            "errors": self.errors,
            "verification": self.verification,
            "createdAt": self.created_at,
            "readOnly": True,
        }
