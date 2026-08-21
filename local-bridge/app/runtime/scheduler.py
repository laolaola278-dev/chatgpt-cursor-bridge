"""Runtime scheduler: inspect and propose, never execute."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.audit.logger import AuditLogger
from app.event import EventBus, EventType
from app.security.validator import ApprovalError
from app.task import TaskManager, TaskStatus

from .models import AgentRuntime, ExecutionProposal, RuntimeState
from .state_store import RuntimeStateStore


_ALLOWED: dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.CREATED: {RuntimeState.READY, RuntimeState.FAILED},
    RuntimeState.READY: {RuntimeState.RUNNING, RuntimeState.FAILED},
    RuntimeState.RUNNING: {RuntimeState.WAITING_APPROVAL, RuntimeState.WAITING_FEEDBACK, RuntimeState.COMPLETED, RuntimeState.FAILED, RuntimeState.RECOVERED},
    RuntimeState.WAITING_APPROVAL: {RuntimeState.RUNNING, RuntimeState.WAITING_FEEDBACK, RuntimeState.FAILED},
    RuntimeState.WAITING_FEEDBACK: {RuntimeState.RUNNING, RuntimeState.COMPLETED, RuntimeState.FAILED},
    RuntimeState.RECOVERED: {RuntimeState.READY, RuntimeState.FAILED},
    RuntimeState.COMPLETED: set(), RuntimeState.FAILED: set(),
}


class RuntimeScheduler:
    def __init__(self, *, store: RuntimeStateStore, tasks: TaskManager, audit: AuditLogger | None = None, events: EventBus | None = None, session_is_active: Callable[[str], bool] | None = None, workflow_is_allowed: Callable[[str, str], bool] | None = None, agent_exists: Callable[[str], bool] | None = None) -> None:
        self.store, self.tasks, self.audit, self.events = store, tasks, audit, events
        self.session_is_active = session_is_active or (lambda session_id: bool(session_id))
        self.workflow_is_allowed = workflow_is_allowed or (lambda workflow_id, stage_id: bool(workflow_id and stage_id))
        self.agent_exists = agent_exists or (lambda agent_id: bool(agent_id))

    def create(self, *, agent_id: str, session_id: str, workflow_id: str, stage_id: str) -> AgentRuntime:
        runtime = AgentRuntime.create(agent_id=agent_id, session_id=session_id, workflow_id=workflow_id, stage_id=stage_id)
        self.store.save(runtime); self._record(runtime, "runtime_created")
        if self.events: self.events.publish(EventType.RUNTIME_CREATED, source="runtime.scheduler", payload=runtime.as_dict())
        return runtime

    def get(self, runtime_id: str) -> AgentRuntime: return self.store.get(runtime_id)
    def list(self) -> list[AgentRuntime]: return self.store.list()

    def transition(self, runtime_id: str, target: RuntimeState | str) -> AgentRuntime:
        runtime = self.get(runtime_id)
        try: next_state = target if isinstance(target, RuntimeState) else RuntimeState(target.upper())
        except ValueError as exc: raise ApprovalError("Unknown runtime state") from exc
        if next_state not in _ALLOWED[runtime.state]: raise ApprovalError(f"Runtime {runtime.id} cannot transition {runtime.state.value} -> {next_state.value}")
        previous = runtime.state; runtime.state = next_state; runtime.updated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds"); runtime.history.append({"from": previous.value, "to": next_state.value, "at": runtime.updated_at}); self.store.save(runtime); self._record(runtime, "runtime_transition")
        if self.events and next_state is RuntimeState.RUNNING: self.events.publish(EventType.RUNTIME_STARTED, source="runtime.scheduler", payload=runtime.as_dict())
        return runtime

    def proposals(self, runtime_id: str) -> list[ExecutionProposal]:
        runtime = self.get(runtime_id)
        if runtime.state not in {RuntimeState.READY, RuntimeState.RUNNING, RuntimeState.WAITING_FEEDBACK}:
            return []
        if not self.session_is_active(runtime.session_id) or not self.workflow_is_allowed(runtime.workflow_id, runtime.stage_id) or not self.agent_exists(runtime.agent_id):
            return []
        proposals = [ExecutionProposal.for_task(task, runtime.id) for task in self.tasks.list_tasks(status=TaskStatus.PENDING) if task.workflow_id == runtime.workflow_id and task.stage_id == runtime.stage_id and task.agent_id == runtime.agent_id]
        for proposal in proposals:
            if self.audit: self.audit.record(action="execution_proposal", path=f"runtime/{runtime.id}/task/{proposal.task_id}", permission="LEVEL_1", approved=False, result="proposal", detail=proposal.reason)
        return proposals

    def execute(self, *_args, **_kwargs) -> None:
        raise ApprovalError("Scheduler cannot execute; it only creates Execution Proposals")

    def _record(self, runtime: AgentRuntime, action: str) -> None:
        if self.audit: self.audit.record(action=action, path=f"runtime/{runtime.id}", permission="LEVEL_1", approved=True, result="success", detail=f"state={runtime.state.value}")
