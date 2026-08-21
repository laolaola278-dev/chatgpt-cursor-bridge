from __future__ import annotations

from app.config import get_settings
from app.intelligence.evidence import DecisionEvidenceManager, EvidenceBundle, EvidenceStore


def test_evidence_bundle_links_observation_pattern_prediction_and_history(bridge):
    store = EvidenceStore(get_settings().intelligence_db_path)
    manager = DecisionEvidenceManager(store)
    bundle = manager.create_bundle(project_id="demo", decision_id="decision_1", observation_ids=["obs_1"], pattern_ids=["pat_1"], prediction_ids=["pred_1"], risk_ids=["risk_1"], strategy_ids=["strategy_1"], recommendation_ids=["rec_1"], historical_evidence=["incident_1"], provenance=["pytest", "audit"], confidence=0.75)
    assert bundle.as_dict()["readOnly"] is True
    assert store.get_for_decision("decision_1", "demo").bundle_id == bundle.bundle_id
    assert store.get(bundle.bundle_id, "other") is None


def test_evidence_bundle_api_requires_approval(bridge):
    body = {"project_id": "demo", "decision_id": "decision_1", "observation_ids": ["obs_1"], "pattern_ids": ["pat_1"], "prediction_ids": ["pred_1"], "provenance": ["test"], "confidence": 0.7}
    pending = bridge.client.post("/intelligence/evidence/bundle", json=body)
    assert pending.status_code == 202
    assert bridge.client.get("/intelligence/evidence", params={"project": "demo"}).json()["evidence"] == []
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    assert bridge.client.get("/intelligence/evidence", params={"project": "demo"}).json()["evidence"]
