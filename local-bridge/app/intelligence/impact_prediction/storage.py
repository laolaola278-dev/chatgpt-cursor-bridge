from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.intelligence.common import ensure_project

from .models import ImpactPrediction, ImpactRiskLevel


class ImpactPredictionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = Lock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_impact_predictions (
                prediction_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                affected_files_json TEXT NOT NULL,
                affected_modules_json TEXT NOT NULL,
                affected_tests_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                why_risky_json TEXT NOT NULL,
                changed_files_json TEXT NOT NULL,
                changed_symbols_json TEXT NOT NULL,
                dependency_paths_json TEXT NOT NULL,
                confidence_sources_json TEXT NOT NULL,
                confidence_explanation TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_impact_project
              ON intelligence_impact_predictions(project_id, created_at DESC);
            """
        )
        self.connection.commit()

    def save(self, prediction: ImpactPrediction) -> ImpactPrediction:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_impact_predictions
                (prediction_id, project_id, affected_files_json, affected_modules_json,
                 affected_tests_json, risk_level, confidence, evidence_json, why_risky_json,
                 changed_files_json, changed_symbols_json, dependency_paths_json,
                 confidence_sources_json, confidence_explanation, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    prediction.prediction_id, prediction.project_id, json.dumps(prediction.affected_files),
                    json.dumps(prediction.affected_modules), json.dumps(prediction.affected_tests),
                    prediction.risk_level, prediction.confidence, json.dumps(prediction.evidence),
                    json.dumps(prediction.why_risky), json.dumps(prediction.changed_files),
                    json.dumps(prediction.changed_symbols), json.dumps(prediction.dependency_paths),
                    json.dumps(prediction.confidence_sources), prediction.confidence_explanation,
                    prediction.created_at,
                ),
            )
            self.connection.commit()
        return prediction

    def save_many(self, predictions: Iterable[ImpactPrediction]) -> list[ImpactPrediction]:
        return [self.save(item) for item in predictions]

    def list(self, project_id: str, limit: int = 100) -> list[ImpactPrediction]:
        project = ensure_project(project_id)
        rows = self.connection.execute(
            "SELECT * FROM intelligence_impact_predictions WHERE project_id=? ORDER BY created_at DESC, prediction_id DESC LIMIT ?",
            (project, max(1, min(int(limit), 1000))),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ImpactPrediction:
        return ImpactPrediction(
            prediction_id=row["prediction_id"], project_id=row["project_id"],
            affected_files=json.loads(row["affected_files_json"] or "[]"),
            affected_modules=json.loads(row["affected_modules_json"] or "[]"),
            affected_tests=json.loads(row["affected_tests_json"] or "[]"),
            risk_level=ImpactRiskLevel(row["risk_level"]), confidence=float(row["confidence"]),
            evidence=json.loads(row["evidence_json"] or "[]"),
            why_risky=json.loads(row["why_risky_json"] or "[]"),
            changed_files=json.loads(row["changed_files_json"] or "[]"),
            changed_symbols=json.loads(row["changed_symbols_json"] or "[]"),
            dependency_paths=json.loads(row["dependency_paths_json"] or "[]"),
            confidence_sources=json.loads(row["confidence_sources_json"] or "{}"),
            confidence_explanation=row["confidence_explanation"], created_at=row["created_at"],
        )
