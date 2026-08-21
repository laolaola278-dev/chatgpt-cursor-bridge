"""Workflow lifecycle orchestration.

The manager owns state transitions but never executes actions on its own:
mutating operations must still go through the existing ApprovalStore, so the
approval system remains the single execution entry point.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from app.audit.logger import AuditLogger
from app.config import Settings
from app.security.permissions import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStore,
    PermissionLevel,
)
from app.security.sandbox import validate_project_name
from app.security.validator import ApprovalError, ResourceNotFound, ValidationFailed

from .models import (
    STAGE_ORDER,
    STAGE_TO_STATUS,
    StageStatus,
    StageType,
    TERMINAL_STATUSES,
    Workflow,
    WorkflowStage,
    WorkflowStatus,
    WorkflowSummary,
    utc_now,
)
from .stages import (
    WorkflowTransitionError,
    assert_stage_transition,
    assert_workflow_transition,
    next_stage,
    validate_stage_report,
)
from .storage import WorkflowStorage


_ID_PATTERN = re.compile(r"^wf_[0-9a-f]{12,32}$")
_STAGE_ID_PATTERN = re.compile(r"^stg_[0-9a-f]{12,32}$")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _ensure_id(value: str, pattern: re.Pattern[str], label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned or not pattern.match(cleaned):
        raise ValidationFailed(f"Invalid {label}: {value!r}")
    return cleaned


class WorkflowManager:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: WorkflowStorage,
        approvals: ApprovalStore,
        audit: AuditLogger,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._approvals = approvals
        self._audit = audit

    @property
    def storage(self) -> WorkflowStorage:
        """Read-only access for context and dashboard aggregation."""
        return self._storage

    # -- audit helper ---------------------------------------------------

    def _log(
        self,
        *,
        action: str,
        workflow: Workflow | None,
        stage: WorkflowStage | None,
        result: str,
        detail: str,
        request_id: str | None = None,
    ) -> None:
        path = "workflow"
        if workflow is not None:
            path = f"{workflow.project}:workflow/{workflow.id}"
        if stage is not None:
            path = f"{path}#{stage.stage_type.value}"
        self._audit.record(
            action=action,
            path=path,
            permission=PermissionLevel.LEVEL_1.value,
            approved=result == "success",
            result=result,
            detail=detail,
            request_id=request_id,
        )

    # -- lookups --------------------------------------------------------

    def list(self) -> list[WorkflowSummary]:
        summaries = [
            WorkflowSummary(
                id=workflow.id,
                project=workflow.project,
                name=workflow.name,
                status=workflow.status,
                current_stage=workflow.current_stage,
                stage_count=len(workflow.stages),
                updated_at=workflow.updated_at,
            )
            for workflow in self._storage.all()
        ]
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    def get(self, workflow_id: str) -> Workflow:
        workflow_id = _ensure_id(workflow_id, _ID_PATTERN, "workflow id")
        return self._storage.load(workflow_id)

    # -- creation -------------------------------------------------------

    def create(self, *, project: str, name: str, description: str) -> Workflow:
        project = validate_project_name(project)
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValidationFailed("Workflow name must not be empty")
        if len(clean_name) > 200:
            raise ValidationFailed("Workflow name exceeds 200 characters")

        clean_description = (description or "").strip()
        if len(clean_description) > 4000:
            raise ValidationFailed("Workflow description exceeds 4000 characters")

        now = utc_now()
        workflow = Workflow(
            id=_new_id("wf"),
            project=project,
            name=clean_name,
            description=clean_description,
            current_stage=StageType.REQUIREMENT,
            status=WorkflowStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        self._storage.save(workflow)
        self._log(
            action="workflow_create",
            workflow=workflow,
            stage=None,
            result="success",
            detail=f"Created workflow '{workflow.name}'",
        )
        return workflow

    # -- state helpers --------------------------------------------------

    def _touch(self, workflow: Workflow) -> None:
        workflow.updated_at = utc_now()

    def _transition_workflow(
        self, workflow: Workflow, target: WorkflowStatus
    ) -> None:
        if workflow.status is target:
            return
        assert_workflow_transition(workflow.status, target)
        workflow.status = target
        if target is WorkflowStatus.COMPLETED:
            workflow.completed_at = utc_now()
        self._touch(workflow)

    def _transition_stage(self, stage: WorkflowStage, target: StageStatus) -> None:
        if stage.status is target:
            return
        assert_stage_transition(stage.status, target)
        stage.status = target
        stage.updated_at = utc_now()

    # -- stage operations ----------------------------------------------

    def start_stage(self, workflow_id: str, stage_type: str) -> WorkflowStage:
        workflow = self.get(workflow_id)
        if workflow.status in TERMINAL_STATUSES:
            raise WorkflowTransitionError(
                f"Cannot start stage in terminal state: {workflow.status.value}"
            )

        stage_enum = _parse_stage(stage_type)
        target_status = STAGE_TO_STATUS[stage_enum]
        if workflow.status is not target_status:
            assert_workflow_transition(workflow.status, target_status)

        now = utc_now()
        stage = WorkflowStage(
            id=_new_id("stg"),
            workflow_id=workflow.id,
            stage_type=stage_enum,
            status=StageStatus.IN_PROGRESS,
            created_at=now,
            updated_at=now,
        )
        workflow.stages.append(stage)
        workflow.current_stage = stage_enum
        workflow.status = target_status
        self._touch(workflow)
        self._storage.save(workflow)
        self._log(
            action="workflow_stage_start",
            workflow=workflow,
            stage=stage,
            result="success",
            detail=f"Started stage {stage_enum.value}",
        )
        return stage

    def submit_report(
        self,
        workflow_id: str,
        stage_id: str,
        *,
        title: str,
        body: str,
    ) -> WorkflowStage:
        workflow = self.get(workflow_id)
        stage_id = _ensure_id(stage_id, _STAGE_ID_PATTERN, "stage id")
        stage = workflow.find_stage(stage_id)
        if stage is None:
            raise ResourceNotFound(f"Stage '{stage_id}' was not found")
        if stage.status not in {StageStatus.IN_PROGRESS, StageStatus.REJECTED, StageStatus.REPORTED}:
            raise WorkflowTransitionError(
                f"Cannot submit report in stage status {stage.status.value}"
            )

        report = validate_stage_report(stage.stage_type, title=title, body=body)
        stage.report_title = report.title
        stage.report = report.body

        # A rejected stage first returns to IN_PROGRESS on the next report cycle.
        if stage.status is StageStatus.REJECTED:
            self._transition_stage(stage, StageStatus.IN_PROGRESS)
        if stage.status is not StageStatus.REPORTED:
            self._transition_stage(stage, StageStatus.REPORTED)

        self._touch(workflow)
        self._storage.save(workflow)
        self._log(
            action="workflow_stage_report",
            workflow=workflow,
            stage=stage,
            result="success",
            detail=f"Report submitted: {stage.report_title}",
        )
        return stage

    def request_stage_approval(
        self, workflow_id: str, stage_id: str, *, reason: str
    ) -> tuple[Workflow, WorkflowStage, ApprovalRequest]:
        """Turn a REPORTED stage into a pending approval request."""
        workflow = self.get(workflow_id)
        stage_id = _ensure_id(stage_id, _STAGE_ID_PATTERN, "stage id")
        stage = workflow.find_stage(stage_id)
        if stage is None:
            raise ResourceNotFound(f"Stage '{stage_id}' was not found")
        if stage.status is not StageStatus.REPORTED:
            raise WorkflowTransitionError(
                f"Stage must be REPORTED before approval, got {stage.status.value}"
            )
        if not stage.report:
            raise ValidationFailed("Stage report is required before approval")
        if stage.stage_type is StageType.DELIVERY and stage.agent_ids:
            gate = stage.quality_gate or {}
            if not gate.get("readyForHumanApproval"):
                raise WorkflowTransitionError(
                    "DELIVERY requires a complete Review → Test → Risk quality gate before human approval"
                )

        preview = self._render_stage_preview(stage)
        approval = self._approvals.create(
            action="workflow_stage_approval",
            project=workflow.project,
            path=f"workflow/{workflow.id}#{stage.stage_type.value}",
            payload={
                "workflow_id": workflow.id,
                "stage_id": stage.id,
                "action_ids": list(stage.action_ids),
            },
            reason=reason or f"Approve stage {stage.stage_type.value}",
            preview=preview,
            workflow_id=workflow.id,
            stage_id=stage.id,
        )
        stage.approval_request_id = approval.request_id
        self._transition_stage(stage, StageStatus.WAITING_APPROVAL)
        self._transition_workflow(workflow, WorkflowStatus.WAITING_APPROVAL)
        self._storage.save(workflow)
        self._log(
            action="workflow_stage_await_approval",
            workflow=workflow,
            stage=stage,
            result="pending_approval",
            detail=f"Awaiting approval for stage {stage.stage_type.value}",
            request_id=approval.request_id,
        )
        return workflow, stage, approval

    def resolve_stage_approval(
        self,
        approval_request_id: str,
        *,
        approved: bool,
        approver: str | None = None,
    ) -> tuple[Workflow, WorkflowStage, list[str]]:
        """Called by the approval executor once the user approves the stage."""
        workflow, stage = self._locate_by_request(approval_request_id)

        if approved:
            self._transition_stage(stage, StageStatus.APPROVED)
            stage.approved_at = utc_now()
            stage.approved_by = approver
            approved_actions = self._approve_bound_actions(workflow, stage)
            self._advance_after_approval(workflow, stage)
        else:
            self._transition_stage(stage, StageStatus.REJECTED)
            approved_actions = []
            # Approvals still auto-drop any linked Level-1 low-risk actions.
            self._reject_bound_actions(workflow, stage)
            self._transition_workflow(
                workflow, STAGE_TO_STATUS[stage.stage_type]
            )

        self._touch(workflow)
        self._storage.save(workflow)
        self._log(
            action="workflow_stage_approved" if approved else "workflow_stage_rejected",
            workflow=workflow,
            stage=stage,
            result="success",
            detail=(
                f"Stage {stage.stage_type.value} approved with "
                f"{len(approved_actions)} bound action(s)"
                if approved
                else f"Stage {stage.stage_type.value} rejected"
            ),
            request_id=approval_request_id,
        )
        return workflow, stage, approved_actions

    def cancel(self, workflow_id: str, *, reason: str) -> Workflow:
        workflow = self.get(workflow_id)
        if workflow.status in TERMINAL_STATUSES:
            raise WorkflowTransitionError(
                f"Workflow already terminal: {workflow.status.value}"
            )
        clean_reason = (reason or "").strip()
        if not clean_reason:
            raise ValidationFailed("Cancellation reason must not be empty")

        # Cascade: any bound approvals that are still pending are failed.
        cancelled_actions: list[str] = []
        for stage in workflow.stages:
            for action_id in stage.action_ids:
                try:
                    request = self._approvals.get(action_id)
                except ResourceNotFound:
                    continue
                if request.status is ApprovalStatus.PENDING:
                    self._approvals.mark_failed(
                        action_id, f"Workflow cancelled: {clean_reason}"
                    )
                    cancelled_actions.append(action_id)
            if stage.approval_request_id:
                try:
                    request = self._approvals.get(stage.approval_request_id)
                except ResourceNotFound:
                    request = None
                if request and request.status is ApprovalStatus.PENDING:
                    self._approvals.mark_failed(
                        stage.approval_request_id,
                        f"Workflow cancelled: {clean_reason}",
                    )

        workflow.cancelled_reason = clean_reason
        assert_workflow_transition(workflow.status, WorkflowStatus.CANCELLED)
        workflow.status = WorkflowStatus.CANCELLED
        self._touch(workflow)
        self._storage.save(workflow)
        self._log(
            action="workflow_cancel",
            workflow=workflow,
            stage=None,
            result="success",
            detail=f"Cancelled: {clean_reason}. Voided {len(cancelled_actions)} pending action(s)",
        )
        return workflow

    # -- action binding -------------------------------------------------

    def validate_binding(
        self, workflow_id: str, stage_id: str, *, project: str | None = None
    ) -> tuple[Workflow, WorkflowStage]:
        workflow = self.get(workflow_id)
        stage_id = _ensure_id(stage_id, _STAGE_ID_PATTERN, "stage id")
        stage = workflow.find_stage(stage_id)
        if stage is None:
            raise ResourceNotFound(f"Stage '{stage_id}' was not found in workflow '{workflow_id}'")
        if project is not None and workflow.project != project:
            raise ValidationFailed("Workflow project does not match the requested project")
        if workflow.status in TERMINAL_STATUSES:
            raise WorkflowTransitionError(
                f"Cannot bind tools in terminal state: {workflow.status.value}"
            )
        return workflow, stage

    def attach_action(
        self,
        *,
        workflow_id: str,
        stage_id: str,
        approval_request_id: str,
    ) -> WorkflowStage:
        workflow, stage = self.validate_binding(workflow_id, stage_id)
        if stage.status not in {StageStatus.IN_PROGRESS, StageStatus.REPORTED}:
            raise WorkflowTransitionError(
                f"Cannot attach actions in stage status {stage.status.value}"
            )
        approval = self._approvals.get(approval_request_id)
        if approval.project != workflow.project:
            raise ValidationFailed("Action project does not match workflow project")
        self._approvals.attach_binding(
            approval_request_id,
            workflow_id=workflow.id,
            stage_id=stage.id,
        )
        if approval_request_id not in stage.action_ids:
            stage.action_ids.append(approval_request_id)
        stage.updated_at = utc_now()
        self._touch(workflow)
        self._storage.save(workflow)
        return stage

    def attach_agent(
        self,
        *,
        workflow_id: str,
        stage_id: str,
        agent_id: str,
    ) -> WorkflowStage:
        workflow, stage = self.validate_binding(workflow_id, stage_id)
        if stage.status not in {StageStatus.IN_PROGRESS, StageStatus.REPORTED}:
            raise WorkflowTransitionError(
                f"Cannot attach agents in stage status {stage.status.value}"
            )
        clean_agent_id = (agent_id or "").strip()
        if not clean_agent_id.startswith("ag_"):
            raise ValidationFailed("Invalid agent id")
        if clean_agent_id not in stage.agent_ids:
            stage.agent_ids.append(clean_agent_id)
        stage.updated_at = utc_now()
        self._touch(workflow)
        self._storage.save(workflow)
        self._log(
            action="workflow_agent_attach",
            workflow=workflow,
            stage=stage,
            result="success",
            detail=f"Attached agent {clean_agent_id}",
        )
        return stage

    def attach_quality_gate(
        self,
        workflow_id: str,
        stage_id: str,
        quality_gate: dict[str, Any],
    ) -> WorkflowStage:
        workflow, stage = self.validate_binding(workflow_id, stage_id)
        if stage.status not in {StageStatus.IN_PROGRESS, StageStatus.REPORTED}:
            raise WorkflowTransitionError(
                f"Cannot attach quality gate in stage status {stage.status.value}"
            )
        if not quality_gate.get("readyForHumanApproval"):
            raise ValidationFailed("Quality gate is not ready for human approval")
        stage.quality_gate = dict(quality_gate)
        stage.updated_at = utc_now()
        self._touch(workflow)
        self._storage.save(workflow)
        self._log(
            action="quality_gate_submit",
            workflow=workflow,
            stage=stage,
            result="success",
            detail="Review, test and risk gate attached",
        )
        return stage

    def record_test_result(
        self,
        workflow_id: str,
        stage_id: str,
        *,
        command: str,
        passed: bool,
        timed_out: bool,
        exit_code: int | None,
        stdout: str,
        stderr: str,
    ) -> WorkflowStage:
        workflow, stage = self.validate_binding(workflow_id, stage_id)
        if stage.stage_type is not StageType.TESTING:
            raise ValidationFailed("Test results can only attach to a TESTING stage")
        if stage.status not in {StageStatus.IN_PROGRESS, StageStatus.REPORTED}:
            raise WorkflowTransitionError(
                f"Cannot attach test result in stage status {stage.status.value}"
            )
        verdict = "passed" if passed else "failed"
        if timed_out:
            verdict = "timed out"
        output = (stdout or stderr or "No output").strip()
        if len(output) > 4000:
            output = output[:4000] + "\n... [report excerpt truncated]"
        stage.report_title = f"Testing Report — {command}"
        stage.report = (
            f"## Coverage\n\nCommand: `{command}`\n\n"
            f"## Results\n\n{verdict}; exit code: {exit_code}\n\n{output}\n\n"
            f"## Gaps\n\nAutomated command output only; manual and integration coverage may remain."
        )
        if stage.status is StageStatus.IN_PROGRESS:
            self._transition_stage(stage, StageStatus.REPORTED)
        self._touch(workflow)
        self._storage.save(workflow)
        self._log(
            action="workflow_test_result",
            workflow=workflow,
            stage=stage,
            result="success",
            detail=f"{command}: {verdict}",
        )
        return stage

    # -- rendering ------------------------------------------------------

    def _render_stage_preview(self, stage: WorkflowStage) -> str:
        title = stage.report_title or f"{stage.stage_type.value} report"
        actions_line = f"Bound actions: {len(stage.action_ids)}; agents: {len(stage.agent_ids)}"
        excerpt = (stage.report or "").strip()
        if len(excerpt) > 1200:
            excerpt = excerpt[:1200] + "\n... [truncated]"
        return f"# {title}\n\n{actions_line}\n\n{excerpt}"

    # -- helpers --------------------------------------------------------

    def _locate_by_request(
        self, approval_request_id: str
    ) -> tuple[Workflow, WorkflowStage]:
        for workflow in self._storage.all():
            for stage in workflow.stages:
                if stage.approval_request_id == approval_request_id:
                    return workflow, stage
        raise ResourceNotFound(
            f"No workflow stage bound to approval {approval_request_id}"
        )

    def _approve_bound_actions(
        self, workflow: Workflow, stage: WorkflowStage
    ) -> list[str]:
        """Batch-approve LEVEL_1 actions attached to the stage.

        High-risk actions (LEVEL_2) are intentionally left pending so they must
        be confirmed one by one.
        """
        approved: list[str] = []
        for action_id in stage.action_ids:
            try:
                request = self._approvals.get(action_id)
            except ResourceNotFound:
                continue
            if request.status is not ApprovalStatus.PENDING:
                continue
            if request.permission_level is PermissionLevel.LEVEL_2:
                # Stage approval never bypasses high-risk individual confirmation.
                continue
            self._approvals.mark_approved(action_id)
            approved.append(action_id)
        return approved

    def _reject_bound_actions(
        self, workflow: Workflow, stage: WorkflowStage
    ) -> None:
        for action_id in stage.action_ids:
            try:
                request = self._approvals.get(action_id)
            except ResourceNotFound:
                continue
            if request.status is ApprovalStatus.PENDING:
                self._approvals.mark_failed(
                    action_id, f"Stage {stage.stage_type.value} rejected"
                )

    def _advance_after_approval(
        self, workflow: Workflow, stage: WorkflowStage
    ) -> None:
        upcoming = next_stage(stage.stage_type)
        if upcoming is None:
            # Delivery approved -> workflow completes.
            self._transition_workflow(workflow, WorkflowStatus.COMPLETED)
            return
        target_status = STAGE_TO_STATUS[upcoming]
        self._transition_workflow(workflow, target_status)
        workflow.current_stage = upcoming


def _parse_stage(value: str) -> StageType:
    cleaned = (value or "").strip().upper()
    if not cleaned:
        raise ValidationFailed("Field 'stage_type' must not be empty")
    try:
        return StageType(cleaned)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in STAGE_ORDER)
        raise ValidationFailed(
            f"Unknown stage_type '{value}'. Allowed: {allowed}"
        ) from exc


__all__ = ["WorkflowManager", "_parse_stage"]
