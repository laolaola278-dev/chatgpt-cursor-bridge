"""Phase 28 · Governance Core tests: record lifecycle, validation, isolation."""

from __future__ import annotations

import pytest

from app.intelligence.governance import GovernanceStore
from app.intelligence.governance.models import (
    GovernanceKind,
    GovernanceRecord,
    GovernanceResult,
    RiskLevel,
)
from app.security.sandbox import SandboxViolation
from app.security.validator import ValidationFailed

from phase28_helpers import governance_store, record


def test_governance_record_defaults_id_and_timestamp():
    item = record()
    assert item.governance_id.startswith("gov_")
    assert item.created_at


def test_governance_record_rejects_unknown_source_kind():
    with pytest.raises(ValidationFailed):
        record(source_kind="unknown_kind")


def test_governance_record_rejects_unknown_risk_level():
    with pytest.raises(ValidationFailed):
        record(risk_level="EXTREME")


def test_governance_record_rejects_unknown_result():
    with pytest.raises(ValidationFailed):
        record(governance_result="MAYBE")


def test_governance_record_rejects_empty_source_id():
    with pytest.raises(ValidationFailed):
        record(source_id="")


def test_governance_record_rejects_bad_project():
    with pytest.raises((ValidationFailed, SandboxViolation)):
        record(project="../../etc")


def test_governance_record_sanitizes_evidence():
    item = record(evidence=["ok", "sk-live-abcdef123456"])
    assert "sk-live" not in " ".join(item.evidence)
    assert "ok" in item.evidence


def test_governance_record_bounds_confidence():
    item = record(confidence=5.0)
    assert item.confidence <= 0.95
    item2 = record(confidence=-1.0)
    assert item2.confidence >= 0.0


def test_governance_record_bounds_risk_score():
    assert record(risk_score=500.0).risk_score == 100.0
    assert record(risk_score=-5.0).risk_score == 0.0


def test_governance_record_as_dict_has_both_key_styles():
    data = record().as_dict()
    assert data["governance_id"] == data["governanceId"]
    assert data["risk_level"] == data["riskLevel"]
    assert data["readOnly"] is True


def test_all_governance_kinds_are_supported():
    for kind in GovernanceKind:
        item = record(source_kind=kind.value)
        assert item.source_kind == kind.value


def test_save_and_load_record_roundtrip(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_record(record())
    loaded = store.get_record(saved.governance_id, "demo")
    assert loaded is not None
    assert loaded.as_dict() == saved.as_dict()


def test_get_record_missing_returns_none(tmp_path):
    store = governance_store(tmp_path / "g.db")
    assert store.get_record("gov_nope", "demo") is None


def test_records_project_isolation(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_record(record(project="demo", source_id="p1"))
    store.save_record(record(project="other", source_id="p2"))
    only_demo = store.records("demo")
    assert len(only_demo) == 1
    assert only_demo[0].source_id == "p1"


def test_records_filter_by_source_kind(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_record(record(source_kind="prediction", source_id="a"))
    store.save_record(record(source_kind="decision", source_id="b"))
    assert len(store.records("demo", source_kind="decision")) == 1


def test_records_filter_by_risk_level(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_record(record(risk_level="LOW", source_id="a"))
    store.save_record(record(risk_level="HIGH", source_id="b"))
    assert [item.source_id for item in store.records("demo", risk_level="HIGH")] == ["b"]


def test_records_filter_by_governance_result(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_record(record(governance_result="PASS", source_id="a"))
    store.save_record(record(governance_result="REVIEW_REQUIRED", source_id="b"))
    assert [item.source_id for item in store.records("demo", governance_result="REVIEW_REQUIRED")] == ["b"]


def test_records_filter_by_agent(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_record(record(agent_id="agent-1", source_id="a"))
    store.save_record(record(agent_id="agent-2", source_id="b"))
    assert [item.source_id for item in store.records("demo", agent_id="agent-2")] == ["b"]


def test_records_filter_by_model(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_record(record(model_id="router", source_id="a"))
    store.save_record(record(model_id="local", source_id="b"))
    assert [item.source_id for item in store.records("demo", model_id="local")] == ["b"]


def test_records_ordered_newest_first(tmp_path):
    store = governance_store(tmp_path / "g.db")
    first = record(source_id="a")
    second = record(source_id="b")
    store.save_record(first)
    store.save_record(second)
    records = store.records("demo")
    assert [item.source_id for item in records] == ["b", "a"]


def test_records_respects_limit(tmp_path):
    store = governance_store(tmp_path / "g.db")
    for index in range(5):
        store.save_record(record(source_id=f"p{index}"))
    assert len(store.records("demo", limit=2)) == 2


def test_record_keeps_audit_request_id(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_record(record(audit_request_id="req_123"))
    assert saved.audit_request_id == "req_123"


def test_record_evidence_persists(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_record(record(evidence=["ev-1", "ev-2"]))
    loaded = store.get_record(saved.governance_id, "demo")
    assert loaded.evidence == ["ev-1", "ev-2"]


def test_record_policy_ids_persist(tmp_path):
    store = governance_store(tmp_path / "g.db")
    item = record()
    item = GovernanceRecord(**{**item.__dict__, "policy_ids": ["p_confidence_threshold"]})
    saved = store.save_record(item)
    assert saved.policy_ids == ["p_confidence_threshold"]


def test_clear_removes_all_records(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_record(record())
    store.clear()
    assert store.records("demo") == []


def test_store_survives_reopen(tmp_path):
    db = tmp_path / "g.db"
    store = governance_store(db)
    saved = store.save_record(record())
    reopened = governance_store(db)
    assert reopened.get_record(saved.governance_id, "demo") is not None


def test_record_source_kind_normalized_to_lowercase():
    assert record(source_kind="PREDICTION").source_kind == "prediction"


def test_record_risk_level_normalized_to_uppercase():
    assert record(risk_level="high").risk_level == "HIGH"


def test_governance_results_statuses():
    expected = {"PASS", "WARNING", "REVIEW_REQUIRED", "BLOCKED"}
    assert {item.value for item in GovernanceResult} == expected


def test_risk_levels_order():
    assert [item.value for item in RiskLevel] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_governance_id_is_unique_per_record(tmp_path):
    store = governance_store(tmp_path / "g.db")
    a = store.save_record(record(source_id="a"))
    b = store.save_record(record(source_id="b"))
    assert a.governance_id != b.governance_id


def test_reason_is_sanitized():
    item = record(reason="token sk-live-abcdef123456 leaked")
    assert "sk-live" not in item.reason


def test_evaluation_result_kept_verbatim():
    assert record(evaluation_result="incorrect").evaluation_result == "incorrect"


def test_record_as_dict_has_evidence_list():
    data = record(evidence=["e1"]).as_dict()
    assert data["evidence"] == ["e1"]
