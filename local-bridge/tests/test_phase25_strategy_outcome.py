from __future__ import annotations

from app.config import get_settings
from app.intelligence.outcome import OutcomeStatus, OutcomeStore, StrategyOutcomeTracker


def test_outcome_lifecycle_records_expected_actual_difference(bridge):
    store = OutcomeStore(get_settings().intelligence_db_path)
    tracker = StrategyOutcomeTracker(store)
    outcome = tracker.record(project_id="demo", strategy_id="strategy_1", decision_id="decision_1", status="SUCCESS", expected_outcome="lower latency", actual_outcome="latency improved", difference="within expected range", evidence=["test_1"], source="test_result", confidence=0.8)
    assert outcome.status is OutcomeStatus.SUCCESS
    restored = store.get(outcome.outcome_id, "demo")
    assert restored is not None and restored.actual_outcome == "latency improved"
    assert store.list("other") == []


def test_outcome_api_is_approval_gated(bridge):
    body = {"project_id": "demo", "strategy_id": "strategy_1", "status": "PARTIAL_SUCCESS", "expected_outcome": "stable build", "actual_outcome": "one warning", "difference": "warning remained", "evidence": ["build_1"], "source": "build_result", "confidence": 0.6}
    pending = bridge.client.post("/intelligence/outcomes/record", json=body)
    assert pending.status_code == 202
    assert bridge.client.get("/intelligence/outcomes", params={"project": "demo"}).json()["outcomes"] == []
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    assert bridge.client.get("/intelligence/outcomes", params={"project": "demo"}).json()["outcomes"][0]["status"] == "PARTIAL_SUCCESS"
