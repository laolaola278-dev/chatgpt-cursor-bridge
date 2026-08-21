"""Phase 27 · Intelligence Evaluation Core tests."""

from __future__ import annotations

import pytest

from app.intelligence.validation import ValidationStore
from app.intelligence.validation.models import (
    EVALUATION_KINDS,
    EvaluationKind,
    EvaluationRecord,
    EvaluationResult,
)
from app.security.validator import ValidationFailed
from tests.phase27_helpers import evaluation, store


# ---------------------------------------------------------------------------
# EvaluationRecord validation
# ---------------------------------------------------------------------------

class TestEvaluationRecord:
    @pytest.mark.parametrize("kind", sorted(EVALUATION_KINDS))
    def test_supports_every_evaluation_kind(self, kind: str) -> None:
        assert evaluation(kind=kind).evaluation_kind == kind

    @pytest.mark.parametrize("result", sorted({item.value for item in EvaluationResult}))
    def test_supports_every_evaluation_result(self, result: str) -> None:
        assert evaluation(result=result).evaluation_result == result

    def test_rejects_unknown_kind(self) -> None:
        with pytest.raises(ValidationFailed):
            evaluation(kind="causal_claim")

    def test_rejects_unknown_result(self) -> None:
        with pytest.raises(ValidationFailed):
            evaluation(result="maybe")

    def test_requires_prediction_id(self) -> None:
        with pytest.raises(ValidationFailed):
            evaluation(prediction_id="")

    def test_bounds_confidence(self) -> None:
        assert evaluation(confidence=5.0).confidence == 0.95
        assert evaluation(confidence=-1.0).confidence == 0.0
        assert evaluation(confidence=0.7).confidence == 0.7

    def test_scrubs_secrets_from_context(self) -> None:
        record = EvaluationRecord(
            evaluation_id="", project_id="demo", prediction_id="pred-1",
            evaluation_kind="prediction", input_context="api key sk-1234567890abcdef",
            prediction_result="claim", expected_outcome="expected", actual_outcome="actual",
            evaluation_result="correct", confidence=0.5,
        )
        assert "sk-1234567890abcdef" not in record.input_context
        assert "[REDACTED]" in record.input_context

    def test_scrubs_secrets_from_agent_model_metadata(self) -> None:
        record = evaluation(agent_id="agent with token=abc123", model_id="model with secret=xyz")
        assert "token=abc123" not in record.agent_id
        assert "secret=xyz" not in record.model_id
        assert "[REDACTED]" in record.model_id

    def test_hides_absolute_paths(self) -> None:
        record = EvaluationRecord(
            evaluation_id="", project_id="demo", prediction_id="pred-1",
            evaluation_kind="prediction", input_context="failed at /home/user/projects/src/x.py",
            prediction_result="claim", expected_outcome="expected", actual_outcome="actual",
            evaluation_result="correct", confidence=0.5,
        )
        assert "/home/user/projects" not in record.input_context
        assert "<internal-path>" in record.input_context

    def test_correct_property_matches_result(self) -> None:
        assert evaluation(result="correct").correct is True
        assert evaluation(result="incorrect").correct is False
        assert evaluation(result="partial").correct is False
        assert evaluation(result="unknown").correct is False

    def test_counted_property(self) -> None:
        assert evaluation(result="correct").counted is True
        assert evaluation(result="incorrect").counted is True
        assert evaluation(result="partial").counted is True
        assert evaluation(result="unknown").counted is False

    def test_as_dict_shape(self) -> None:
        data = evaluation().as_dict()
        assert data["evaluationId"] == data["evaluation_id"]
        assert data["projectId"] == "demo"
        assert data["evaluationKind"] == "prediction"
        assert data["readOnly"] is True

    def test_optional_links_roundtrip(self) -> None:
        record = evaluation()
        assert record.decision_id is None
        assert record.recommendation_id is None

    def test_evidence_is_deduplicated(self) -> None:
        record = EvaluationRecord(
            evaluation_id="", project_id="demo", prediction_id="pred-1",
            evaluation_kind="prediction", input_context="", prediction_result="claim",
            expected_outcome="expected", actual_outcome="actual",
            evaluation_result="correct", confidence=0.5,
            evidence=["obs-1", "obs-1", "obs-2"],
        )
        assert record.evidence == ["obs-1", "obs-2"]

    def test_negative_evidence_entries_are_dropped(self) -> None:
        record = EvaluationRecord(
            evaluation_id="", project_id="demo", prediction_id="pred-1",
            evaluation_kind="prediction", input_context="", prediction_result="claim",
            expected_outcome="expected", actual_outcome="actual",
            evaluation_result="correct", confidence=0.5, evidence=["", "  ", "[REDACTED]"],
        )
        assert record.evidence == []


# ---------------------------------------------------------------------------
# ValidationStore persistence and isolation
# ---------------------------------------------------------------------------

class TestEvaluationStorage:
    def test_save_and_get_roundtrip(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        saved = db.save_evaluation(evaluation())
        loaded = db.get_evaluation(saved.evaluation_id)
        assert loaded is not None
        assert loaded.prediction_id == "pred-1"
        assert loaded.as_dict()["evaluationId"] == saved.evaluation_id

    def test_get_requires_same_project(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        saved = db.save_evaluation(evaluation())
        assert db.get_evaluation(saved.evaluation_id, project_id="demo") is not None
        assert db.get_evaluation(saved.evaluation_id, project_id="other") is None

    def test_get_without_project_filter_still_finds(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        saved = db.save_evaluation(evaluation())
        assert db.get_evaluation(saved.evaluation_id) is not None

    def test_list_is_project_isolated(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(project="demo"))
        db.save_evaluation(evaluation(project="alpha"))
        assert len(db.evaluations("demo")) == 1
        assert len(db.evaluations("alpha")) == 1
        assert len(db.evaluations("demo")) + len(db.evaluations("alpha")) == 2

    def test_list_filters_by_kind(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(kind="prediction"))
        db.save_evaluation(evaluation(kind="failure_prediction", prediction_id="pred-2"))
        assert len(db.evaluations("demo", kind="prediction")) == 1
        assert len(db.evaluations("demo", kind="failure_prediction")) == 1

    def test_list_filters_by_agent(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(agent_id="agent-1"))
        db.save_evaluation(evaluation(agent_id="agent-2", prediction_id="pred-2"))
        assert len(db.evaluations("demo", agent_id="agent-1")) == 1
        assert len(db.evaluations("demo", agent_id="agent-2")) == 1

    def test_list_filters_by_model(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(model_id="router"))
        db.save_evaluation(evaluation(model_id="coder", prediction_id="pred-2"))
        assert len(db.evaluations("demo", model_id="router")) == 1
        assert len(db.evaluations("demo", model_id="coder")) == 1

    def test_list_orders_newest_first(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        first = evaluation(prediction_id="pred-1")
        first = EvaluationRecord(
            evaluation_id="", project_id=first.project_id, prediction_id=first.prediction_id,
            evaluation_kind=first.evaluation_kind, input_context=first.input_context,
            prediction_result=first.prediction_result, expected_outcome=first.expected_outcome,
            actual_outcome=first.actual_outcome, evaluation_result=first.evaluation_result,
            confidence=first.confidence, evaluated_at="2026-01-01T00:00:00+00:00",
        )
        second = evaluation(prediction_id="pred-2")
        second = EvaluationRecord(
            evaluation_id="", project_id=second.project_id, prediction_id=second.prediction_id,
            evaluation_kind=second.evaluation_kind, input_context=second.input_context,
            prediction_result=second.prediction_result, expected_outcome=second.expected_outcome,
            actual_outcome=second.actual_outcome, evaluation_result=second.evaluation_result,
            confidence=second.confidence, evaluated_at="2026-01-02T00:00:00+00:00",
        )
        db.save_evaluation(first)
        db.save_evaluation(second)
        ids = [item.evaluation_id for item in db.evaluations("demo")]
        assert ids[0] == second.evaluation_id
        assert ids[1] == first.evaluation_id

    def test_limit_is_enforced(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        for index in range(5):
            db.save_evaluation(evaluation(prediction_id=f"pred-{index}"))
        assert len(db.evaluations("demo", limit=2)) == 2
        assert len(db.evaluations("demo", limit=100)) == 5

    def test_save_many_batches(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_many([evaluation(prediction_id="pred-1"), evaluation(prediction_id="pred-2")])
        assert len(db.evaluations("demo")) == 2

    def test_evaluation_id_is_generated(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        saved = db.save_evaluation(evaluation())
        assert saved.evaluation_id.startswith("eval_")
        assert len(saved.evaluation_id) > 8

    def test_evaluations_never_contains_payload_secrets(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        record = EvaluationRecord(
            evaluation_id="", project_id="demo", prediction_id="pred-1",
            evaluation_kind="prediction", input_context="password=correct-horse",
            prediction_result="claim", expected_outcome="expected", actual_outcome="actual",
            evaluation_result="correct", confidence=0.5,
        )
        db.save_evaluation(record)
        loaded = db.evaluations("demo")[0]
        assert "correct-horse" not in loaded.input_context


# ---------------------------------------------------------------------------
# API flow (approval-gated record + read-only GET)
# ---------------------------------------------------------------------------

class TestEvaluationApi:
    def test_post_requires_approval_then_approve(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "parser change",
                "prediction_result": "high regression risk", "expected_outcome": "regression",
                "actual_outcome": "regression occurred", "evaluation_result": "correct",
                "confidence": 0.8, "agent_id": "agent-1",
            },
        )
        assert pending.status_code == 202
        assert pending.json()["action"] == "intelligence_evaluation_record"
        assert pending.json()["status"] == "pending"
        # Nothing is written before approval.
        assert bridge.client.get("/intelligence/accuracy?project=demo").json()["counted"] == 0
        response = bridge.approve(pending.json()["requestId"])
        assert response.status_code == 200
        assert bridge.client.get("/intelligence/accuracy?project=demo").json()["counted"] == 1

    def test_post_rejects_unknown_kind(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "causal_claim", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        assert response.status_code == 400

    def test_post_rejects_unknown_result(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "maybe",
            },
        )
        assert response.status_code == 400

    def test_get_detail_after_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-9",
                "evaluation_kind": "risk_assessment", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "incorrect",
                "confidence": 0.4,
            },
        )
        bridge.approve(pending.json()["requestId"])
        detail = bridge.client.get(f"/intelligence/evaluation/{pending.json()['requestId']}?project=demo")
        # The evaluation id differs from the approval request id; read it from
        # the accuracy/listing endpoints instead.
        assert detail.status_code == 404
        listing = bridge.client.get("/intelligence/evaluations/phase27?project=demo").json()
        assert len(listing["evaluations"]) == 1
        evaluation_id = listing["evaluations"][0]["evaluationId"]
        ok = bridge.client.get(f"/intelligence/evaluation/{evaluation_id}?project=demo")
        assert ok.status_code == 200
        assert ok.json()["evaluationResult"] == "incorrect"

    def test_get_detail_is_project_scoped(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        bridge.approve(pending.json()["requestId"])
        listing = bridge.client.get("/intelligence/evaluations/phase27?project=demo").json()
        evaluation_id = listing["evaluations"][0]["evaluationId"]
        assert bridge.client.get(f"/intelligence/evaluation/{evaluation_id}?project=other").status_code == 404

    def test_evaluation_list_is_read_only(self, bridge) -> None:
        response = bridge.client.get("/intelligence/evaluations/phase27?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True

    def test_evaluation_list_filters_by_kind(self, bridge) -> None:
        for kind in ("prediction", "failure_prediction"):
            pending = bridge.client.post(
                "/intelligence/evaluation",
                json={
                    "project_id": "demo", "prediction_id": f"pred-{kind}",
                    "evaluation_kind": kind, "input_context": "",
                    "prediction_result": "claim", "expected_outcome": "expected",
                    "actual_outcome": "actual", "evaluation_result": "correct",
                },
            )
            bridge.approve(pending.json()["requestId"])
        listing = bridge.client.get("/intelligence/evaluations/phase27?project=demo&kind=failure_prediction").json()
        assert len(listing["evaluations"]) == 1
        assert listing["evaluations"][0]["evaluationKind"] == "failure_prediction"
