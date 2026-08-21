from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.intelligence.common import ensure_project

from .models import PredictionResult, PredictionType


class PredictionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_predictions (
                prediction_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                prediction_type TEXT NOT NULL,
                prediction TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                observations_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_predictions_project
              ON intelligence_predictions(project_id, created_at DESC);
            """
        )
        self.connection.commit()

    def save(self, prediction: PredictionResult) -> PredictionResult:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_predictions
                (prediction_id, project_id, prediction_type, prediction, confidence, evidence_json, observations_json, risk_level, created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (prediction.prediction_id, prediction.project_id, prediction.prediction_type.value, prediction.prediction, prediction.confidence, json.dumps(prediction.evidence), json.dumps(prediction.observations), prediction.risk_level, prediction.created_at),
            )
            self.connection.commit()
        return prediction

    def save_many(self, predictions: Iterable[PredictionResult]) -> list[PredictionResult]:
        return [self.save(item) for item in predictions]

    def get(self, prediction_id: str, project_id: str | None = None) -> PredictionResult | None:
        query = "SELECT * FROM intelligence_predictions WHERE prediction_id=?"
        values: list[object] = [prediction_id]
        if project_id is not None:
            query += " AND project_id=?"
            values.append(ensure_project(project_id))
        row = self.connection.execute(query, values).fetchone()
        return self._from_row(row) if row else None

    def list(self, project_id: str, prediction_type: str | None = None, limit: int = 100) -> list[PredictionResult]:
        project = ensure_project(project_id)
        query = "SELECT * FROM intelligence_predictions WHERE project_id=?"
        values: list[object] = [project]
        if prediction_type:
            query += " AND prediction_type=?"
            values.append(prediction_type)
        query += " ORDER BY created_at DESC, prediction_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 1000)))
        return [self._from_row(row) for row in self.connection.execute(query, values).fetchall()]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> PredictionResult:
        return PredictionResult(
            prediction_id=row["prediction_id"], project_id=row["project_id"], prediction_type=PredictionType(row["prediction_type"]),
            prediction=row["prediction"], confidence=float(row["confidence"]), evidence=json.loads(row["evidence_json"] or "[]"), observations=json.loads(row["observations_json"] or "[]"), risk_level=row["risk_level"], created_at=row["created_at"],
        )
