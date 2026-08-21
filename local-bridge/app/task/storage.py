"""SQLite storage for the persistent task queue."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock

from app.security.validator import ResourceNotFound

from .models import Task, TaskStatus


class TaskStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, stage_id TEXT NOT NULL,
            agent_id TEXT NOT NULL, priority INTEGER NOT NULL, status TEXT NOT NULL,
            context_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        self.connection.commit()

    @staticmethod
    def from_row(row: sqlite3.Row) -> Task:
        return Task(row["id"], row["workflow_id"], row["stage_id"], row["agent_id"], row["priority"], TaskStatus(row["status"]), json.loads(row["context_json"]), row["created_at"], row["updated_at"])

    def save(self, task: Task) -> Task:
        with self._lock:
            self.connection.execute("""INSERT INTO tasks (id, workflow_id, stage_id, agent_id, priority, status, context_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET workflow_id=excluded.workflow_id, stage_id=excluded.stage_id,
                agent_id=excluded.agent_id, priority=excluded.priority, status=excluded.status,
                context_json=excluded.context_json, updated_at=excluded.updated_at""",
                (task.id, task.workflow_id, task.stage_id, task.agent_id, task.priority, task.status.value, json.dumps(task.context, ensure_ascii=False), task.created_at, task.updated_at))
            self.connection.commit()
        return task

    def get(self, task_id: str) -> Task:
        with self._lock:
            row = self.connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ResourceNotFound(f"Task '{task_id}' was not found")
        return self.from_row(row)

    def list(self, *, status: TaskStatus | None = None, limit: int = 100) -> list[Task]:
        with self._lock:
            if status is None:
                rows = self.connection.execute("SELECT * FROM tasks ORDER BY priority DESC, created_at LIMIT ?", (limit,)).fetchall()
            else:
                rows = self.connection.execute("SELECT * FROM tasks WHERE status=? ORDER BY priority DESC, created_at LIMIT ?", (status.value, limit)).fetchall()
        return [self.from_row(row) for row in rows]
