from __future__ import annotations

import pytest

from app.intelligence.evaluation import EvaluationStore, PredictionEvaluator, RecommendationOutcomeEvaluator
from app.intelligence.observation import ObservationStore, ObservationType
from app.intelligence.outcome import OutcomeStore, OutcomeStatus
from app.intelligence.recommendation import IntelligenceRecommendation
from app.intelligence.risk_prediction import PredictionResult, PredictionType


@pytest.mark.parametrize("status", [OutcomeStatus.SUCCESS.value, OutcomeStatus.PARTIAL_SUCCESS.value, OutcomeStatus.FAILURE.value, OutcomeStatus.CANCELLED.value] * 8)
def test_prediction_evaluation_matrix_uses_explicit_outcome(status, tmp_path):
    db = tmp_path / f"eval-{status}.db"
    outcome = OutcomeStore(db).record(project_id="demo", strategy_id="strategy", status=status, expected_outcome="stable build", actual_outcome="build failed" if status == "FAILURE" else "stable build", evidence=["obs-1"])
    prediction = PredictionResult("pred-1", "demo", PredictionType.REGRESSION_RISK, "regression risk", 0.8, ["obs-1"], ["obs-1"], "high")
    result = PredictionEvaluator().evaluate(prediction, outcome)
    assert result.project_id == "demo" and result.evidence
    assert result.correct == (result.predicted == result.actual)


def test_prediction_evaluations_only_count_real_outcomes(tmp_path):
    prediction = PredictionResult("pred-1", "demo", PredictionType.TEST_FAILURE_RISK, "test failure risk", 0.8, ["obs-1"], ["obs-1"], "high")
    assert PredictionEvaluator().evaluate_many([prediction], []) == []


def test_evaluation_metrics_are_not_fabricated(tmp_path):
    db = tmp_path / "metrics.db"
    store = EvaluationStore(db)
    assert store.metrics("demo").predictions == 0
    prediction = PredictionResult("pred-1", "demo", PredictionType.TEST_FAILURE_RISK, "test failure risk", 0.8, ["obs-1"], ["obs-1"], "high")
    outcome = OutcomeStore(db).record(project_id="demo", strategy_id="s", status="FAILURE", expected_outcome="pass", actual_outcome="failed", evidence=["obs-1"])
    evaluation = PredictionEvaluator(store).evaluate_many([prediction], [outcome])
    assert evaluation and store.metrics("demo").predictions == 1
    assert store.metrics("other").predictions == 0


def test_recommendation_outcome_evaluation(tmp_path):
    db = tmp_path / "recommendation.db"
    recommendation = IntelligenceRecommendation("rec-1", "demo", "pred-1", "Review tests", "history", ["obs-1"], 0.7, "high")
    outcome = OutcomeStore(db).record(project_id="demo", strategy_id="s", status="SUCCESS", expected_outcome="stable tests", actual_outcome="stable tests", evidence=["obs-1"])
    result = RecommendationOutcomeEvaluator().evaluate(recommendation, outcome, decision="human_selected")
    assert result.success is True and result.recommendation_id == "rec-1"


def test_evaluation_rejects_cross_project_links(tmp_path):
    db = tmp_path / "cross.db"
    prediction = PredictionResult("pred-1", "demo", PredictionType.TEST_FAILURE_RISK, "risk", 0.7, ["obs"], ["obs"], "high")
    outcome = OutcomeStore(db).record(project_id="other", strategy_id="s", status="SUCCESS", expected_outcome="x", actual_outcome="x")
    with pytest.raises(ValueError):
        PredictionEvaluator().evaluate(prediction, outcome)


def test_evaluation_store_keeps_prediction_and_recommendation_records(tmp_path):
    db = tmp_path / "store.db"
    store = EvaluationStore(db)
    prediction = PredictionResult("pred-1", "demo", PredictionType.TEST_FAILURE_RISK, "risk", 0.7, ["obs"], ["obs"], "high")
    outcome = OutcomeStore(db).record(project_id="demo", strategy_id="s", status="SUCCESS", expected_outcome="x", actual_outcome="x", evidence=["obs"])
    store.save_prediction(PredictionEvaluator().evaluate(prediction, outcome))
    recommendation = IntelligenceRecommendation("rec-1", "demo", "pred-1", "review", "reason", ["obs"], 0.7, "high")
    store.save_recommendation(RecommendationOutcomeEvaluator().evaluate(recommendation, outcome))
    assert len(store.list("demo")) == 2
