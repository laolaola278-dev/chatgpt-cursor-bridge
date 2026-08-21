"""Phase 28 · Governance Memory tests.

Governance memory must only be written through Governance Proposal ->
ApprovalStore -> Human Approval. These tests verify the proposal shape, the
approval-only apply path, category whitelisting, and project isolation.
"""

from __future__ import annotations

import pytest

from app.intelligence.governance import (
    GOVERNANCE_MEMORY_CATEGORIES,
    GovernanceMemory,
    GovernanceMemoryRecord,
)
from app.security.validator import ValidationFailed

from phase28_helpers import governance_store, memory_record


def test_all_categories_supported():
    assert GOVERNANCE_MEMORY_CATEGORIES == {"finding", "risk", "quality", "policy_violation", "review", "history"}


def test_build_proposal_valid_category():
    proposal = GovernanceMemory().build_proposal(project_id="demo", category="finding", content="new finding")
    assert proposal.project_id == "demo"
    assert proposal.category == "finding"
    assert proposal.content == "new finding"


def test_build_proposal_rejects_unknown_category():
    with pytest.raises(ValueError):
        GovernanceMemory().build_proposal(project_id="demo", category="mutation", content="x")


def test_proposal_payload_roundtrip():
    proposal = GovernanceMemory().build_proposal(
        project_id="demo", category="risk", content="risk finding",
        source="risk_analyzer", evidence=["e1"], confidence=0.6,
    )
    payload = proposal.payload()
    assert payload["category"] == "risk"
    assert payload["evidence"] == ["e1"]
    assert payload["confidence"] == 0.6


def test_proposal_preview_mentions_governance_only():
    proposal = GovernanceMemory().build_proposal(project_id="demo", category="finding", content="finding")
    assert "governance" in proposal.preview()
    assert "no engineering memory mutation" in proposal.preview()


def test_apply_after_approval_creates_record():
    record = GovernanceMemory().apply_after_approval(
        project_id="demo", category="review", content="reviewed",
        approval_request_id="req_1",
    )
    assert record.memory_id.startswith("gm_")
    assert record.approval_request_id == "req_1"
    assert record.created_at


def test_apply_after_approval_requires_valid_category():
    with pytest.raises(ValueError):
        GovernanceMemory().apply_after_approval(project_id="demo", category="auto", content="x")


def test_apply_after_approval_requires_content():
    with pytest.raises(ValidationFailed):
        GovernanceMemory().apply_after_approval(project_id="demo", category="finding", content="")


def test_record_defaults_and_sanitization():
    record = memory_record(content="token sk-live-abcdef123456 leak")
    assert "sk-live" not in record.content
    assert record.memory_id.startswith("gm_")


def test_record_rejects_unknown_category():
    with pytest.raises(ValidationFailed):
        GovernanceMemoryRecord(memory_id="", project_id="demo", category="auto", content="x", source="s", confidence=0.5)


def test_record_rejects_bad_project():
    from app.security.sandbox import SandboxViolation

    with pytest.raises((ValidationFailed, SandboxViolation)):
        memory_record(project="../../x")


def test_save_and_load_memory(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_memory(memory_record())
    records = store.memory("demo")
    assert len(records) == 1
    assert records[0].memory_id == saved.memory_id


def test_memory_project_isolation(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_memory(memory_record(project="demo"))
    store.save_memory(memory_record(project="other"))
    assert len(store.memory("demo")) == 1
    assert len(store.memory("other")) == 1


def test_memory_filter_by_category(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_memory(memory_record(category="finding"))
    store.save_memory(memory_record(category="review", content="review"))
    assert len(store.memory("demo", category="review")) == 1


def test_memory_keeps_approval_request_id(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_memory(memory_record(approval_request_id="req_42"))
    assert saved.approval_request_id == "req_42"


def test_memory_evidence_persists(tmp_path):
    store = governance_store(tmp_path / "g.db")
    item = GovernanceMemoryRecord(
        memory_id="", project_id="demo", category="finding", content="finding",
        source="s", confidence=0.5, evidence=["ev-1"],
    )
    saved = store.save_memory(item)
    loaded = store.memory("demo")[0]
    assert loaded.evidence == ["ev-1"]
    assert saved.evidence == ["ev-1"]


def test_memory_as_dict_keys(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_memory(memory_record())
    data = saved.as_dict()
    assert data["memory_id"] == data["memoryId"]
    assert data["approvalRequestId"] == data["approval_request_id"]
    assert data["readOnly"] is True


def test_memory_clear(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_memory(memory_record())
    store.clear()
    assert store.memory("demo") == []


def test_memory_survives_reopen(tmp_path):
    db = tmp_path / "g.db"
    store = governance_store(db)
    saved = store.save_memory(memory_record())
    reopened = governance_store(db)
    assert len(reopened.memory("demo")) == 1
    assert reopened.memory("demo")[0].memory_id == saved.memory_id


def test_confidence_bounded():
    record = GovernanceMemory().apply_after_approval(
        project_id="demo", category="finding", content="x", confidence=5.0,
    )
    assert record.confidence <= 0.95


def test_no_auto_write_from_engine():
    """Building a proposal must not persist anything."""
    db = ":memory:"
    from app.intelligence.governance import GovernanceStore

    store = GovernanceStore(db)
    GovernanceMemory().build_proposal(project_id="demo", category="finding", content="x")
    assert store.memory("demo") == []


def test_source_attribution_kept():
    record = GovernanceMemory().apply_after_approval(
        project_id="demo", category="policy_violation", content="violation",
        source="rule_engine",
    )
    assert record.source == "rule_engine"


def test_memory_categories_whitelisted_in_storage():
    for category in GOVERNANCE_MEMORY_CATEGORIES:
        record = GovernanceMemory().apply_after_approval(project_id="demo", category=category, content=f"{category} content")
        assert record.category == category
