"""Event contracts for the local runtime."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(str, Enum):
    RUNTIME_CREATED = "runtime.created"
    RUNTIME_STARTED = "runtime.started"
    AGENT_STARTED = "agent.started"
    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_COMPLETED = "approval.completed"
    EXECUTION_FINISHED = "execution.finished"
    MEMORY_UPDATED = "memory.updated"


@dataclass(frozen=True)
class Event:
    event_id: str
    timestamp: str
    event_type: str
    source: str
    payload: dict[str, Any]
    audit_id: str
    checksum: str

    @classmethod
    def create(
        cls,
        event_type: str | EventType,
        *,
        source: str,
        payload: dict[str, Any],
        audit_id: str | None = None,
    ) -> "Event":
        event = cls(
            event_id=f"evt_{secrets.token_hex(10)}",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            event_type=event_type.value if isinstance(event_type, EventType) else event_type,
            source=source,
            payload=dict(payload),
            audit_id=audit_id or f"aud_{secrets.token_hex(10)}",
            checksum="",
        )
        return cls(**{**event.__dict__, "checksum": event.calculate_checksum()})

    def _unsigned(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "timestamp": self.timestamp,
            "type": self.event_type,
            "source": self.source,
            "payload": self.payload,
            "auditId": self.audit_id,
        }

    def calculate_checksum(self) -> str:
        raw = json.dumps(self._unsigned(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def is_valid(self) -> bool:
        return bool(self.event_id and self.audit_id and self.checksum == self.calculate_checksum())

    def as_dict(self) -> dict[str, Any]:
        return {**self._unsigned(), "checksum": self.checksum}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Event":
        return cls(
            event_id=str(value["eventId"]),
            timestamp=str(value["timestamp"]),
            event_type=str(value["type"]),
            source=str(value["source"]),
            payload=dict(value.get("payload") or {}),
            audit_id=str(value["auditId"]),
            checksum=str(value["checksum"]),
        )
