from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_hex
from typing import Any

from app.audit.logger import AuditLogger
from app.config import Settings
from app.execution import ExecutionManager, ExecutionStorage
from app.execution.models import ExecutionResult
from app.execution.verification_pipeline import VerificationPipeline
from app.quality.gate8 import QualityGate8Evaluator
from app.security.permissions import ApprovalStore
from app.security.validator import ResourceNotFound, ValidationFailed

from .models import ExecutionLoop, LoopStatus
from .rollback_manager import ExecutionLoopRollbackManager
from .storage import ExecutionLoopStorage

_ALLOWED: dict[LoopStatus, set[LoopStatus]] = {
    LoopStatus.CREATED: {LoopStatus.PLANNING, LoopStatus.CANCELLED},
    LoopStatus.PLANNING: {LoopStatus.PROPOSAL_READY, LoopStatus.FAILED, LoopStatus.CANCELLED, LoopStatus.RECOVERED},
    LoopStatus.PROPOSAL_READY: {LoopStatus.WAITING_APPROVAL, LoopStatus.FAILED, LoopStatus.CANCELLED, LoopStatus.RECOVERED},
    LoopStatus.WAITING_APPROVAL: {LoopStatus.EXECUTING, LoopStatus.FAILED, LoopStatus.CANCELLED, LoopStatus.RECOVERED},
    LoopStatus.EXECUTING: {LoopStatus.VERIFYING, LoopStatus.FAILED, LoopStatus.ROLLED_BACK, LoopStatus.RECOVERED},
    LoopStatus.VERIFYING: {LoopStatus.COMPLETED, LoopStatus.FAILED, LoopStatus.ROLLED_BACK, LoopStatus.RECOVERED},
    LoopStatus.RECOVERED: {LoopStatus.WAITING_APPROVAL, LoopStatus.FAILED, LoopStatus.ROLLED_BACK, LoopStatus.CANCELLED},
    LoopStatus.FAILED: {LoopStatus.ROLLED_BACK},
    LoopStatus.COMPLETED: set(),
    LoopStatus.ROLLED_BACK: set(),
    LoopStatus.CANCELLED: set(),
}


class ExecutionLoopOrchestrator:
    """Coordinate the approval-controlled engineering loop.

    The orchestrator only assigns metadata, generates proposals, collects
    results and queues approvals. It never modifies files, never calls shell,
    and never executes actions directly: all execution goes through
    ``ControlledExecutor`` via the existing /permission/approve pipeline.
    """

    def __init__(
        self,
        storage: ExecutionLoopStorage,
        settings: Settings,
        *,
        approvals: ApprovalStore,
        audit: AuditLogger,
        execution_manager: ExecutionManager | None = None,
        pipeline: VerificationPipeline | None = None,
        rollback_manager: ExecutionLoopRollbackManager | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.approvals = approvals
        self.audit = audit
        self.execution_manager = execution_manager or ExecutionManager(
            ExecutionStorage(settings.execution_db_path), settings, approvals=approvals
        )
        self.pipeline = pipeline or VerificationPipeline()
        self.rollback_manager = rollback_manager or ExecutionLoopRollbackManager(settings)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _transition(self, loop: ExecutionLoop, target: LoopStatus, detail: str = "") -> ExecutionLoop:
        if target not in _ALLOWED[loop.status]:
            raise ValidationFailed(f"Illegal execution loop transition {loop.status.value} -> {target.value}")
        now = self._now()
        loop.status = target
        loop.updated_at = now
        loop.history.append({"status": target.value, "at": now, "detail": detail})
        self.audit.record(
            action="execution_loop_transition",
            path=f"{loop.project}:loop/{loop.id}",
            permission="LEVEL_1",
            approved=False,
            result="transition",
            detail=f"{loop.status.value} (loop {loop.id}) {detail}".strip(),
        )
        self.storage.save(loop)
        return loop

    # -- lifecycle ------------------------------------------------------

    def create(self, *, project: str, plan_id: str, workflow_id: str | None, approval_id: str | None = None) -> ExecutionLoop:
        loop = ExecutionLoop(
            id=f"eloop_{token_hex(8)}",
            project=project,
            plan_id=plan_id,
            workflow_id=workflow_id,
            task_ids=[],
            approval_id=approval_id,
            created_at=self._now(),
            updated_at=self._now(),
            history=[],
        )
        loop.history.append({"status": LoopStatus.CREATED.value, "at": loop.created_at, "detail": "loop created"})
        self.audit.record(
            action="execution_loop_created",
            path=f"{project}:loop/{loop.id}",
            permission="LEVEL_1",
            approved=False,
            result="created",
            detail=f"Execution loop {loop.id} created from plan {plan_id}",
        )
        plan = self._load_plan(plan_id)
        tasks = self.execution_manager.create_from_plan(
            plan_id=plan_id, project=project, workflow_id=workflow_id, plan_content=plan["content"]
        )
        loop.task_ids = [task.id for task in tasks]
        loop.history.append({"status": LoopStatus.PLANNING.value, "at": self._now(), "detail": f"{len(tasks)} task(s) planned"})
        loop.status = LoopStatus.PLANNING
        loop.updated_at = self._now()
        self.storage.save(loop)
        return loop

    def _load_plan(self, plan_id: str) -> dict[str, Any]:
        from app.simulation import SimulationStorage

        plan = SimulationStorage(self.settings.simulation_db_path).get_plan(plan_id)
        if plan is None:
            raise ResourceNotFound(f"Engineering plan '{plan_id}' was not found")
        return {"id": plan.id, "content": plan.content}

    def get(self, loop_id: str) -> ExecutionLoop:
        loop = self.storage.get(loop_id)
        if loop is None:
            raise ResourceNotFound(f"Execution loop '{loop_id}' was not found")
        return loop

    def list_loops(self, project: str | None = None, limit: int = 200) -> list[ExecutionLoop]:
        return self.storage.list_loops(project=project, limit=limit)

    def find_loop_for_task(self, task_id: str) -> ExecutionLoop | None:
        return self.storage.find_by_task(task_id)

    # -- prepare --------------------------------------------------------

    def prepare(self, loop_id: str, *, approval_id: str | None = None) -> ExecutionLoop:
        loop = self.get(loop_id)
        if loop.proposal_id is not None:
            raise ValidationFailed("Execution loop already has a proposal")
        if not loop.task_ids:
            raise ValidationFailed("Execution loop has no planned tasks")
        proposal = self.execution_manager.generate_proposal(loop.task_ids[0])
        loop.proposal_id = proposal.id
        loop.approval_id = approval_id or loop.approval_id
        self._transition(loop, LoopStatus.PROPOSAL_READY, "proposal generated")
        self._transition(loop, LoopStatus.WAITING_APPROVAL, "awaiting human approval for execution")
        self.audit.record(action="execution_proposal_generated", path=f"{loop.project}:loop/{loop.id}", permission="LEVEL_1", approved=False, result="proposal", detail=f"proposal {proposal.id} bound to loop {loop.id}")
        return loop

    # -- post-execution hook (called by _execute_action) ----------------

    def on_executed(self, loop_id: str, result: ExecutionResult) -> ExecutionLoop:
        loop = self.get(loop_id)
        loop.result_id = result.id
        self._transition(loop, LoopStatus.EXECUTING, "controlled execution approved")
        self._transition(loop, LoopStatus.VERIFYING, "execution result recorded")
        self.audit.record(action="execution_started", path=f"{loop.project}:loop/{loop.id}", permission="LEVEL_1", approved=True, result="executed", detail=f"result {result.id} recorded")
        return loop

    # -- verification ---------------------------------------------------

    def verify(self, loop_id: str, *, approval_id: str | None = None, quality_score: int | None = None, risk_score: int | None = None, test_passed: bool | None = None) -> ExecutionLoop:
        loop = self.get(loop_id)
        if loop.result_id is None:
            raise ValidationFailed("Execution loop has no result to verify")
        result = self.execution_manager.storage.get_result(loop.result_id)
        if result is None:
            raise ResourceNotFound(f"Execution result '{loop.result_id}' was not found")
        report = self.pipeline.build(result, quality_score=quality_score, risk_score=risk_score, test_passed=test_passed)
        self.pipeline.validate(report)
        loop.verification = report
        quality = QualityGate8Evaluator().evaluate(
            approval_present=True,
            snapshot_present=bool(result.verification.get("snapshotCaptured")),
            verification_status=report["status"],
            risk_level=self._loop_risk(loop),
            rollback_capability=True,
            test_result=report["testResult"],
            confidence=report.get("qualityScore") or (80 if report["status"] == "PASS" else 30),
        )
        loop.quality = quality
        target = LoopStatus.COMPLETED if report["status"] == "PASS" else LoopStatus.FAILED
        self._transition(loop, target, f"verification {report['status']}")
        self.audit.record(action="execution_verified", path=f"{loop.project}:loop/{loop.id}", permission="LEVEL_1", approved=True, result=report["status"].lower(), detail=f"{len(report['checks'])} check(s)")
        if target is LoopStatus.COMPLETED:
            self._queue_learning_memory(loop, category="history", document="execution-history.md")
        else:
            self._queue_learning_memory(loop, category="failures", document="failure-patterns.md")
        return loop

    def _loop_risk(self, loop: ExecutionLoop) -> str:
        task = self.execution_manager.storage.get_task(loop.task_ids[0]) if loop.task_ids else None
        return task.risk if task else "medium"

    def _queue_learning_memory(self, loop: ExecutionLoop, *, category: str, document: str) -> None:
        if loop.memory_proposal_id:
            return
        checks = loop.verification.get("checks", [])
        content = (
            f"## Execution Loop: {loop.id}\n\n"
            f"- Status: {loop.status.value}\n"
            f"- Verification: {', '.join(checks)}\n"
            f"- Quality: {loop.quality.get('quality', '')}/100\n"
        )
        request = self.approvals.create(
            action="execution_memory_append",
            project=loop.project,
            path=f"memory/execution/{document}",
            payload={"category": category, "content": content},
            reason=f"Record loop learning memory for {loop.id}",
            preview=f"[execution memory proposal/{category}]\n\n{content[:1200]}",
            execution_loop_id=loop.id,
        )
        loop.memory_proposal_id = request.request_id
        self.storage.save(loop)
        self.audit.record(action="execution_memory_append", path=f"{loop.project}:memory/execution/{document}", permission="LEVEL_1", approved=False, result="pending_approval", detail="Loop learning memory proposal queued; separate approval required", request_id=request.request_id)

    # -- recovery (Runtime Recovery 2.0) --------------------------------

    def recover(self, loop_id: str, *, approval_id: str | None = None) -> ExecutionLoop:
        """Mark an interrupted loop as RECOVERED.

        Recovery is metadata only: it never resumes execution, never approves a
        proposal, and never invokes the executor. The user must explicitly
        confirm and re-approve any subsequent prepare/verify step.
        """
        loop = self.get(loop_id)
        loop.approval_id = approval_id or loop.approval_id
        self._transition(loop, LoopStatus.RECOVERED, "interrupted loop recovered; user confirmation required")
        self.audit.record(
            action="execution_loop_recovered",
            path=f"{loop.project}:loop/{loop.id}",
            permission="LEVEL_1",
            approved=False,
            result="recovered",
            detail="Loop marked RECOVERED after restart; no automatic continuation",
        )
        return loop

    # -- rollback -------------------------------------------------------

    def rollback(self, loop_id: str, *, approval_id: str | None = None) -> ExecutionLoop:
        loop = self.get(loop_id)
        preview = self.rollback_manager.preview(loop)
        if not preview["snapshots"]:
            raise ResourceNotFound("No rollback snapshots exist for this loop")
        restored = self.rollback_manager.restore(loop)
        loop.rollback = {**restored, "approvalId": approval_id, "preview": preview}
        self._transition(loop, LoopStatus.ROLLED_BACK, "reverse-order rollback applied")
        self.audit.record(action="execution_rolled_back", path=f"{loop.project}:loop/{loop.id}", permission="LEVEL_1", approved=True, result="rolled_back", detail=f"restored {restored['count']} file(s)")
        return loop

    def timeline(self, loop_id: str) -> list[dict[str, str]]:
        return self.get(loop_id).history
