"""JSONL audit logging.

Every bridge operation (success, failure or denial) is appended to
``<LOG_PATH>/audit.jsonl``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import get_settings


class AuditLogger:
    def __init__(self, log_file: Path, *, max_bytes: int = 5 * 1024 * 1024) -> None:
        self._log_file = log_file
        self._max_bytes = max_bytes
        self._lock = Lock()
        self._log_file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def archive_dir(self) -> Path:
        return self._log_file.parent / "archive"

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if not self._log_file.exists() or self._log_file.stat().st_size + incoming_bytes <= self._max_bytes:
            return
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.archive_dir / f"{self._log_file.stem}-{stamp}{self._log_file.suffix}"
        counter = 1
        while target.exists():
            target = self.archive_dir / f"{self._log_file.stem}-{stamp}-{counter}{self._log_file.suffix}"
            counter += 1
        self._log_file.replace(target)

    @property
    def log_file(self) -> Path:
        return self._log_file

    def record(
        self,
        *,
        action: str,
        path: str,
        permission: str,
        approved: bool,
        result: str,
        detail: str | None = None,
        request_id: str | None = None,
        audit_id: str | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "action": action,
            "path": path,
            "permission": permission,
            "approved": approved,
            "result": result,
        }
        if detail:
            entry["detail"] = detail[:2000]
        if request_id:
            entry["requestId"] = request_id
        if audit_id:
            entry["auditId"] = audit_id

        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self._rotate_if_needed(len((line + "\n").encode("utf-8")))
            with self._log_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return entry

    def read_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self._log_file.exists():
            return []
        with self._log_file.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        entries: list[dict[str, Any]] = []
        for raw in lines[-limit:]:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:  # pragma: no cover - corrupted line guard
                continue
        return entries


@lru_cache(maxsize=1)
def get_audit_logger() -> AuditLogger:
    settings = get_settings()
    return AuditLogger(settings.audit_log_file, max_bytes=settings.audit_max_bytes)


def reset_audit_logger() -> None:
    get_audit_logger.cache_clear()
