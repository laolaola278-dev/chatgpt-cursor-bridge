"""Phase 28 · Intelligence Risk Analyzer tests."""

from __future__ import annotations

import pytest

from app.intelligence.governance import IntelligenceRiskAnalyzer, risk_level_for_score
from app.intelligence.governance.models import RiskLevel

analyze = IntelligenceRiskAnalyzer().analyze


def test_low_risk_default():
    result = analyze(project="demo", source_kind="prediction", source_id="p1")
    assert result.finding.risk_level == RiskLevel.LOW.value
    assert result.finding.risk_score < 30


def test_low_confidence_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", confidence=0.1)
    assert "low_confidence" in result.factors


def test_incorrect_prediction_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", evaluation_result="incorrect")
    assert "incorrect_prediction" in result.factors


def test_partial_prediction_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", evaluation_result="partial")
    assert "partial_prediction" in result.factors


def test_high_risk_source_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", source_risk_level="HIGH")
    assert "high_risk_source" in result.factors


def test_high_risk_source_by_score():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", source_risk_score=75)
    assert "high_risk_source" in result.factors


def test_declining_accuracy_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", prior_accuracy=0.4)
    assert "declining_accuracy" in result.factors


def test_high_accuracy_no_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", prior_accuracy=0.9)
    assert "declining_accuracy" not in result.factors


def test_similar_high_risk_history_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", similar_history=["HIGH", "MEDIUM"])
    assert "similar_high_risk_history" in result.factors


def test_low_risk_history_no_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", similar_history=["LOW"])
    assert "similar_high_risk_history" not in result.factors


def test_model_unreliable_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", model_reliability=0.3)
    assert "model_unreliable" in result.factors


def test_reliable_model_no_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", model_reliability=0.9)
    assert "model_unreliable" not in result.factors


def test_regression_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", regression=True)
    assert "regression_observed" in result.factors


def test_sensitive_context_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", context="uses api key AKIA1234567890ABCD")
    assert "sensitive_context" in result.factors


def test_clean_context_no_factor():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", context="parser refactor")
    assert "sensitive_context" not in result.factors


def test_combined_factors_raise_risk_level():
    result = analyze(
        project="demo", source_kind="prediction", source_id="p1",
        confidence=0.2, evaluation_result="incorrect", source_risk_level="HIGH",
    )
    assert result.finding.risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)


def test_risk_score_monotonic_in_factors():
    base = analyze(project="demo", source_kind="prediction", source_id="p1")
    stacked = analyze(
        project="demo", source_kind="prediction", source_id="p1",
        evaluation_result="incorrect", source_risk_level="HIGH", confidence=0.2,
    )
    assert stacked.finding.risk_score > base.finding.risk_score


def test_risk_score_bounded():
    result = analyze(
        project="demo", source_kind="prediction", source_id="p1",
        confidence=0.1, evaluation_result="incorrect", source_risk_level="CRITICAL",
        source_risk_score=95, prior_accuracy=0.1, model_reliability=0.1,
        regression=True, context="api key", similar_history=["CRITICAL"],
    )
    assert 0.0 <= result.finding.risk_score <= 100.0


def test_confidence_bounded():
    result = analyze(
        project="demo", source_kind="prediction", source_id="p1",
        confidence=0.1, evaluation_result="incorrect", source_risk_level="CRITICAL",
    )
    assert 0.0 <= result.finding.confidence <= 0.95


def test_confidence_increases_with_factors():
    low = analyze(project="demo", source_kind="prediction", source_id="p1")
    high = analyze(
        project="demo", source_kind="prediction", source_id="p1",
        confidence=0.2, evaluation_result="incorrect",
    )
    assert high.finding.confidence > low.finding.confidence


def test_deterministic_same_input_same_output():
    kwargs = dict(project="demo", source_kind="prediction", source_id="p1", confidence=0.2, evaluation_result="incorrect")
    first = analyze(**kwargs).finding.as_dict()
    second = analyze(**kwargs).finding.as_dict()
    for key in ("createdAt", "created_at", "riskId", "risk_id"):
        first.pop(key, None)
        second.pop(key, None)
    assert first == second


def test_reason_reflects_factors():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", evaluation_result="incorrect")
    assert "incorrect_prediction" in result.finding.reason


def test_no_factors_reason():
    result = analyze(project="demo", source_kind="prediction", source_id="p1")
    assert "No material risk factors" in result.finding.reason


def test_finding_keeps_source_identity():
    result = analyze(project="demo", source_kind="recommendation", source_id="rec-9", agent_id="agent-x", model_id="model-y")
    assert result.finding.source_kind == "recommendation"
    assert result.finding.source_id == "rec-9"
    assert result.finding.agent_id == "agent-x"
    assert result.finding.model_id == "model-y"


def test_finding_risk_factors_persisted(tmp_path):
    from phase28_helpers import governance_store

    store = governance_store(tmp_path / "g.db")
    result = analyze(project="demo", source_kind="prediction", source_id="p1", confidence=0.2)
    saved = store.save_risk(result.finding)
    assert "low_confidence" in saved.risk_factors


def test_risk_list_orders_by_score_desc(tmp_path):
    from phase28_helpers import governance_store, risk_finding

    store = governance_store(tmp_path / "g.db")
    store.save_risk(risk_finding(risk_score=90, source_id="a"))
    store.save_risk(risk_finding(risk_score=30, source_id="b"))
    store.save_risk(risk_finding(risk_score=60, source_id="c"))
    assert [item.source_id for item in store.risks("demo")] == ["a", "c", "b"]


def test_risk_list_project_isolation(tmp_path):
    from phase28_helpers import governance_store, risk_finding

    store = governance_store(tmp_path / "g.db")
    store.save_risk(risk_finding(project="demo", source_id="a"))
    store.save_risk(risk_finding(project="other", source_id="b"))
    assert [item.source_id for item in store.risks("demo")] == ["a"]


def test_risk_list_filters_by_level(tmp_path):
    from phase28_helpers import governance_store, risk_finding

    store = governance_store(tmp_path / "g.db")
    store.save_risk(risk_finding(risk_level="HIGH", source_id="a"))
    store.save_risk(risk_finding(risk_level="LOW", source_id="b"))
    assert [item.source_id for item in store.risks("demo", risk_level="HIGH")] == ["a"]


def test_risk_list_filters_by_agent(tmp_path):
    from phase28_helpers import governance_store, risk_finding

    store = governance_store(tmp_path / "g.db")
    store.save_risk(risk_finding(agent_id="agent-1", source_id="a"))
    store.save_risk(risk_finding(agent_id="agent-2", source_id="b"))
    assert [item.source_id for item in store.risks("demo", agent_id="agent-2")] == ["b"]


def test_risk_level_for_score_boundaries():
    assert risk_level_for_score(85) == "CRITICAL"
    assert risk_level_for_score(80) == "CRITICAL"
    assert risk_level_for_score(79) == "HIGH"
    assert risk_level_for_score(55) == "HIGH"
    assert risk_level_for_score(54) == "MEDIUM"
    assert risk_level_for_score(30) == "MEDIUM"
    assert risk_level_for_score(29) == "LOW"
    assert risk_level_for_score(0) == "LOW"


@pytest.mark.parametrize("confidence", [0.1, 0.25, 0.29])
def test_low_confidence_detected(confidence):
    result = analyze(project="demo", source_kind="prediction", source_id="p1", confidence=confidence)
    assert "low_confidence" in result.factors


@pytest.mark.parametrize("confidence", [0.3, 0.5, 0.95])
def test_acceptable_confidence_not_detected(confidence):
    result = analyze(project="demo", source_kind="prediction", source_id="p1", confidence=confidence)
    assert "low_confidence" not in result.factors


@pytest.mark.parametrize("evaluation_result", ["incorrect", "partial"])
def test_non_correct_results_add_factor(evaluation_result):
    result = analyze(project="demo", source_kind="prediction", source_id="p1", evaluation_result=evaluation_result)
    assert len(result.factors) >= 1


@pytest.mark.parametrize("source_risk_level", ["HIGH", "CRITICAL"])
def test_high_risk_sources_flagged(source_risk_level):
    result = analyze(project="demo", source_kind="prediction", source_id="p1", source_risk_level=source_risk_level)
    assert "high_risk_source" in result.factors


def test_analysis_is_readonly():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", evaluation_result="incorrect")
    assert result.as_dict()["readOnly"] is True
    assert "finding" in result.as_dict()


def test_risk_similar_cases_deduplicated():
    result = analyze(project="demo", source_kind="prediction", source_id="p1", similar_history=["HIGH", "HIGH"])
    assert result.finding.similar_cases == ["HIGH"]
