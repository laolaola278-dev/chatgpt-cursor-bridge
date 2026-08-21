from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.intelligence.common import ensure_project

from .models import CorrelationResult


class CorrelationStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = Lock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_correlations (
                correlation_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                events_json TEXT NOT NULL,
                relationship TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                event_details_json TEXT NOT NULL,
                interpretation TEXT NOT NULL,
                causation_claim INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_correlations_project
              ON intelligence_correlations(project_id, created_at DESC);
            """
        )
        self.connection.commit()

    def save(self, result: CorrelationResult) -> CorrelationResult:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_correlations
                (correlation_id, project_id, events_json, relationship, confidence,
                 evidence_json, event_details_json, interpretation, causation_claim, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    result.correlation_id, result.project_id, json.dumps(result.events),
                    result.relationship, result.confidence, json.dumps(result.evidence),
                    json.dumps(result.event_details), result.interpretation,
                    int(result.causation_claim), result.created_at,
                ),
            )
            self.connection.commit()
        return result

    def save_many(self, results: Iterable[CorrelationResult]) -> list[CorrelationResult]:
        return [self.save(item) for item in results]

    def list(self, project_id: str, limit: int = 100) -> list[CorrelationResult]:
        project = ensure_project(project_id)
        rows = self.connection.execute(
            "SELECT * FROM intelligence_correlations WHERE project_id=? ORDER BY created_at DESC, correlation_id DESC LIMIT ?",
            (project, max(1, min(int(limit), 1000))),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> CorrelationResult:
        return CorrelationResult(
            correlation_id=row["correlation_id"], project_id=row["project_id"],
            events=json.loads(row["events_json"] or "[]"), relationship=row["relationship"],
            confidence=float(row["confidence"]), evidence=json.loads(row["evidence_json"] or "[]"),
            event_details=json.loads(row["event_details_json"] or "[]"),
            interpretation=row["interpretation"], causation_claim=bool(row["causation_claim"]),
            created_at=row["created_at"],
        )
