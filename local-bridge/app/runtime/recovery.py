"""Restart recovery for interrupted runtime metadata."""

from __future__ import annotations

from datetime import datetime, timezone

from app.audit.logger import AuditLogger
from app.event import EventBus

from .models import RuntimeState
from .scheduler import RuntimeScheduler


class RuntimeRecovery:
    def __init__(self, scheduler: RuntimeScheduler, audit: AuditLogger | None = None, events: EventBus | None = None) -> None:
        self.scheduler, self.audit, self.events = scheduler, audit, events

    def recover(self) -> list[dict[str, object]]:
        recovered: list[dict[str, object]] = []
        for runtime in self.scheduler.store.running():
            runtime.state = RuntimeState.RECOVERED
            runtime.updated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            runtime.history.append({"from": RuntimeState.RUNNING.value, "to": RuntimeState.RECOVERED.value, "at": runtime.updated_at})
            self.scheduler.store.save(runtime)
            payload = {"runtimeId": runtime.id, "state": runtime.state.value, "requiresConfirmation": True, "autoResumed": False}
            recovered.append(payload)
            if self.audit: self.audit.record(action="runtime_recovered", path=f"runtime/{runtime.id}", permission="LEVEL_1", approved=False, result="recovered", detail="Startup recovery requires explicit user confirmation")
        return recovered
