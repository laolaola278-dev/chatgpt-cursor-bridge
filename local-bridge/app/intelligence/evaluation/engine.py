from __future__ import annotations

from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import ensure_project, tokens
from app.intelligence.outcome import OutcomeStatus, StrategyOutcome
from app.intelligence.risk_prediction.models import PredictionResult
from app.intelligence.recommendation import IntelligenceRecommendation

from .models import PredictionEvaluation, RecommendationEvaluation
from .storage import EvaluationStore


class PredictionEvaluator:
    """Evaluate only against explicit historical outcomes; missing outcomes stay unevaluated."""

    def __init__(self, store: EvaluationStore | None = None) -> None:
        self.store = store

    @staticmethod
    def _actual(prediction: PredictionResult, outcome: StrategyOutcome) -> bool:
        text = " ".join((outcome.expected_outcome, outcome.actual_outcome, outcome.difference)).lower()
        failure_words = ("fail", "error", "regression", "broken", "timeout", "degrad")
        observed_failure = outcome.status is OutcomeStatus.FAILURE or any(word in text for word in failure_words)
        prediction_words = tokens(prediction.prediction_type.value, prediction.prediction)
        if prediction.prediction_type.value == "performance_risk":
            return observed_failure or any(word in text for word in ("slow", "latency", "performance"))
        if prediction.prediction_type.value == "dependency_risk":
            return observed_failure or "depend" in text
        return observed_failure or bool(prediction_words & tokens(text))

    @staticmethod
    def _predicted(prediction: PredictionResult) -> bool:
        return prediction.risk_level.lower() in {"high", "critical"} or prediction.confidence >= 0.7

    def evaluate(self, prediction: PredictionResult, outcome: StrategyOutcome) -> PredictionEvaluation:
        if prediction.project_id != outcome.project_id:
            raise ValueError("Prediction and outcome must belong to the same project")
        predicted = self._predicted(prediction)
        actual = self._actual(prediction, outcome)
        return PredictionEvaluation(
            evaluation_id=f"prediction_eval_{token_hex(8)}", project_id=prediction.project_id,
            prediction_id=prediction.prediction_id, predicted=predicted, actual=actual,
            correct=predicted == actual, confidence=prediction.confidence,
            evaluated_at=outcome.created_at, evidence=list(dict.fromkeys(prediction.evidence + outcome.evidence)),
            outcome_id=outcome.outcome_id,
        )

    def evaluate_many(self, predictions: Iterable[PredictionResult], outcomes: Iterable[StrategyOutcome]) -> list[PredictionEvaluation]:
        outcome_items = list(outcomes)
        results: list[PredictionEvaluation] = []
        for prediction in predictions:
            matching = [item for item in outcome_items if item.project_id == prediction.project_id]
            if matching:
                results.append(self.evaluate(prediction, sorted(matching, key=lambda item: item.created_at)[-1]))
        if self.store is not None:
            self.store.save_many(results)
        return results

    evaluate_prediction = evaluate


class RecommendationOutcomeEvaluator:
    """Evaluate usefulness after a human decision and recorded outcome."""

    def __init__(self, store: EvaluationStore | None = None) -> None:
        self.store = store

    def evaluate(
        self,
        recommendation: IntelligenceRecommendation,
        outcome: StrategyOutcome,
        *,
        decision: str = "human_decision",
    ) -> RecommendationEvaluation:
        if recommendation.project_id != outcome.project_id:
            raise ValueError("Recommendation and outcome must belong to the same project")
        success = outcome.status is OutcomeStatus.SUCCESS
        return RecommendationEvaluation(
            evaluation_id=f"recommendation_eval_{token_hex(8)}", project_id=outcome.project_id,
            recommendation_id=recommendation.recommendation_id, decision=decision,
            expected_result=outcome.expected_outcome, actual_result=outcome.actual_outcome,
            success=success, evidence=list(dict.fromkeys(recommendation.evidence + outcome.evidence)),
            evaluated_at=outcome.created_at, outcome_id=outcome.outcome_id,
        )

    def evaluate_many(self, recommendations: Iterable[IntelligenceRecommendation], outcomes: Iterable[StrategyOutcome], *, decision: str = "human_decision") -> list[RecommendationEvaluation]:
        outcome_items = list(outcomes)
        results: list[RecommendationEvaluation] = []
        for recommendation in recommendations:
            matching = [item for item in outcome_items if item.project_id == recommendation.project_id]
            if matching:
                results.append(self.evaluate(recommendation, sorted(matching, key=lambda item: item.created_at)[-1], decision=decision))
        if self.store is not None:
            self.store.save_many(results)
        return results

    evaluate_recommendation = evaluate


RecommendationEvaluator = RecommendationOutcomeEvaluator
