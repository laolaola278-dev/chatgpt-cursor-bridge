from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.intelligence.common import ensure_project

from .models import DependencyRisk, DependencyRiskLevel


class DependencyRiskStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = Lock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_dependency_risks (
                risk_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                dependency TEXT NOT NULL,
                risk TEXT NOT NULL,
                reason TEXT NOT NULL,
                historical_evidence_json TEXT NOT NULL,
                affected_components_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                change_type TEXT NOT NULL,
                old_version TEXT NOT NULL,
                new_version TEXT NOT NULL,
                transitive INTEGER NOT NULL,
                concentration REAL,
                coupling REAL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_dependency_project
              ON intelligence_dependency_risks(project_id, created_at DESC);
            """
        )
        self.connection.commit()

    def save(self, result: DependencyRisk) -> DependencyRisk:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_dependency_risks
                (risk_id, project_id, dependency, risk, reason, historical_evidence_json,
                 affected_components_json, confidence, change_type, old_version, new_version,
                 transitive, concentration, coupling, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    result.risk_id, result.project_id, result.dependency, result.risk,
                    result.reason, json.dumps(result.historical_evidence),
                    json.dumps(result.affected_components), result.confidence, result.change_type,
                    result.old_version, result.new_version, int(result.transitive),
                    result.concentration, result.coupling, result.created_at,
                ),
            )
            self.connection.commit()
        return result

    def save_many(self, results: Iterable[DependencyRisk]) -> list[DependencyRisk]:
        return [self.save(item) for item in results]

    def list(self, project_id: str, limit: int = 100) -> list[DependencyRisk]:
        project = ensure_project(project_id)
        rows = self.connection.execute(
            "SELECT * FROM intelligence_dependency_risks WHERE project_id=? ORDER BY created_at DESC, risk_id DESC LIMIT ?",
            (project, max(1, min(int(limit), 1000))),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DependencyRisk:
        return DependencyRisk(
            risk_id=row["risk_id"], project_id=row["project_id"], dependency=row["dependency"],
            risk=DependencyRiskLevel(row["risk"]), reason=row["reason"],
            historical_evidence=json.loads(row["historical_evidence_json"] or "[]"),
            affected_components=json.loads(row["affected_components_json"] or "[]"),
            confidence=float(row["confidence"]), change_type=row["change_type"],
            old_version=row["old_version"], new_version=row["new_version"],
            transitive=bool(row["transitive"]), concentration=row["concentration"],
            coupling=row["coupling"], created_at=row["created_at"],
        )
