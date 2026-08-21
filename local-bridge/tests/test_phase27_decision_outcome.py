"""Phase 27 · Decision Outcome Intelligence tests."""

from __future__ import annotations

import pytest

from app.intelligence.validation import DecisionOutcomeIntelligence
from app.intelligence.validation.models import DECISION_TYPES, DecisionOutcomeStatus
from app.security.validator import ValidationFailed
from tests.phase27_helpers import store


def _record(intelligence: DecisionOutcomeIntelligence, db, *, project: str = "demo", decision_type: str = "architecture", status: str = "SUCCESS", index: int = 0) -> None:
    record = intelligence.record(
        project_id=project, decision_id=f"decision-{index}", decision_type=decision_type,
        title=f"decision {index}", expected_outcome="expected", actual_outcome="actual",
        status=status, agent_id="agent-1", model_id="router",
    )
    db.save_decision_outcome(record)


class TestDecisionOutcomeRecord:
    @pytest.mark.parametrize("decision_type", DECISION_TYPES)
    def test_supports_all_decision_types(self, decision_type: str) -> None:
        record = DecisionOutcomeIntelligence().record(
            project_id="demo", decision_id="d-1", decision_type=decision_type,
            title="t", expected_outcome="e", actual_outcome="a", status="SUCCESS",
        )
        assert record.decision_type == decision_type

    @pytest.mark.parametrize("status", sorted({item.value for item in DecisionOutcomeStatus}))
    def test_supports_all_statuses(self, status: str) -> None:
        record = DecisionOutcomeIntelligence().record(
            project_id="demo", decision_id="d-1", decision_type="debugging",
            title="t", expected_outcome="e", actual_outcome="a", status=status,
        )
        assert record.status == status

    def test_rejects_unknown_decision_type(self) -> None:
        with pytest.raises(ValidationFailed):
            DecisionOutcomeIntelligence().record(
                project_id="demo", decision_id="d-1", decision_type="crypto",
                title="t", expected_outcome="e", actual_outcome="a", status="SUCCESS",
            )

    def test_rejects_unknown_status(self) -> None:
        with pytest.raises(ValidationFailed):
            DecisionOutcomeIntelligence().record(
                project_id="demo", decision_id="d-1", decision_type="test",
                title="t", expected_outcome="e", actual_outcome="a", status="MAYBE",
            )

    def test_requires_decision_id(self) -> None:
        with pytest.raises(ValidationFailed):
            DecisionOutcomeIntelligence().record(
                project_id="demo", decision_id="", decision_type="test",
                title="t", expected_outcome="e", actual_outcome="a", status="SUCCESS",
            )

    def test_generates_outcome_id(self) -> None:
        record = DecisionOutcomeIntelligence().record(
            project_id="demo", decision_id="d-1", decision_type="test",
            title="t", expected_outcome="e", actual_outcome="a", status="SUCCESS",
        )
        assert record.outcome_id.startswith("dout_")

    def test_scrubs_secrets(self) -> None:
        record = DecisionOutcomeIntelligence().record(
            project_id="demo", decision_id="d-1", decision_type="refactoring",
            title="token=abc123", expected_outcome="e", actual_outcome="a", status="SUCCESS",
        )
        assert "abc123" not in record.title

    def test_metadata_fields_roundtrip(self) -> None:
        record = DecisionOutcomeIntelligence().record(
            project_id="demo", decision_id="d-1", decision_type="dependency",
            title="t", expected_outcome="e", actual_outcome="a", status="PARTIAL",
            agent_id="agent-2", model_id="coder", evidence=["obs-1", "obs-2"],
        )
        assert record.agent_id == "agent-2"
        assert record.model_id == "coder"
        assert record.evidence == ["obs-1", "obs-2"]


class TestDecisionOutcomeStorage:
    def test_save_roundtrip(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        record = DecisionOutcomeIntelligence().record(
            project_id="demo", decision_id="d-1", decision_type="architecture",
            title="t", expected_outcome="e", actual_outcome="a", status="SUCCESS",
        )
        db.save_decision_outcome(record)
        loaded = db.decision_outcomes("demo")[0]
        assert loaded.outcome_id == record.outcome_id
        assert loaded.decision_type == "architecture"

    def test_is_project_isolated(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        intelligence = DecisionOutcomeIntelligence()
        _record(intelligence, db, project="demo", index=1)
        _record(intelligence, db, project="alpha", index=2)
        assert len(db.decision_outcomes("demo")) == 1
        assert len(db.decision_outcomes("alpha")) == 1

    def test_filter_by_type(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        intelligence = DecisionOutcomeIntelligence()
        _record(intelligence, db, decision_type="architecture", index=1)
        _record(intelligence, db, decision_type="debugging", index=2)
        assert len(db.decision_outcomes("demo", decision_type="debugging")) == 1


class TestDecisionOutcomeSummary:
    def test_success_rate_by_type(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        intelligence = DecisionOutcomeIntelligence()
        _record(intelligence, db, decision_type="architecture", status="SUCCESS", index=1)
        _record(intelligence, db, decision_type="architecture", status="FAILURE", index=2)
        _record(intelligence, db, decision_type="debugging", status="SUCCESS", index=3)
        summary = DecisionOutcomeIntelligence.summary("demo", db.decision_outcomes("demo"))
        assert summary.total == 3
        assert summary.by_type["architecture"]["successRate"] == pytest.approx(0.5, abs=0.001)
        assert summary.by_type["debugging"]["successRate"] == 1.0
        assert summary.overall_success_rate == pytest.approx(2 / 3, abs=0.001)

    def test_partial_is_not_success(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        intelligence = DecisionOutcomeIntelligence()
        _record(intelligence, db, status="PARTIAL", index=1)
        _record(intelligence, db, status="FAILURE", index=2)
        summary = DecisionOutcomeIntelligence.summary("demo", db.decision_outcomes("demo"))
        assert summary.overall_success_rate == 0.0

    def test_empty_summary(self) -> None:
        summary = DecisionOutcomeIntelligence.summary("demo", [])
        assert summary.total == 0
        assert summary.overall_success_rate == 0.0

    def test_summary_is_project_scoped(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        intelligence = DecisionOutcomeIntelligence()
        _record(intelligence, db, project="demo", status="SUCCESS", index=1)
        _record(intelligence, db, project="other", status="FAILURE", index=2)
        summary = DecisionOutcomeIntelligence.summary("demo", db.decision_outcomes("demo"))
        assert summary.total == 1
        assert summary.overall_success_rate == 1.0

    def test_summary_dict_shape(self, tmp_path) -> None:
        summary = DecisionOutcomeIntelligence.summary("demo", [])
        data = summary.as_dict()
        assert data["projectId"] == "demo"
        assert data["readOnly"] is True


class TestDecisionOutcomeApi:
    def test_endpoint_read_only_empty(self, bridge) -> None:
        response = bridge.client.get("/intelligence/decision-outcomes?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True
        assert response.json()["summary"]["total"] == 0

    def test_endpoint_is_project_scoped(self, bridge) -> None:
        assert bridge.client.get("/intelligence/decision-outcomes?project=demo").json()["summary"]["total"] == 0
        assert bridge.client.get("/intelligence/decision-outcomes?project=other").json()["summary"]["total"] == 0

    def test_endpoint_filters_by_type(self, bridge) -> None:
        response = bridge.client.get("/intelligence/decision-outcomes?project=demo&decision_type=architecture")
        assert response.status_code == 200
        assert response.json()["decisionOutcomes"] == []
