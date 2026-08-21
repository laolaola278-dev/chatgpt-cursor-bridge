from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.intelligence.common import ensure_project

from .models import TrendDirection, TrendResult


class TrendStore:
    """SQLite store; the HTTP read path never writes to it automatically."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = Lock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_trends (
                trend_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                period TEXT NOT NULL,
                direction TEXT NOT NULL,
                change_rate REAL NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                values_json TEXT NOT NULL,
                confidence_sources_json TEXT NOT NULL,
                confidence_explanation TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_trends_project
              ON intelligence_trends(project_id, created_at DESC);
            """
        )
        self.connection.commit()

    def save(self, trend: TrendResult) -> TrendResult:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_trends
                (trend_id, project_id, metric, period, direction, change_rate, confidence,
                 evidence_json, sample_count, values_json, confidence_sources_json,
                 confidence_explanation, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trend.trend_id, trend.project_id, trend.metric, trend.period,
                    trend.direction.value, trend.change_rate, trend.confidence,
                    json.dumps(trend.evidence), trend.sample_count,
                    json.dumps(trend.values), json.dumps(trend.confidence_sources),
                    trend.confidence_explanation, trend.created_at,
                ),
            )
            self.connection.commit()
        return trend

    def save_many(self, trends: Iterable[TrendResult]) -> list[TrendResult]:
        return [self.save(item) for item in trends]

    def list(self, project_id: str, metric: str | None = None, limit: int = 100) -> list[TrendResult]:
        project = ensure_project(project_id)
        query = "SELECT * FROM intelligence_trends WHERE project_id=?"
        values: list[object] = [project]
        if metric:
            query += " AND metric=?"
            values.append(metric)
        query += " ORDER BY created_at DESC, trend_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 1000)))
        return [self._from_row(row) for row in self.connection.execute(query, values).fetchall()]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TrendResult:
        return TrendResult(
            trend_id=row["trend_id"], project_id=row["project_id"], metric=row["metric"],
            period=row["period"], direction=TrendDirection(row["direction"]),
            change_rate=float(row["change_rate"]), confidence=float(row["confidence"]),
            evidence=json.loads(row["evidence_json"] or "[]"), sample_count=int(row["sample_count"]),
            values=json.loads(row["values_json"] or "[]"),
            confidence_sources=json.loads(row["confidence_sources_json"] or "{}"),
            confidence_explanation=row["confidence_explanation"], created_at=row["created_at"],
        )
