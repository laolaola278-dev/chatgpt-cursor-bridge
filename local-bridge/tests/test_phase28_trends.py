"""Phase 28 · Intelligence Trend Analysis tests."""

from __future__ import annotations

import pytest

from app.intelligence.governance import GovernanceTrendAnalyzer

from phase28_helpers import (
    benchmark_run,
    decision_outcome,
    effectiveness,
    evaluation,
    record,
    validation_store,
)


def _store(db, *, projects=("demo",)):
    store = validation_store(db)
    return store


def test_single_bucket_is_stable_low_confidence(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(evaluated_at="2026-01-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo")
    assert trend.direction == "stable"
    assert trend.change_rate == 0.0
    assert trend.confidence < 0.4


def test_improving_accuracy_detected(tmp_path):
    store = _store(tmp_path / "i.db")
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"p{index}", result="incorrect", evaluated_at="2026-01-0" + str(index + 1) + "T00:00:00+00:00"))
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"q{index}", result="correct", evaluated_at="2026-02-0" + str(index + 1) + "T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo")
    assert trend.direction == "improving"
    assert trend.change_rate > 0


def test_declining_accuracy_detected(tmp_path):
    store = _store(tmp_path / "i.db")
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"p{index}", result="correct", evaluated_at="2026-01-0" + str(index + 1) + "T00:00:00+00:00"))
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"q{index}", result="incorrect", evaluated_at="2026-02-0" + str(index + 1) + "T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo")
    assert trend.direction == "declining"
    assert trend.change_rate < 0


def test_stable_accuracy_detected(tmp_path):
    store = _store(tmp_path / "i.db")
    # Both buckets end up at exactly 50% accuracy -> stable.
    for index in range(2):
        store.save_evaluation(evaluation(prediction_id=f"p{index}", result="correct", evaluated_at="2026-01-01T00:00:00+00:00"))
        store.save_evaluation(evaluation(prediction_id=f"q{index}", result="incorrect", evaluated_at="2026-01-01T00:00:00+00:00"))
        store.save_evaluation(evaluation(prediction_id=f"r{index}", result="correct", evaluated_at="2026-02-01T00:00:00+00:00"))
        store.save_evaluation(evaluation(prediction_id=f"s{index}", result="incorrect", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo")
    assert trend.direction == "stable"
    assert abs(trend.change_rate) < 0.02


def test_trend_has_evidence_buckets(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo")
    assert trend.evidence
    assert trend.sample_count == 2


def test_effectiveness_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_effectiveness(effectiveness(recommendation_id="r1", user_decision="accepted", success=True, evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_effectiveness(effectiveness(recommendation_id="r2", user_decision="accepted", success=False, evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).effectiveness_trend("demo")
    assert trend.metric == "recommendation_effectiveness"
    assert trend.change_rate < 0


def test_decision_success_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_decision_outcome(decision_outcome(decision_id="d1", status="SUCCESS", evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_decision_outcome(decision_outcome(decision_id="d2", status="FAILURE", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).decision_success_trend("demo")
    assert trend.metric == "decision_success"
    assert trend.change_rate < 0


def test_confidence_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(confidence=0.4, evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", confidence=0.8, evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).confidence_trend("demo")
    assert trend.metric == "confidence"
    assert trend.change_rate > 0


def test_risk_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    from phase28_helpers import governance_store

    gov = governance_store(tmp_path / "g.db")
    gov.save_record(record(risk_score=10.0, created_at="2026-01-01T00:00:00+00:00"))
    gov.save_record(record(source_id="p2", risk_score=80.0, created_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).risk_trend("demo", gov.records("demo"))
    assert trend.metric == "risk_score"
    assert trend.direction == "increasing"


def test_model_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(model_id="m1", result="incorrect", evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", model_id="m1", result="correct", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).model_trend("demo", "m1")
    assert trend.direction == "improving"


def test_agent_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(agent_id="a1", result="correct", evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", agent_id="a1", result="incorrect", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).agent_trend("demo", "a1")
    assert trend.direction == "declining"


def test_agent_filter_in_accuracy_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(agent_id="a1", result="correct", evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", agent_id="a2", result="incorrect", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo", agent_id="a1")
    assert trend.sample_count == 1


def test_model_filter_in_accuracy_trend(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(model_id="m1", result="correct", evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", model_id="m2", result="incorrect", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo", model_id="m2")
    assert trend.sample_count == 1


def test_overall_returns_metric_set(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", evaluated_at="2026-02-01T00:00:00+00:00"))
    trends = GovernanceTrendAnalyzer(store).overall("demo")
    metrics = {trend.metric for trend in trends}
    assert {"accuracy", "recommendation_effectiveness", "decision_success", "confidence"} <= metrics


def test_overall_includes_risk_when_records(tmp_path):
    store = _store(tmp_path / "i.db")
    from phase28_helpers import governance_store

    gov = governance_store(tmp_path / "g.db")
    gov.save_record(record(risk_score=20.0))
    gov.save_record(record(source_id="p2", risk_score=40.0))
    trends = GovernanceTrendAnalyzer(store).overall("demo", governance_records=gov.records("demo"))
    assert any(trend.metric == "risk_score" for trend in trends)


def test_overall_period_normalized(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", evaluated_at="2026-02-01T00:00:00+00:00"))
    trends = GovernanceTrendAnalyzer(store).overall("demo", period="hourly")
    assert all(trend.period == "weekly" for trend in trends)


def test_detected_quality_degradation(tmp_path):
    store = _store(tmp_path / "i.db")
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"p{index}", result="correct", evaluated_at="2026-01-0" + str(index + 1) + "T00:00:00+00:00"))
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"q{index}", result="incorrect", evaluated_at="2026-02-0" + str(index + 1) + "T00:00:00+00:00"))
    analyzer = GovernanceTrendAnalyzer(store)
    trends = analyzer.overall("demo")
    signals = analyzer.detected(trends)
    assert any(signal["signal"] == "quality_degradation" for signal in signals)


def test_detected_regression(tmp_path):
    store = _store(tmp_path / "i.db")
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"p{index}", result="correct", evaluated_at="2026-01-0" + str(index + 1) + "T00:00:00+00:00"))
    for index in range(5):
        store.save_evaluation(evaluation(prediction_id=f"q{index}", result="incorrect", evaluated_at="2026-02-0" + str(index + 1) + "T00:00:00+00:00"))
    analyzer = GovernanceTrendAnalyzer(store)
    trends = analyzer.overall("demo")
    signals = analyzer.detected(trends)
    assert any(signal["signal"] == "regression" for signal in signals)


def test_detected_risk_escalation(tmp_path):
    store = _store(tmp_path / "i.db")
    from phase28_helpers import governance_store

    gov = governance_store(tmp_path / "g.db")
    gov.save_record(record(risk_score=10.0, created_at="2026-01-01T00:00:00+00:00"))
    gov.save_record(record(source_id="p2", risk_score=90.0, created_at="2026-02-01T00:00:00+00:00"))
    analyzer = GovernanceTrendAnalyzer(store)
    trends = analyzer.overall("demo", governance_records=gov.records("demo"))
    signals = analyzer.detected(trends)
    assert any(signal["signal"] == "risk_escalation" for signal in signals)


def test_no_signals_on_healthy_data(tmp_path):
    store = _store(tmp_path / "i.db")
    for index in range(4):
        store.save_evaluation(evaluation(prediction_id=f"p{index}", result="correct", evaluated_at="2026-01-01T00:00:00+00:00"))
        store.save_evaluation(evaluation(prediction_id=f"q{index}", result="correct", evaluated_at="2026-02-01T00:00:00+00:00"))
    analyzer = GovernanceTrendAnalyzer(store)
    trends = analyzer.overall("demo")
    signals = analyzer.detected(trends)
    assert all(signal["signal"] not in ("quality_degradation", "regression", "risk_escalation") for signal in signals)


def test_trend_is_readonly(tmp_path):
    store = _store(tmp_path / "i.db")
    store.save_evaluation(evaluation(evaluated_at="2026-01-01T00:00:00+00:00"))
    store.save_evaluation(evaluation(prediction_id="p2", evaluated_at="2026-02-01T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo")
    data = trend.as_dict()
    assert data["readOnly"] is True
    assert data["metric"] == "accuracy"
    assert data["changeRate"] == data["change_rate"]


def test_trend_confidence_rises_with_samples(tmp_path):
    store = _store(tmp_path / "i.db")
    for day in range(1, 8):
        store.save_evaluation(evaluation(prediction_id=f"p{day}", result="correct", evaluated_at=f"2026-01-{day:02d}T00:00:00+00:00"))
    trend = GovernanceTrendAnalyzer(store).accuracy_trend("demo")
    assert trend.confidence >= 0.3


def test_unknown_metric_trend_not_created(tmp_path):
    store = _store(tmp_path / "i.db")
    with pytest.raises(AttributeError):
        GovernanceTrendAnalyzer(store).nonexistent_trend("demo")
