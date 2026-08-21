from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.security.permissions import ApprovalStore
from app.security.validator import ResourceNotFound, ValidationFailed
from app.workflow.manager import WorkflowManager

from .executor import ControlledExecutor
from .models import (
    ExecutionProposal,
    ExecutionResult,
    ExecutionTask,
    ExecutionTaskStatus,
)
from .planner import ExecutionPlanner
from .storage import ExecutionStorage

_ALLOWED_TASK_TRANSITIONS: dict[ExecutionTaskStatus, set[ExecutionTaskStatus]] = {
    ExecutionTaskStatus.PROPOSED: {ExecutionTaskStatus.APPROVAL_REQUIRED},
    ExecutionTaskStatus.APPROVAL_REQUIRED: {ExecutionTaskStatus.APPROVED, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.ROLLED_BACK},
    ExecutionTaskStatus.APPROVED: {ExecutionTaskStatus.EXECUTING, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.ROLLED_BACK},
    ExecutionTaskStatus.EXECUTING: {ExecutionTaskStatus.VERIFYING, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.ROLLED_BACK},
    ExecutionTaskStatus.VERIFYING: {ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.FAILED, ExecutionTaskStatus.ROLLED_BACK},
    ExecutionTaskStatus.COMPLETED: set(),
    ExecutionTaskStatus.FAILED: set(),
    ExecutionTaskStatus.ROLLED_BACK: set(),
}


class ExecutionManager:
    def __init__(
        self,
        storage: ExecutionStorage,
        settings: Settings,
        *,
        approvals: ApprovalStore | None = None,
        workflow_manager: WorkflowManager | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.approvals = approvals
        self.workflow_manager = workflow_manager
        self.planner = ExecutionPlanner()
        self.executor = ControlledExecutor(
            storage,
            settings,
            approvals=approvals,
            workflow_manager=workflow_manager,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _transition(task: ExecutionTask, target: ExecutionTaskStatus) -> ExecutionTask:
        if target not in _ALLOWED_TASK_TRANSITIONS[task.status]:
            raise ValidationFailed(f"Illegal execution task transition {task.status.value} -> {target.value}")
        task.status = target
        task.updated_at = ExecutionManager._now()
        return task

    # -- task lifecycle -------------------------------------------------

    def create_from_plan(self, *, plan_id: str, project: str, workflow_id: str | None, plan_content: str) -> list[ExecutionTask]:
        drafts = self.planner.build_tasks(
            plan_id=plan_id,
            project=project,
            workflow_id=workflow_id,
            plan_content=plan_content,
        )
        now = self._now()
        saved: list[ExecutionTask] = []
        for draft in drafts:
            task = ExecutionTask(
                id=draft.id,
                workflow_id=draft.workflow_id,
                plan_id=draft.plan_id,
                project=draft.project,
                title=draft.title,
                task_type=draft.task_type,
                files=draft.files,
                dependencies=draft.dependencies,
                risk=draft.risk,
                risk_score=draft.risk_score,
                status=ExecutionTaskStatus.PROPOSED,
                created_at=now,
                updated_at=now,
            )
            self.storage.save_task(task)
            saved.append(task)
        return saved

    def get_task(self, task_id: str) -> ExecutionTask:
        task = self.storage.get_task(task_id)
        if task is None:
            raise ResourceNotFound(f"Execution task '{task_id}' was not found")
        return task

    def list_tasks(self, project: str | None = None, status: str | None = None, limit: int = 200) -> list[ExecutionTask]:
        return self.storage.list_tasks(project=project, status=status, limit=limit)

    # -- proposal lifecycle ----------------------------------------------

    def generate_proposal(self, task_id: str) -> ExecutionProposal:
        task = self.get_task(task_id)
        proposal = self.planner.build_proposal(task)
        proposal.created_at = self._now()
        self.storage.save_proposal(proposal)
        self._transition(task, ExecutionTaskStatus.APPROVAL_REQUIRED)
        self.storage.save_task(task)
        return proposal

    def get_proposal(self, proposal_id: str) -> ExecutionProposal:
        proposal = self.storage.get_proposal(proposal_id)
        if proposal is None:
            raise ResourceNotFound(f"Execution proposal '{proposal_id}' was not found")
        return proposal

    def list_proposals(self, project: str | None = None, status: str | None = None, limit: int = 200) -> list[ExecutionProposal]:
        return self.storage.list_proposals(project=project, status=status, limit=limit)

    # -- controlled execution -------------------------------------------

    def execute(self, proposal_id: str, *, approval_id: str | None = None) -> ExecutionResult:
        proposal = self.get_proposal(proposal_id)
        task = self.get_task(proposal.task_id)
        self._transition(task, ExecutionTaskStatus.APPROVED)
        self.storage.save_task(task)
        return self.executor.execute(task, proposal, approval_id=approval_id)

    def result_for_proposal(self, proposal_id: str) -> ExecutionResult | None:
        return self.storage.get_result_for_proposal(proposal_id)

    def list_results(self, project: str | None = None, limit: int = 200) -> list[ExecutionResult]:
        return self.storage.list_results(project=project, limit=limit)

    def verification(self, task_id: str) -> dict:
        task = self.get_task(task_id)
        if task.verification:
            return task.verification
        result = self.storage.get_result_for_proposal(
            next((proposal.id for proposal in self.storage.list_proposals(project=task.project) if proposal.task_id == task_id), "")
        )
        if result is not None:
            return result.verification
        raise ResourceNotFound(f"No verification exists for execution task '{task_id}'")

    def mark_rolled_back(self, task_id: str) -> ExecutionTask:
        task = self.get_task(task_id)
        self._transition(task, ExecutionTaskStatus.ROLLED_BACK)
        self.storage.save_task(task)
        return task
