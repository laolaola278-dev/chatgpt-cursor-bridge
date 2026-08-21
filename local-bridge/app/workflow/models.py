"""Workflow domain models.

A workflow is a human-in-the-loop pipeline. Each stage produces a report and
must be explicitly approved before the workflow can advance. Actions live
inside a stage and still flow through the existing approval system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StageType(str, Enum):
    REQUIREMENT = "REQUIREMENT"
    ANALYSIS = "ANALYSIS"
    ARCHITECTURE = "ARCHITECTURE"
    IMPLEMENTATION = "IMPLEMENTATION"
    TESTING = "TESTING"
    DEBUG = "DEBUG"
    DELIVERY = "DELIVERY"


#: Canonical order of the workflow pipeline.
STAGE_ORDER: tuple[StageType, ...] = (
    StageType.REQUIREMENT,
    StageType.ANALYSIS,
    StageType.ARCHITECTURE,
    StageType.IMPLEMENTATION,
    StageType.TESTING,
    StageType.DEBUG,
    StageType.DELIVERY,
)


class StageStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    REPORTED = "REPORTED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


class WorkflowStatus(str, Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    DESIGNING = "DESIGNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: Which workflow status naturally accompanies which stage while it is active.
STAGE_TO_STATUS: dict[StageType, WorkflowStatus] = {
    StageType.REQUIREMENT: WorkflowStatus.CREATED,
    StageType.ANALYSIS: WorkflowStatus.ANALYZING,
    StageType.ARCHITECTURE: WorkflowStatus.DESIGNING,
    StageType.IMPLEMENTATION: WorkflowStatus.IMPLEMENTING,
    StageType.TESTING: WorkflowStatus.TESTING,
    StageType.DEBUG: WorkflowStatus.TESTING,
    # DELIVERY stays in TESTING while running; approval transitions to COMPLETED.
    StageType.DELIVERY: WorkflowStatus.TESTING,
}

#: Terminal states from which no further transition is legal.
TERMINAL_STATUSES: frozenset[WorkflowStatus] = frozenset(
    {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class WorkflowStage:
    id: str
    workflow_id: str
    stage_type: StageType
    status: StageStatus
    created_at: str
    updated_at: str
    report: str | None = None
    report_title: str | None = None
    approval_request_id: str | None = None
    approved_at: str | None = None
    approved_by: str | None = None
    action_ids: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)
    quality_gate: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflowId": self.workflow_id,
            "stageType": self.stage_type.value,
            "status": self.status.value,
            "reportTitle": self.report_title,
            "report": self.report,
            "approvalRequestId": self.approval_request_id,
            "approvedAt": self.approved_at,
            "approvedBy": self.approved_by,
            "actionIds": list(self.action_ids),
            "agentIds": list(self.agent_ids),
            "qualityGate": self.quality_gate,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass
class Workflow:
    id: str
    project: str
    name: str
    description: str
    current_stage: StageType
    status: WorkflowStatus
    created_at: str
    updated_at: str
    stages: list[WorkflowStage] = field(default_factory=list)
    cancelled_reason: str | None = None
    completed_at: str | None = None

    def find_stage(self, stage_id: str) -> WorkflowStage | None:
        return next((stage for stage in self.stages if stage.id == stage_id), None)

    def latest_stage(self, stage_type: StageType) -> WorkflowStage | None:
        for stage in reversed(self.stages):
            if stage.stage_type is stage_type:
                return stage
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "name": self.name,
            "description": self.description,
            "currentStage": self.current_stage.value,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "completedAt": self.completed_at,
            "cancelledReason": self.cancelled_reason,
            "stages": [stage.as_dict() for stage in self.stages],
        }


@dataclass(frozen=True)
class WorkflowSummary:
    id: str
    project: str
    name: str
    status: WorkflowStatus
    current_stage: StageType
    stage_count: int
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "name": self.name,
            "status": self.status.value,
            "currentStage": self.current_stage.value,
            "stageCount": self.stage_count,
            "updatedAt": self.updated_at,
        }
