from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ExecutionLoop, LoopStatus


class ExecutionLoopStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS execution_loops (
                id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                workflow_id TEXT,
                task_ids_json TEXT NOT NULL,
                proposal_id TEXT,
                result_id TEXT,
                approval_id TEXT,
                status TEXT NOT NULL,
                verification_json TEXT NOT NULL DEFAULT '{}',
                quality_json TEXT NOT NULL DEFAULT '{}',
                rollback_json TEXT NOT NULL DEFAULT '{}',
                memory_proposal_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                history_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS execution_loop_project ON execution_loops(project, updated_at);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def save(self, loop: ExecutionLoop) -> None:
        self.connection.execute(
            """
            INSERT INTO execution_loops (
                id, project, plan_id, workflow_id, task_ids_json, proposal_id, result_id,
                approval_id, status, verification_json, quality_json, rollback_json,
                memory_proposal_id, created_at, updated_at, history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              project=excluded.project,
              plan_id=excluded.plan_id,
              workflow_id=excluded.workflow_id,
              task_ids_json=excluded.task_ids_json,
              proposal_id=excluded.proposal_id,
              result_id=excluded.result_id,
              approval_id=excluded.approval_id,
              status=excluded.status,
              verification_json=excluded.verification_json,
              quality_json=excluded.quality_json,
              rollback_json=excluded.rollback_json,
              memory_proposal_id=excluded.memory_proposal_id,
              updated_at=excluded.updated_at,
              history_json=excluded.history_json
            """,
            (
                loop.id,
                loop.project,
                loop.plan_id,
                loop.workflow_id,
                json.dumps(loop.task_ids, ensure_ascii=False),
                loop.proposal_id,
                loop.result_id,
                loop.approval_id,
                loop.status.value,
                json.dumps(loop.verification, ensure_ascii=False),
                json.dumps(loop.quality, ensure_ascii=False),
                json.dumps(loop.rollback, ensure_ascii=False),
                loop.memory_proposal_id,
                loop.created_at,
                loop.updated_at,
                json.dumps(loop.history, ensure_ascii=False),
            ),
        )
        self.connection.commit()

    @staticmethod
    def _loop(row: sqlite3.Row) -> ExecutionLoop:
        return ExecutionLoop(
            id=row["id"],
            project=row["project"],
            plan_id=row["plan_id"],
            workflow_id=row["workflow_id"],
            task_ids=json.loads(row["task_ids_json"]),
            proposal_id=row["proposal_id"],
            result_id=row["result_id"],
            approval_id=row["approval_id"],
            status=LoopStatus(row["status"]),
            verification=json.loads(row["verification_json"] or "{}"),
            quality=json.loads(row["quality_json"] or "{}"),
            rollback=json.loads(row["rollback_json"] or "{}"),
            memory_proposal_id=row["memory_proposal_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            history=json.loads(row["history_json"] or "[]"),
        )

    def get(self, loop_id: str) -> ExecutionLoop | None:
        row = self.connection.execute("SELECT * FROM execution_loops WHERE id=?", (loop_id,)).fetchone()
        return self._loop(row) if row else None

    def list_loops(self, project: str | None = None, limit: int = 200) -> list[ExecutionLoop]:
        if project:
            rows = self.connection.execute("SELECT * FROM execution_loops WHERE project=? ORDER BY updated_at DESC LIMIT ?", (project, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM execution_loops ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._loop(row) for row in rows]

    def find_by_task(self, task_id: str) -> ExecutionLoop | None:
        for loop in self.list_loops(limit=1000):
            if task_id in loop.task_ids:
                return loop
        return None
