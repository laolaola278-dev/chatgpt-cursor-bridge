from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import (
    ExecutionProposal,
    ExecutionProposalStatus,
    ExecutionResult,
    ExecutionTask,
    ExecutionTaskStatus,
)


class ExecutionStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS execution_tasks (
                id TEXT PRIMARY KEY,
                workflow_id TEXT,
                plan_id TEXT,
                project TEXT NOT NULL,
                title TEXT NOT NULL,
                task_type TEXT NOT NULL,
                files_json TEXT NOT NULL,
                dependencies_json TEXT NOT NULL,
                risk TEXT NOT NULL,
                risk_score INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                verification_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS execution_proposals (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES execution_tasks(id) ON DELETE CASCADE,
                project TEXT NOT NULL,
                workflow_id TEXT,
                operations_json TEXT NOT NULL,
                estimated_changes INTEGER NOT NULL,
                risk_score INTEGER NOT NULL,
                status TEXT NOT NULL,
                approval_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_results (
                id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL REFERENCES execution_proposals(id) ON DELETE CASCADE,
                task_id TEXT NOT NULL,
                project TEXT NOT NULL,
                files_changed_json TEXT NOT NULL,
                diff_summary_json TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                errors_json TEXT NOT NULL,
                verification_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS execution_task_project ON execution_tasks(project, updated_at);
            CREATE INDEX IF NOT EXISTS execution_proposal_task ON execution_proposals(task_id, status);
            CREATE INDEX IF NOT EXISTS execution_result_proposal ON execution_results(proposal_id, created_at);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ExecutionStorage":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- tasks ----------------------------------------------------------

    def save_task(self, task: ExecutionTask) -> None:
        self.connection.execute(
            """
            INSERT INTO execution_tasks (
                id, workflow_id, plan_id, project, title, task_type, files_json,
                dependencies_json, risk, risk_score, status, created_at, updated_at, verification_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              workflow_id=excluded.workflow_id,
              plan_id=excluded.plan_id,
              project=excluded.project,
              title=excluded.title,
              task_type=excluded.task_type,
              files_json=excluded.files_json,
              dependencies_json=excluded.dependencies_json,
              risk=excluded.risk,
              risk_score=excluded.risk_score,
              status=excluded.status,
              updated_at=excluded.updated_at,
              verification_json=excluded.verification_json
            """,
            (
                task.id,
                task.workflow_id,
                task.plan_id,
                task.project,
                task.title,
                task.task_type,
                json.dumps(task.files, ensure_ascii=False),
                json.dumps(task.dependencies, ensure_ascii=False),
                task.risk,
                task.risk_score,
                task.status.value,
                task.created_at,
                task.updated_at,
                json.dumps(task.verification, ensure_ascii=False),
            ),
        )
        self.connection.commit()

    @staticmethod
    def _task(row: sqlite3.Row) -> ExecutionTask:
        return ExecutionTask(
            id=row["id"],
            workflow_id=row["workflow_id"],
            plan_id=row["plan_id"],
            project=row["project"],
            title=row["title"],
            task_type=row["task_type"],
            files=json.loads(row["files_json"]),
            dependencies=json.loads(row["dependencies_json"]),
            risk=row["risk"],
            risk_score=int(row["risk_score"]),
            status=ExecutionTaskStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            verification=json.loads(row["verification_json"] or "{}"),
        )

    def get_task(self, task_id: str) -> ExecutionTask | None:
        row = self.connection.execute("SELECT * FROM execution_tasks WHERE id=?", (task_id,)).fetchone()
        return self._task(row) if row else None

    def list_tasks(self, project: str | None = None, status: str | None = None, limit: int = 200) -> list[ExecutionTask]:
        clauses, values = [], []
        if project:
            clauses.append("project=?"); values.append(project)
        if status:
            clauses.append("status=?"); values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(f"SELECT * FROM execution_tasks {where} ORDER BY updated_at DESC LIMIT ?", (*values, limit)).fetchall()
        return [self._task(row) for row in rows]

    # -- proposals ------------------------------------------------------

    def save_proposal(self, proposal: ExecutionProposal) -> None:
        self.connection.execute(
            """
            INSERT INTO execution_proposals (
                id, task_id, project, workflow_id, operations_json, estimated_changes,
                risk_score, status, approval_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.id,
                proposal.task_id,
                proposal.project,
                proposal.workflow_id,
                json.dumps([operation.as_dict() for operation in proposal.operations], ensure_ascii=False),
                proposal.estimated_changes,
                proposal.risk_score,
                proposal.status.value,
                proposal.approval_id,
                proposal.created_at,
            ),
        )
        self.connection.commit()

    def update_proposal(self, proposal: ExecutionProposal) -> None:
        self.connection.execute(
            "UPDATE execution_proposals SET status=?, approval_id=? WHERE id=?",
            (proposal.status.value, proposal.approval_id, proposal.id),
        )
        self.connection.commit()

    @staticmethod
    def _proposal(row: sqlite3.Row) -> ExecutionProposal:
        from .models import ExecutionOperation

        operations = [ExecutionOperation(item["type"], item["path"], item.get("reason", "")) for item in json.loads(row["operations_json"])]
        return ExecutionProposal(
            id=row["id"],
            task_id=row["task_id"],
            project=row["project"],
            workflow_id=row["workflow_id"],
            operations=operations,
            estimated_changes=int(row["estimated_changes"]),
            risk_score=int(row["risk_score"]),
            status=ExecutionProposalStatus(row["status"]),
            approval_id=row["approval_id"],
            created_at=row["created_at"],
        )

    def get_proposal(self, proposal_id: str) -> ExecutionProposal | None:
        row = self.connection.execute("SELECT * FROM execution_proposals WHERE id=?", (proposal_id,)).fetchone()
        return self._proposal(row) if row else None

    def list_proposals(self, project: str | None = None, status: str | None = None, limit: int = 200) -> list[ExecutionProposal]:
        clauses, values = [], []
        if project:
            clauses.append("project=?"); values.append(project)
        if status:
            clauses.append("status=?"); values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(f"SELECT * FROM execution_proposals {where} ORDER BY created_at DESC LIMIT ?", (*values, limit)).fetchall()
        return [self._proposal(row) for row in rows]

    # -- results --------------------------------------------------------

    def save_result(self, result: ExecutionResult) -> None:
        self.connection.execute(
            """
            INSERT INTO execution_results (
                id, proposal_id, task_id, project, files_changed_json, diff_summary_json,
                duration_ms, errors_json, verification_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.id,
                result.proposal_id,
                result.task_id,
                result.project,
                json.dumps(result.files_changed, ensure_ascii=False),
                json.dumps(result.diff_summary, ensure_ascii=False),
                result.duration_ms,
                json.dumps(result.errors, ensure_ascii=False),
                json.dumps(result.verification, ensure_ascii=False),
                result.created_at,
            ),
        )
        self.connection.commit()

    @staticmethod
    def _result(row: sqlite3.Row) -> ExecutionResult:
        return ExecutionResult(
            id=row["id"],
            proposal_id=row["proposal_id"],
            task_id=row["task_id"],
            project=row["project"],
            files_changed=json.loads(row["files_changed_json"]),
            diff_summary=json.loads(row["diff_summary_json"]),
            duration_ms=int(row["duration_ms"]),
            errors=json.loads(row["errors_json"]),
            verification=json.loads(row["verification_json"]),
            created_at=row["created_at"],
        )

    def get_result(self, result_id: str) -> ExecutionResult | None:
        row = self.connection.execute("SELECT * FROM execution_results WHERE id=?", (result_id,)).fetchone()
        return self._result(row) if row else None

    def get_result_for_proposal(self, proposal_id: str) -> ExecutionResult | None:
        row = self.connection.execute("SELECT * FROM execution_results WHERE proposal_id=? ORDER BY created_at DESC LIMIT 1", (proposal_id,)).fetchone()
        return self._result(row) if row else None

    def list_results(self, project: str | None = None, limit: int = 200) -> list[ExecutionResult]:
        clauses, values = [], []
        if project:
            clauses.append("project=?"); values.append(project)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(f"SELECT * FROM execution_results {where} ORDER BY created_at DESC LIMIT ?", (*values, limit)).fetchall()
        return [self._result(row) for row in rows]
