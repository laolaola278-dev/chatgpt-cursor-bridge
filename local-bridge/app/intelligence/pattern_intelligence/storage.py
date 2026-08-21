from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.intelligence.common import ensure_project

from .models import PatternResult, PatternType


class PatternStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_patterns (
                pattern_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                similar_history_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_patterns_project
              ON intelligence_patterns(project_id, created_at DESC);
            """
        )
        self.connection.commit()

    def save(self, pattern: PatternResult) -> PatternResult:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_patterns
                (pattern_id, project_id, pattern_type, evidence_json, similar_history_json, confidence, summary, created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (pattern.pattern_id, pattern.project_id, pattern.pattern_type.value, json.dumps(pattern.evidence), json.dumps(pattern.similar_history), pattern.confidence, pattern.summary, pattern.created_at),
            )
            self.connection.commit()
        return pattern

    def save_many(self, patterns: Iterable[PatternResult]) -> list[PatternResult]:
        return [self.save(pattern) for pattern in patterns]

    def get(self, pattern_id: str, project_id: str | None = None) -> PatternResult | None:
        query = "SELECT * FROM intelligence_patterns WHERE pattern_id=?"
        values: list[object] = [pattern_id]
        if project_id is not None:
            query += " AND project_id=?"
            values.append(ensure_project(project_id))
        row = self.connection.execute(query, values).fetchone()
        return self._from_row(row) if row else None

    def list(self, project_id: str, pattern_type: str | None = None, limit: int = 100) -> list[PatternResult]:
        project = ensure_project(project_id)
        query = "SELECT * FROM intelligence_patterns WHERE project_id=?"
        values: list[object] = [project]
        if pattern_type:
            query += " AND pattern_type=?"
            values.append(pattern_type)
        query += " ORDER BY created_at DESC, pattern_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 1000)))
        return [self._from_row(row) for row in self.connection.execute(query, values).fetchall()]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PatternResult:
        return PatternResult(
            pattern_id=row["pattern_id"], project_id=row["project_id"], pattern_type=PatternType(row["pattern_type"]),
            evidence=json.loads(row["evidence_json"] or "[]"), similar_history=json.loads(row["similar_history_json"] or "[]"),
            confidence=float(row["confidence"]), summary=row["summary"], created_at=row["created_at"],
        )
