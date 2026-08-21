from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now


@dataclass(frozen=True)
class PredictionEvaluation:
    evaluation_id: str
    project_id: str
    prediction_id: str
    predicted: bool
    actual: bool
    correct: bool
    confidence: float
    evaluated_at: str
    evidence: list[str] = field(default_factory=list)
    outcome_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "prediction_id", sanitize_text(self.prediction_id, limit=200))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "evaluated_at", self.evaluated_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id, "evaluationId": self.evaluation_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "prediction_id": self.prediction_id, "predictionId": self.prediction_id,
            "predicted": self.predicted, "actual": self.actual, "correct": self.correct,
            "confidence": self.confidence, "evaluated_at": self.evaluated_at,
            "evaluatedAt": self.evaluated_at, "evidence": self.evidence,
            "outcome_id": self.outcome_id, "outcomeId": self.outcome_id,
            "readOnly": True,
        }


@dataclass(frozen=True)
class RecommendationEvaluation:
    evaluation_id: str
    project_id: str
    recommendation_id: str
    decision: str
    expected_result: str
    actual_result: str
    success: bool
    evidence: list[str] = field(default_factory=list)
    evaluated_at: str = ""
    outcome_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "recommendation_id", sanitize_text(self.recommendation_id, limit=200))
        object.__setattr__(self, "decision", sanitize_text(self.decision, limit=2000))
        object.__setattr__(self, "expected_result", sanitize_text(self.expected_result, limit=4000))
        object.__setattr__(self, "actual_result", sanitize_text(self.actual_result, limit=4000))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "evaluated_at", self.evaluated_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id, "evaluationId": self.evaluation_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "recommendation_id": self.recommendation_id, "recommendationId": self.recommendation_id,
            "decision": self.decision, "expected_result": self.expected_result,
            "expectedResult": self.expected_result, "actual_result": self.actual_result,
            "actualResult": self.actual_result, "success": self.success,
            "evidence": self.evidence, "evaluated_at": self.evaluated_at,
            "evaluatedAt": self.evaluated_at, "outcome_id": self.outcome_id,
            "outcomeId": self.outcome_id, "readOnly": True,
        }


@dataclass(frozen=True)
class EvaluationMetrics:
    project_id: str
    predictions: int
    correct: int
    incorrect: int
    accuracy: float
    precision: float
    recall: float
    false_positive_rate: float
    false_negative_rate: float
    recommendation_count: int = 0
    recommendation_successes: int = 0
    recommendation_success_rate: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        for name in ("accuracy", "precision", "recall", "false_positive_rate", "false_negative_rate", "recommendation_success_rate"):
            object.__setattr__(self, name, round(max(0.0, min(1.0, float(getattr(self, name)))), 3))

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "projectId": self.project_id,
            "predictions": self.predictions, "correct": self.correct,
            "incorrect": self.incorrect, "accuracy": self.accuracy,
            "precision": self.precision, "recall": self.recall,
            "false_positive_rate": self.false_positive_rate,
            "falsePositiveRate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "falseNegativeRate": self.false_negative_rate,
            "recommendation_count": self.recommendation_count,
            "recommendationCount": self.recommendation_count,
            "recommendation_successes": self.recommendation_successes,
            "recommendationSuccesses": self.recommendation_successes,
            "recommendation_success_rate": self.recommendation_success_rate,
            "recommendationSuccessRate": self.recommendation_success_rate,
            "readOnly": True,
        }
