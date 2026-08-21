from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReplayStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path); self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False); self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS replays (id TEXT PRIMARY KEY, project TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL, steps_json TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS replay_project_idx ON replays(project, created_at);
        """); self.connection.commit()

    def save(self, replay: dict[str, Any]) -> dict[str, Any]:
        self.connection.execute("INSERT OR REPLACE INTO replays VALUES (?,?,?,?,?)", (replay["id"], replay["project"], replay["title"], replay["createdAt"], json.dumps(replay["steps"]))); self.connection.commit(); return replay

    def get(self, replay_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM replays WHERE id=?", (replay_id,)).fetchone()
        if not row: return None
        return {"id": row["id"], "project": row["project"], "title": row["title"], "createdAt": row["created_at"], "steps": json.loads(row["steps_json"]), "readOnly": True}

    def list(self, project: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM replays WHERE project=? ORDER BY created_at DESC LIMIT ?" if project else "SELECT * FROM replays ORDER BY created_at DESC LIMIT ?", (project, limit) if project else (limit,)).fetchall()
        return [{"id": row["id"], "project": row["project"], "title": row["title"], "createdAt": row["created_at"], "steps": json.loads(row["steps_json"]), "readOnly": True} for row in rows]


class EngineeringReplay:
    """Reconstruct a read-only engineering timeline from persisted evidence."""

    def __init__(self, storage: ReplayStorage, audit: Any = None) -> None:
        self.storage = storage; self.audit = audit

    def build(self, project: str, title: str, *, events: list[Any] = [], audit_entries: list[dict[str, Any]] = [], runs: list[Any] = []) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        for event in events:
            record = event.as_dict() if hasattr(event, "as_dict") else (event if isinstance(event, dict) else {})
            steps.append({"stage": str(record.get("eventType", record.get("event_type", "event"))), "detail": str(record.get("source", "")), "timestamp": str(record.get("timestamp", ""))})
        for entry in audit_entries:
            steps.append({"stage": entry.get("action", "audit"), "detail": entry.get("detail") or "", "timestamp": entry.get("timestamp", "")})
        for run in runs:
            record = run.as_dict() if hasattr(run, "as_dict") else (run if isinstance(run, dict) else {})
            steps.append({"stage": "validation_run", "detail": record.get("result", "RECORDED"), "timestamp": record.get("createdAt", "")})
        steps.sort(key=lambda step: step.get("timestamp", ""))
        return self.storage.save({"id": f"replay_{secrets.token_hex(6)}", "project": project, "title": title, "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "steps": steps})
