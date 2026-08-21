"""Task state machine; it never executes an action itself."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.audit.logger import AuditLogger
from app.event import EventBus, EventType
from app.security.validator import ApprovalError

from .models import Task, TaskStatus
from .storage import TaskStorage


class TaskTransitionError(ApprovalError):
    pass


_ALLOWED: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.WAITING_APPROVAL, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.WAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {TaskStatus.PENDING, TaskStatus.WAITING_APPROVAL, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(), TaskStatus.FAILED: set(), TaskStatus.CANCELLED: set(),
}


class TaskManager:
    def __init__(self, storage: TaskStorage, audit: AuditLogger | None = None, events: EventBus | None = None) -> None:
        self.storage, self.audit, self.events = storage, audit, events

    def create_task(self, *, workflow_id: str, stage_id: str, agent_id: str, priority: int = 0, context: dict[str, Any] | None = None) -> Task:
        if not workflow_id or not stage_id or not agent_id:
            raise TaskTransitionError("workflow_id, stage_id and agent_id are required")
        if priority < 0 or priority > 100:
            raise TaskTransitionError("priority must be between 0 and 100")
        task = Task.create(workflow_id=workflow_id, stage_id=stage_id, agent_id=agent_id, priority=priority, context=context or {})
        self.storage.save(task)
        self._record(task, "task_created")
        if self.events: self.events.publish(EventType.TASK_CREATED, source="task.manager", payload=task.as_dict())
        return task

    def get_task(self, task_id: str) -> Task: return self.storage.get(task_id)
    def list_tasks(self, *, status: TaskStatus | None = None, limit: int = 100) -> list[Task]: return self.storage.list(status=status, limit=max(1, min(limit, 500)))

    def transition(self, task_id: str, status: TaskStatus | str) -> Task:
        task = self.get_task(task_id)
        try: target = status if isinstance(status, TaskStatus) else TaskStatus(status.upper())
        except ValueError as exc: raise TaskTransitionError("Unknown task status") from exc
        if target not in _ALLOWED[task.status]:
            raise TaskTransitionError(f"Task {task.id} cannot transition {task.status.value} -> {target.value}")
        task.status = target
        task.updated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.storage.save(task)
        action = "task_completed" if target is TaskStatus.COMPLETED else "task_transition"
        self._record(task, action)
        if self.events and target is TaskStatus.COMPLETED:
            self.events.publish(EventType.TASK_COMPLETED, source="task.manager", payload=task.as_dict())
        return task

    def start_task(self, task_id: str) -> Task: return self.transition(task_id, TaskStatus.RUNNING)
    def complete_task(self, task_id: str) -> Task: return self.transition(task_id, TaskStatus.COMPLETED)
    def cancel_task(self, task_id: str) -> Task: return self.transition(task_id, TaskStatus.CANCELLED)

    def _record(self, task: Task, action: str) -> None:
        if self.audit:
            self.audit.record(action=action, path=f"task/{task.id}", permission="LEVEL_1", approved=True, result="success", detail=f"status={task.status.value}")
