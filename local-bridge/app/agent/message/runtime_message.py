"""Audited, metadata-only messages between built-in agent roles."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any

from app.audit.logger import AuditLogger


class RuntimeMessageType(str, Enum):
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    REPORT = "REPORT"
    BLOCK = "BLOCK"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


@dataclass(frozen=True)
class RuntimeMessage:
    message_id: str
    sender: str
    receiver: str
    message_type: RuntimeMessageType
    task_id: str
    workflow_id: str
    context_reference: str
    timestamp: str
    body: str

    @classmethod
    def create(cls, *, sender: str, receiver: str, message_type: RuntimeMessageType | str, task_id: str, workflow_id: str, context_reference: str = "", body: str = "") -> "RuntimeMessage":
        return cls(f"msg_{secrets.token_hex(8)}", sender, receiver, RuntimeMessageType(message_type), task_id, workflow_id, context_reference, datetime.now(timezone.utc).isoformat(timespec="milliseconds"), body)

    def as_dict(self) -> dict[str, Any]:
        return {"messageId": self.message_id, "sender": self.sender, "receiver": self.receiver, "type": self.message_type.value, "taskId": self.task_id, "workflowId": self.workflow_id, "contextReference": self.context_reference, "timestamp": self.timestamp, "body": self.body}


class RuntimeMessageStore:
    def __init__(self, root: str | Path, audit: AuditLogger | None = None) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True); self.path = self.root / "runtime.jsonl"; self.audit = audit; self._lock = Lock()

    def append(self, message: RuntimeMessage) -> RuntimeMessage:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(message.as_dict(), ensure_ascii=False) + "\n")
        if self.audit: self.audit.record(action="agent_runtime_message", path=f"messages/{message.message_id}", permission="LEVEL_1", approved=True, result="success", detail=f"{message.sender}->{message.receiver}")
        return message

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        records: list[dict[str, Any]] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 500)):]:
            try: records.append(json.loads(raw))
            except json.JSONDecodeError: continue
        return records
