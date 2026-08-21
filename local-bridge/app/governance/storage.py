"""SQLite persistence for governance telemetry.

Stores health snapshots, drift snapshots, debt items and policy events. All
records are derived analysis or approval-gated metadata; nothing here can
modify project source or memory.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import DebtItem, DebtStatus, PolicyEvaluation


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GovernanceStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS health_reports (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, report_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drift_reports (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, report_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS debt_items (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, category TEXT NOT NULL, severity TEXT NOT NULL,
                source TEXT NOT NULL, affected_json TEXT NOT NULL, estimated_cost INTEGER NOT NULL,
                risk TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policy_events (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, policy TEXT NOT NULL, result TEXT NOT NULL,
                severity TEXT NOT NULL, message TEXT NOT NULL, context_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS health_project_idx ON health_reports(project);
            CREATE INDEX IF NOT EXISTS drift_project_idx ON drift_reports(project);
            CREATE INDEX IF NOT EXISTS debt_project_idx ON debt_items(project);
            CREATE INDEX IF NOT EXISTS policy_project_idx ON policy_events(project);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    # -- health snapshots --------------------------------------------------

    def record_health(self, project: str, report: dict[str, Any]) -> str:
        snapshot_id = f"health_{project}_{report.get('createdAt', '')[:19].replace(':', '')}"
        self.connection.execute(
            "INSERT OR REPLACE INTO health_reports(id,project,report_json,created_at) VALUES (?,?,?,?)",
            (snapshot_id, project, json.dumps(report, ensure_ascii=False), report.get("createdAt", "")),
        )
        self.connection.commit()
        return snapshot_id

    def list_health(self, project: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT report_json FROM health_reports WHERE project=? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [json.loads(row["report_json"]) for row in rows]

    # -- drift snapshots ---------------------------------------------------

    def record_drift(self, project: str, report: dict[str, Any]) -> str:
        snapshot_id = f"drift_{project}_{report.get('createdAt', '')[:19].replace(':', '')}"
        self.connection.execute(
            "INSERT OR REPLACE INTO drift_reports(id,project,report_json,created_at) VALUES (?,?,?,?)",
            (snapshot_id, project, json.dumps(report, ensure_ascii=False), report.get("createdAt", "")),
        )
        self.connection.commit()
        return snapshot_id

    def list_drift(self, project: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT report_json FROM drift_reports WHERE project=? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [json.loads(row["report_json"]) for row in rows]

    # -- debt items --------------------------------------------------------

    def save_debt(self, item: DebtItem) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO debt_items(id,project,category,severity,source,affected_json,estimated_cost,risk,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                item.id, item.project, item.category, item.severity, item.source,
                json.dumps(item.affected_components), item.estimated_cost, item.risk,
                item.status.value, item.created_at, item.updated_at,
            ),
        )
        self.connection.commit()

    def get_debt(self, debt_id: str) -> DebtItem | None:
        row = self.connection.execute("SELECT * FROM debt_items WHERE id=?", (debt_id,)).fetchone()
        return self._debt(row) if row else None

    def list_debt(self, project: str | None = None, status: str | None = None, limit: int = 200) -> list[DebtItem]:
        query = "SELECT * FROM debt_items"
        clauses: list[str] = []
        args: list[str] = []
        if project:
            clauses.append("project=?")
            args.append(project)
        if status:
            clauses.append("status=?")
            args.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        args.append(str(limit))
        rows = self.connection.execute(query, args).fetchall()
        return [self._debt(row) for row in rows]

    def update_debt_status(self, debt_id: str, status: DebtStatus) -> DebtItem:
        item = self.get_debt(debt_id)
        if item is None:
            raise KeyError(debt_id)
        item.status = status
        item.updated_at = _now()
        self.save_debt(item)
        return item

    @staticmethod
    def _debt(row: sqlite3.Row) -> DebtItem:
        return DebtItem(
            row["id"], row["project"], row["category"], row["severity"], row["source"],
            json.loads(row["affected_json"]), int(row["estimated_cost"]), row["risk"],
            DebtStatus(row["status"]), row["created_at"], row["updated_at"],
        )

    # -- policy events -----------------------------------------------------

    def record_policy_event(self, project: str, evaluation: PolicyEvaluation) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO policy_events(id,project,policy,result,severity,message,context_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                f"policy_{evaluation.created_at[:19].replace(':', '')}_{project[:16]}",
                project, evaluation.policy, evaluation.result, evaluation.severity,
                evaluation.message, json.dumps(evaluation.context, ensure_ascii=False), evaluation.created_at,
            ),
        )
        self.connection.commit()

    def list_policy_events(self, project: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM policy_events"
        args: list[str] = []
        if project:
            query += " WHERE project=?"
            args.append(project)
        query += " ORDER BY created_at DESC LIMIT ?"
        args.append(str(limit))
        rows = self.connection.execute(query, args).fetchall()
        return [
            {
                "project": row["project"], "policy": row["policy"], "result": row["result"],
                "severity": row["severity"], "message": row["message"],
                "context": json.loads(row["context_json"]), "createdAt": row["created_at"],
                "readOnly": True,
            }
            for row in rows
        ]
