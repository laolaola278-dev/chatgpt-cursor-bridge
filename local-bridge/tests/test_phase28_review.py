"""Phase 28 · Governance Review Proposal tests.

Proposals only ever enter the ApprovalStore for human review. There is no
automatic approval path anywhere in the governance layer.
"""

from __future__ import annotations

import pytest

from app.intelligence.governance import (
    GovernanceReviewEngine,
    ReviewProposal,
    ReviewStatus,
)
from app.intelligence.governance.models import REVIEW_STATUSES
from app.security.validator import ValidationFailed

from phase28_helpers import governance_store, proposal


def test_should_propose_on_high_risk():
    assert GovernanceReviewEngine().should_propose(risk_level="HIGH")


def test_should_propose_on_critical_risk():
    assert GovernanceReviewEngine().should_propose(risk_level="CRITICAL")


def test_should_propose_on_high_risk_score():
    assert GovernanceReviewEngine().should_propose(risk_score=70)


def test_should_propose_on_review_required_result():
    assert GovernanceReviewEngine().should_propose(governance_result="REVIEW_REQUIRED")


def test_should_propose_on_blocked_result():
    assert GovernanceReviewEngine().should_propose(governance_result="BLOCKED")


def test_should_propose_on_accuracy_degradation():
    assert GovernanceReviewEngine().should_propose(accuracy_degraded=True)


def test_should_propose_on_regression():
    assert GovernanceReviewEngine().should_propose(regression_detected=True)


def test_should_propose_on_violation():
    assert GovernanceReviewEngine().should_propose(violation_detected=True)


def test_should_propose_on_model_degradation():
    assert GovernanceReviewEngine().should_propose(model_degraded=True)


def test_should_not_propose_on_low_risk():
    assert not GovernanceReviewEngine().should_propose(risk_level="LOW", risk_score=10)


def test_build_proposal_draft():
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="prediction",
        risk_level="HIGH", reason="high risk", recommended_action="review",
    )
    assert draft.risk_level == "HIGH"
    assert draft.preview().startswith("REVIEW")


def test_build_proposal_normalizes_risk_level():
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="prediction",
        risk_level="high", reason="x", recommended_action="y",
    )
    assert draft.risk_level == "HIGH"


def test_build_proposal_defaults_unknown_risk_to_low():
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="prediction",
        risk_level="EXTREME", reason="x", recommended_action="y",
    )
    assert draft.risk_level == "LOW"


def test_build_proposal_payload():
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="prediction",
        risk_level="HIGH", reason="reason", recommended_action="action", evidence=["e1"],
    )
    payload = draft.payload()
    assert payload["source_id"] == "pred-1"
    assert payload["evidence"] == ["e1"]


def test_create_record_defaults_to_proposed():
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="prediction",
        risk_level="HIGH", reason="x", recommended_action="y",
    )
    record = GovernanceReviewEngine().create_record(draft)
    assert record.status == "proposed"
    assert record.proposal_id.startswith("review_")
    assert record.created_at


def test_create_record_keeps_fields():
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="recommendation",
        risk_level="CRITICAL", reason="reason", recommended_action="action", confidence=0.8,
    )
    record = GovernanceReviewEngine().create_record(draft)
    assert record.source_kind == "recommendation"
    assert record.risk_level == "CRITICAL"
    assert record.confidence == 0.8


def test_apply_review_approved():
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="prediction",
        risk_level="HIGH", reason="x", recommended_action="y",
    )
    record = GovernanceReviewEngine().create_record(draft)
    reviewed = GovernanceReviewEngine().apply_review(
        proposal_id=record.proposal_id, project_id="demo", source_id=record.source_id,
        source_kind=record.source_kind, risk_level=record.risk_level, reason=record.reason,
        recommended_action=record.recommended_action, confidence=record.confidence,
        evidence=record.evidence, decision="approved", reviewer_note="looks fine",
        approval_request_id="req_1",
    )
    assert reviewed.status == "approved"
    assert reviewed.reviewer_note == "looks fine"
    assert reviewed.audit_request_id == "req_1"
    assert reviewed.resolved_at


def test_apply_review_rejected():
    record = GovernanceReviewEngine().apply_review(
        proposal_id="review_1", project_id="demo", source_id="pred-1",
        source_kind="prediction", risk_level="HIGH", reason="x",
        recommended_action="y", confidence=0.7, evidence=[], decision="rejected",
    )
    assert record.status == "rejected"


def test_apply_review_rejects_unknown_decision():
    with pytest.raises(ValueError):
        GovernanceReviewEngine().apply_review(
            proposal_id="review_1", project_id="demo", source_id="pred-1",
            source_kind="prediction", risk_level="HIGH", reason="x",
            recommended_action="y", confidence=0.7, evidence=[], decision="maybe",
        )


def test_review_statuses_set():
    assert REVIEW_STATUSES == {"proposed", "approved", "rejected", "executed"}
    assert {item.value for item in ReviewStatus} == REVIEW_STATUSES


def test_proposal_validation_rejects_bad_kind():
    with pytest.raises(ValidationFailed):
        proposal(source_kind="auto_fix")


def test_proposal_validation_rejects_bad_risk():
    with pytest.raises(ValidationFailed):
        proposal(risk_level="EXTREME")


def test_proposal_validation_rejects_bad_status():
    with pytest.raises(ValidationFailed):
        proposal(status="auto_approved")


def test_proposal_sanitizes_reason():
    item = proposal(reason="token=ghp_abcdef123456 leaked")
    assert "ghp_" not in item.reason


def test_save_and_list_proposals(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_proposal(proposal())
    proposals = store.proposals("demo")
    assert len(proposals) == 1
    assert proposals[0].proposal_id == saved.proposal_id


def test_get_proposal(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_proposal(proposal())
    assert store.get_proposal(saved.proposal_id, "demo") is not None
    assert store.get_proposal(saved.proposal_id, "other") is None
    assert store.get_proposal("review_missing", "demo") is None


def test_proposals_project_isolation(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_proposal(proposal(project="demo", source_id="a"))
    store.save_proposal(proposal(project="other", source_id="b"))
    assert [item.source_id for item in store.proposals("demo")] == ["a"]


def test_proposals_filter_by_status(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_proposal(proposal(status="proposed", source_id="a"))
    store.save_proposal(proposal(status="approved", source_id="b"))
    assert [item.source_id for item in store.proposals("demo", status="approved")] == ["b"]


def test_proposals_filter_by_risk_level(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_proposal(proposal(risk_level="HIGH", source_id="a"))
    store.save_proposal(proposal(risk_level="LOW", source_id="b"))
    assert [item.source_id for item in store.proposals("demo", risk_level="LOW")] == ["b"]


def test_proposal_as_dict_keys(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_proposal(proposal())
    data = saved.as_dict()
    assert data["proposal_id"] == data["proposalId"]
    assert data["recommendedAction"] == data["recommended_action"]
    assert data["readOnly"] is True


def test_review_outcome_persists(tmp_path):
    store = governance_store(tmp_path / "g.db")
    saved = store.save_proposal(proposal())
    reviewed = GovernanceReviewEngine().apply_review(
        proposal_id=saved.proposal_id, project_id="demo", source_id=saved.source_id,
        source_kind=saved.source_kind, risk_level=saved.risk_level, reason=saved.reason,
        recommended_action=saved.recommended_action, confidence=saved.confidence,
        evidence=saved.evidence, decision="approved", reviewer_note="ok",
    )
    store.save_proposal(reviewed)
    loaded = store.get_proposal(saved.proposal_id, "demo")
    assert loaded.status == "approved"
    assert loaded.reviewer_note == "ok"


def test_review_proposal_clear(tmp_path):
    store = governance_store(tmp_path / "g.db")
    store.save_proposal(proposal())
    store.clear()
    assert store.proposals("demo") == []


def test_proposal_created_after_approval_only(tmp_path):
    """create_record is a pure builder; nothing is stored until save_proposal."""
    store = governance_store(tmp_path / "g.db")
    draft = GovernanceReviewEngine().build_proposal(
        project_id="demo", source_id="pred-1", source_kind="prediction",
        risk_level="HIGH", reason="x", recommended_action="y",
    )
    GovernanceReviewEngine().create_record(draft)
    assert store.proposals("demo") == []
