from __future__ import annotations

from app.quality.gate11 import QualityGate11Evaluator


def test_quality_gate11_pass_warn_block():
    evaluator = QualityGate11Evaluator()
    assert evaluator.evaluate()["status"] == "WARN"  # no observations is a visible warning
    assert evaluator.evaluate(observation_count=1)["status"] == "PASS"
    assert evaluator.evaluate(observation_integrity=False, observation_count=1)["status"] == "BLOCK"


def test_quality_gate11_has_all_intelligence_checks():
    report = QualityGate11Evaluator().evaluate(observation_count=2, pattern_count=1, prediction_count=1, prediction_confidence=0.75, recommendation_count=1, decision_count=1, outcome_count=1, knowledge_count=1)
    assert report["readOnly"] is True
    assert set(report["checks"]) == {"observationIntegrity", "patternEvidence", "predictionConfidence", "recommendationTraceability", "decisionEvidence", "outcomeCompleteness", "knowledgeProvenance"}


def test_quality_api_is_project_scoped_and_read_only(bridge):
    response = bridge.client.get("/intelligence/quality", params={"project": "demo"})
    assert response.status_code == 200 and response.json()["readOnly"] is True
    assert response.json()["project"] == "demo"
    assert bridge.client.get("/quality/v11/demo").json()["readOnly"] is True
