from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.intelligence.common import ensure_project

from .models import EvaluationMetrics, PredictionEvaluation, RecommendationEvaluation


class EvaluationStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = Lock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_prediction_evaluations (
                evaluation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, prediction_id TEXT NOT NULL,
                predicted INTEGER NOT NULL, actual INTEGER NOT NULL, correct INTEGER NOT NULL,
                confidence REAL NOT NULL, evaluated_at TEXT NOT NULL, evidence_json TEXT NOT NULL,
                outcome_id TEXT
            );
            CREATE TABLE IF NOT EXISTS intelligence_recommendation_evaluations (
                evaluation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, recommendation_id TEXT NOT NULL,
                decision TEXT NOT NULL, expected_result TEXT NOT NULL, actual_result TEXT NOT NULL,
                success INTEGER NOT NULL, evidence_json TEXT NOT NULL, evaluated_at TEXT NOT NULL,
                outcome_id TEXT
            );
            CREATE INDEX IF NOT EXISTS intelligence_prediction_eval_project
              ON intelligence_prediction_evaluations(project_id, evaluated_at DESC);
            CREATE INDEX IF NOT EXISTS intelligence_recommendation_eval_project
              ON intelligence_recommendation_evaluations(project_id, evaluated_at DESC);
            """
        )
        self.connection.commit()

    def save_prediction(self, evaluation: PredictionEvaluation) -> PredictionEvaluation:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_prediction_evaluations
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    evaluation.evaluation_id, evaluation.project_id, evaluation.prediction_id,
                    int(evaluation.predicted), int(evaluation.actual), int(evaluation.correct),
                    evaluation.confidence, evaluation.evaluated_at, json.dumps(evaluation.evidence),
                    evaluation.outcome_id,
                ),
            )
            self.connection.commit()
        return evaluation

    def save_recommendation(self, evaluation: RecommendationEvaluation) -> RecommendationEvaluation:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_recommendation_evaluations
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    evaluation.evaluation_id, evaluation.project_id, evaluation.recommendation_id,
                    evaluation.decision, evaluation.expected_result, evaluation.actual_result,
                    int(evaluation.success), json.dumps(evaluation.evidence), evaluation.evaluated_at,
                    evaluation.outcome_id,
                ),
            )
            self.connection.commit()
        return evaluation

    def save_many(self, evaluations: Iterable[PredictionEvaluation | RecommendationEvaluation]) -> list[Any]:
        result: list[Any] = []
        for evaluation in evaluations:
            result.append(self.save_prediction(evaluation) if isinstance(evaluation, PredictionEvaluation) else self.save_recommendation(evaluation))
        return result

    def predictions(self, project_id: str, limit: int = 1000) -> list[PredictionEvaluation]:
        project = ensure_project(project_id)
        rows = self.connection.execute("SELECT * FROM intelligence_prediction_evaluations WHERE project_id=? ORDER BY evaluated_at DESC LIMIT ?", (project, max(1, min(int(limit), 2000)))).fetchall()
        return [PredictionEvaluation(row["evaluation_id"], row["project_id"], row["prediction_id"], bool(row["predicted"]), bool(row["actual"]), bool(row["correct"]), float(row["confidence"]), row["evaluated_at"], json.loads(row["evidence_json"] or "[]"), row["outcome_id"]) for row in rows]

    def recommendations(self, project_id: str, limit: int = 1000) -> list[RecommendationEvaluation]:
        project = ensure_project(project_id)
        rows = self.connection.execute("SELECT * FROM intelligence_recommendation_evaluations WHERE project_id=? ORDER BY evaluated_at DESC LIMIT ?", (project, max(1, min(int(limit), 2000)))).fetchall()
        return [RecommendationEvaluation(row["evaluation_id"], row["project_id"], row["recommendation_id"], row["decision"], row["expected_result"], row["actual_result"], bool(row["success"]), json.loads(row["evidence_json"] or "[]"), row["evaluated_at"], row["outcome_id"]) for row in rows]

    def list(self, project_id: str, limit: int = 1000) -> list[dict[str, object]]:
        return [item.as_dict() for item in self.predictions(project_id, limit)] + [item.as_dict() for item in self.recommendations(project_id, limit)]

    def metrics(self, project_id: str, limit: int = 1000) -> EvaluationMetrics:
        predictions = self.predictions(project_id, limit)
        recommendations = self.recommendations(project_id, limit)
        tp = sum(1 for item in predictions if item.predicted and item.actual)
        tn = sum(1 for item in predictions if not item.predicted and not item.actual)
        fp = sum(1 for item in predictions if item.predicted and not item.actual)
        fn = sum(1 for item in predictions if not item.predicted and item.actual)
        total = len(predictions)
        rec_total = len(recommendations)
        rec_successes = sum(1 for item in recommendations if item.success)
        return EvaluationMetrics(
            project_id=ensure_project(project_id), predictions=total,
            correct=sum(1 for item in predictions if item.correct), incorrect=sum(1 for item in predictions if not item.correct),
            accuracy=(tp + tn) / total if total else 0.0,
            precision=tp / (tp + fp) if tp + fp else 0.0,
            recall=tp / (tp + fn) if tp + fn else 0.0,
            false_positive_rate=fp / (fp + tn) if fp + tn else 0.0,
            false_negative_rate=fn / (fn + tp) if fn + tp else 0.0,
            recommendation_count=rec_total, recommendation_successes=rec_successes,
            recommendation_success_rate=rec_successes / rec_total if rec_total else 0.0,
        )
