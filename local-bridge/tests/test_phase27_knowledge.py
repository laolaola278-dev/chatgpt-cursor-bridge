"""Phase 27 · Knowledge Improvement Engine tests.

Verifies that improvement proposals are validated before approval, only
persist after human approval, and never mutate memory or knowledge directly.
"""

from __future__ import annotations

import pytest

from app.intelligence.validation import KnowledgeImprovementEngine
from app.intelligence.validation.models import KnowledgeImprovementStatus
from app.security.validator import ValidationFailed
from tests.phase27_helpers import store


class TestProposal:
    def test_build_proposal_validates(self) -> None:
        proposal = KnowledgeImprovementEngine().build_proposal(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="predictions", content="parser changes correlate with regressions",
            evidence=["obs-1"], confidence=0.7,
        )
        assert proposal.project_id == "demo"
        assert proposal.category == "predictions"
        assert proposal.preview()

    def test_preview_mentions_evaluation_and_confidence(self) -> None:
        proposal = KnowledgeImprovementEngine().build_proposal(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="trends", content="build failures are increasing",
            evidence=["obs-1"], confidence=0.6,
        )
        preview = proposal.preview()
        assert "eval-1" in preview
        assert "0.6" in preview

    def test_rejects_unknown_category(self) -> None:
        with pytest.raises(ValidationFailed):
            KnowledgeImprovementEngine().build_proposal(
                project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
                category="memes", content="x", confidence=0.5,
            )

    def test_supports_all_knowledge_categories(self) -> None:
        for category in ("patterns", "predictions", "strategies", "outcomes", "trends", "correlations", "recommendations", "evaluations"):
            proposal = KnowledgeImprovementEngine().build_proposal(
                project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
                category=category, content="x", confidence=0.5,
            )
            assert proposal.category == category

    def test_scrubs_secrets_from_content(self) -> None:
        proposal = KnowledgeImprovementEngine().build_proposal(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="predictions", content="token ghp-1234567890abcdefgh",
            evidence=["obs-1"], confidence=0.5,
        )
        assert "ghp-1234567890abcdefgh" not in proposal.content
        assert "[REDACTED]" in proposal.content

    def test_bounds_confidence(self) -> None:
        proposal = KnowledgeImprovementEngine().build_proposal(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="predictions", content="x", confidence=99.0,
        )
        assert proposal.confidence <= 0.95

    def test_payload_contains_structured_fields(self) -> None:
        proposal = KnowledgeImprovementEngine().build_proposal(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="predictions", content="x", evidence=["obs-1"], confidence=0.6,
        )
        payload = proposal.payload()
        assert payload["evaluation_id"] == "eval-1"
        assert payload["evidence"] == ["obs-1"]
        assert "reason" not in payload

    def test_requires_content(self) -> None:
        with pytest.raises(ValidationFailed):
            KnowledgeImprovementEngine().build_proposal(
                project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
                category="predictions", content="", confidence=0.5,
            )

    def test_requires_evaluation_id(self) -> None:
        with pytest.raises(ValidationFailed):
            KnowledgeImprovementEngine().build_proposal(
                project_id="demo", evaluation_id="", prediction_id="pred-1",
                category="predictions", content="x", confidence=0.5,
            )


class TestApplyAfterApproval:
    def test_apply_marks_validated(self) -> None:
        record = KnowledgeImprovementEngine().apply_after_approval(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="correlations", content="cache + regression correlation",
            source="evaluation_feedback", evidence=["obs-1"], confidence=0.7,
            approval_request_id="req-123",
        )
        assert record.status == KnowledgeImprovementStatus.VALIDATED.value
        assert record.validated_at
        assert record.approval_request_id == "req-123"
        assert record.improvement_id.startswith("improve_")

    def test_apply_does_not_touch_memory(self, bridge) -> None:
        # There is no automatic memory write: after approval the improvement
        # record exists, but intelligence knowledge stays empty.
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "predictions", "content": "parser changes are risky",
                "evidence": ["obs-1"], "confidence": 0.7,
            },
        )
        assert pending.status_code == 202
        assert bridge.client.get("/intelligence/knowledge?project=demo").json()["knowledge"] == []
        bridge.approve(pending.json()["requestId"])
        # Improvement recorded...
        improvements = bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["improvements"]
        assert any(item["status"] == "validated" for item in improvements)
        # ...but intelligence knowledge remains untouched without a separate
        # approved knowledge proposal.
        assert bridge.client.get("/intelligence/knowledge?project=demo").json()["knowledge"] == []

    def test_apply_roundtrip_via_store(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        record = KnowledgeImprovementEngine().apply_after_approval(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="trends", content="build trend", source="evaluation_feedback",
            evidence=["obs-1"], confidence=0.6, approval_request_id="req-1",
        )
        db.save_improvement(record)
        loaded = db.improvements("demo")[0]
        assert loaded.improvement_id == record.improvement_id
        assert loaded.status == "validated"

    def test_list_improvements_is_project_scoped(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_improvement(KnowledgeImprovementEngine().apply_after_approval(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="patterns", content="x", source="evaluation_feedback",
            evidence=[], confidence=0.5, approval_request_id="req-1",
        ))
        db.save_improvement(KnowledgeImprovementEngine().apply_after_approval(
            project_id="alpha", evaluation_id="eval-2", prediction_id="pred-2",
            category="patterns", content="y", source="evaluation_feedback",
            evidence=[], confidence=0.5, approval_request_id="req-2",
        ))
        assert len(KnowledgeImprovementEngine.list_improvements(db.improvements("demo"), "demo")) == 1
        assert len(KnowledgeImprovementEngine.list_improvements(db.improvements("alpha"), "alpha")) == 1

    def test_list_filters_by_status(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_improvement(KnowledgeImprovementEngine().apply_after_approval(
            project_id="demo", evaluation_id="eval-1", prediction_id="pred-1",
            category="outcomes", content="x", source="evaluation_feedback",
            evidence=[], confidence=0.5, approval_request_id="req-1",
        ))
        assert len(KnowledgeImprovementEngine.list_improvements(db.improvements("demo"), "demo", status="validated")) == 1
        assert len(KnowledgeImprovementEngine.list_improvements(db.improvements("demo"), "demo", status="proposed")) == 0


class TestImprovementApi:
    def test_post_requires_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "recommendations", "content": "standardize retry logic",
                "evidence": ["obs-1"], "confidence": 0.6,
            },
        )
        assert pending.status_code == 202
        assert pending.json()["action"] == "intelligence_knowledge_improvement"
        assert pending.json()["status"] == "pending"
        # Before approval the improvement is visible as a pending proposal.
        improvements = bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["improvements"]
        assert any(item["status"] == "pending" for item in improvements)

    def test_approval_marks_validated(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "patterns", "content": "cache invalidation failures recur",
                "evidence": ["obs-1"], "confidence": 0.7,
            },
        )
        bridge.approve(pending.json()["requestId"])
        improvements = bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["improvements"]
        assert any(item["status"] == "validated" for item in improvements)

    def test_rejection_keeps_record_out_of_validated(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "patterns", "content": "noise pattern", "evidence": [],
                "confidence": 0.1,
            },
        )
        bridge.client.post("/permission/reject", json={"request_id": pending.json()["requestId"], "reason": "not useful"})
        improvements = bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["improvements"]
        assert any(item["status"] == "rejected" for item in improvements)
        assert not any(item["status"] == "validated" for item in improvements)

    def test_post_rejects_unknown_category(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "memes", "content": "x", "evidence": [], "confidence": 0.5,
            },
        )
        assert response.status_code == 400

    def test_get_is_project_scoped(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "strategies", "content": "plan", "evidence": [], "confidence": 0.5,
            },
        )
        bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["improvements"]) == 1
        assert bridge.client.get("/intelligence/knowledge/improvements?project=other").json()["improvements"] == []

    def test_get_filters_by_status(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "predictions", "content": "risk", "evidence": [], "confidence": 0.5,
            },
        )
        bridge.approve(pending.json()["requestId"])
        validated = bridge.client.get("/intelligence/knowledge/improvements?project=demo&status=validated").json()["improvements"]
        assert len(validated) == 1
        assert bridge.client.get("/intelligence/knowledge/improvements?project=demo&status=proposed").json()["improvements"] == []

    def test_endpoint_is_read_only(self, bridge) -> None:
        assert bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["readOnly"] is True

    def test_no_auto_knowledge_write_endpoint(self, bridge) -> None:
        # There is no endpoint that lets an improvement write knowledge without
        # a separate approved knowledge proposal.
        assert bridge.client.get("/intelligence/knowledge/improvements/apply?project=demo").status_code == 404
