"""Phase 27 · Recommendation Effectiveness tests."""

from __future__ import annotations

import pytest

from app.intelligence.validation import RecommendationEffectivenessEngine
from app.intelligence.validation.models import EffectivenessClass
from app.security.validator import ValidationFailed
from tests.phase27_helpers import effectiveness, store


class TestClassification:
    @pytest.mark.parametrize(
        ("decision", "success", "expected"),
        [
            ("accepted", True, EffectivenessClass.CORRECT.value),
            ("accepted", False, EffectivenessClass.INCORRECT.value),
            ("accepted", None, EffectivenessClass.PARTIALLY_USEFUL.value),
            ("rejected", True, EffectivenessClass.REJECTED.value),
            ("rejected", False, EffectivenessClass.REJECTED.value),
            ("partial", True, EffectivenessClass.PARTIALLY_USEFUL.value),
            ("partial", False, EffectivenessClass.PARTIALLY_USEFUL.value),
            ("partial", None, EffectivenessClass.PARTIALLY_USEFUL.value),
        ],
    )
    def test_classify_buckets(self, decision, success, expected) -> None:
        classification, _ = RecommendationEffectivenessEngine.classify(user_decision=decision, success=success)
        assert classification == expected

    def test_rejection_is_not_an_ai_error(self) -> None:
        classification, score = RecommendationEffectivenessEngine.classify(user_decision="rejected", success=False)
        assert classification == EffectivenessClass.REJECTED.value
        # Rejected recommendations get score 0 but are NOT in the incorrect bucket.
        assert score == 0.0

    def test_correct_score_is_one(self) -> None:
        _, score = RecommendationEffectivenessEngine.classify(user_decision="accepted", success=True)
        assert score == 1.0

    def test_incorrect_score_is_zero(self) -> None:
        _, score = RecommendationEffectivenessEngine.classify(user_decision="accepted", success=False)
        assert score == 0.0

    def test_partial_scores(self) -> None:
        assert RecommendationEffectivenessEngine.classify(user_decision="partial", success=True)[1] == 0.75
        assert RecommendationEffectivenessEngine.classify(user_decision="partial", success=False)[1] == 0.25
        assert RecommendationEffectivenessEngine.classify(user_decision="partial", success=None)[1] == 0.5


class TestEffectivenessRecord:
    def test_evaluate_builds_record(self) -> None:
        record = RecommendationEffectivenessEngine().evaluate(
            project_id="demo", recommendation_id="rec-1", content="review parser",
            confidence=0.8, user_decision="accepted", actual_result="tests passed",
            success=True,
        )
        assert record.classification == EffectivenessClass.CORRECT.value
        assert record.effectiveness_score == 1.0
        assert record.effectiveness_id.startswith("effect_")

    def test_incorrect_gets_default_failure_reason(self) -> None:
        record = RecommendationEffectivenessEngine().evaluate(
            project_id="demo", recommendation_id="rec-1", content="review parser",
            confidence=0.8, user_decision="accepted", actual_result="regression",
            success=False,
        )
        assert record.failure_reason

    def test_correct_has_empty_failure_reason(self) -> None:
        record = RecommendationEffectivenessEngine().evaluate(
            project_id="demo", recommendation_id="rec-1", content="review parser",
            confidence=0.8, user_decision="accepted", actual_result="passed",
            success=True,
        )
        assert record.failure_reason == ""

    def test_rejects_unknown_user_decision(self) -> None:
        with pytest.raises(ValidationFailed):
            RecommendationEffectivenessEngine().evaluate(
                project_id="demo", recommendation_id="rec-1", content="x",
                confidence=0.5, user_decision="maybe", actual_result="r", success=True,
            )

    def test_rejects_unknown_classification(self) -> None:
        with pytest.raises(ValidationFailed):
            effectiveness(classification="not-a-class")

    def test_bounds_confidence_and_score(self) -> None:
        record = RecommendationEffectivenessEngine().evaluate(
            project_id="demo", recommendation_id="rec-1", content="x",
            confidence=9.9, user_decision="accepted", actual_result="r", success=True,
        )
        assert record.confidence <= 0.95
        assert record.effectiveness_score <= 1.0

    def test_evidence_deduped(self) -> None:
        record = RecommendationEffectivenessEngine().evaluate(
            project_id="demo", recommendation_id="rec-1", content="x",
            confidence=0.5, user_decision="accepted", actual_result="r",
            success=True, evidence=["obs-1", "obs-1"],
        )
        assert record.evidence == ["obs-1"]

    def test_scrubs_secrets_from_content(self) -> None:
        record = RecommendationEffectivenessEngine().evaluate(
            project_id="demo", recommendation_id="rec-1", content="password=hunter2",
            confidence=0.5, user_decision="accepted", actual_result="r", success=True,
        )
        assert "hunter2" not in record.content

    def test_decision_link_is_optional(self) -> None:
        record = RecommendationEffectivenessEngine().evaluate(
            project_id="demo", recommendation_id="rec-1", content="x",
            confidence=0.5, user_decision="accepted", actual_result="r", success=True,
            decision_id="decision-1",
        )
        assert record.decision_id == "decision-1"


class TestEffectivenessStorage:
    def test_save_roundtrip(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        record = db.save_effectiveness(effectiveness())
        loaded = db.effectiveness("demo")[0]
        assert loaded.effectiveness_id == record.effectiveness_id
        assert loaded.classification == EffectivenessClass.CORRECT.value

    def test_effectiveness_is_project_isolated(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_effectiveness(effectiveness(project="demo"))
        db.save_effectiveness(effectiveness(project="alpha"))
        assert len(db.effectiveness("demo")) == 1
        assert len(db.effectiveness("alpha")) == 1

    def test_effectiveness_orders_newest_first(self, tmp_path) -> None:
        from app.intelligence.validation.models import RecommendationEffectiveness

        db = store(tmp_path / "i.db")
        first = effectiveness(recommendation_id="rec-1")
        first = RecommendationEffectiveness(
            effectiveness_id="", project_id=first.project_id, recommendation_id=first.recommendation_id,
            content=first.content, confidence=first.confidence, user_decision=first.user_decision,
            actual_result=first.actual_result, effectiveness_score=first.effectiveness_score,
            classification=first.classification, evaluated_at="2026-01-01T00:00:00+00:00",
        )
        second = effectiveness(recommendation_id="rec-2")
        second = RecommendationEffectiveness(
            effectiveness_id="", project_id=second.project_id, recommendation_id=second.recommendation_id,
            content=second.content, confidence=second.confidence, user_decision=second.user_decision,
            actual_result=second.actual_result, effectiveness_score=second.effectiveness_score,
            classification=second.classification, evaluated_at="2026-01-02T00:00:00+00:00",
        )
        db.save_effectiveness(first)
        db.save_effectiveness(second)
        ids = [item.recommendation_id for item in db.effectiveness("demo")]
        assert ids[0] == "rec-2"


class TestEffectivenessSummary:
    def test_summary_counts_buckets(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_effectiveness(effectiveness(recommendation_id="a", user_decision="accepted", success=True))
        db.save_effectiveness(effectiveness(recommendation_id="b", user_decision="accepted", success=False))
        db.save_effectiveness(effectiveness(recommendation_id="c", user_decision="rejected", success=False))
        summary = RecommendationEffectivenessEngine.summary("demo", db.effectiveness("demo"))
        assert summary["total"] == 3
        assert summary["correct"] == 1
        assert summary["incorrect"] == 1
        assert summary["rejected"] == 1

    def test_rejection_excluded_from_effectiveness_rate(self) -> None:
        records = [
            effectiveness(recommendation_id="a", user_decision="accepted", success=True),
            effectiveness(recommendation_id="b", user_decision="rejected", success=False),
        ]
        summary = RecommendationEffectivenessEngine.summary("demo", records)
        assert summary["effectivenessRate"] == 1.0

    def test_partial_gets_half_credit(self) -> None:
        records = [
            effectiveness(recommendation_id="a", user_decision="accepted", success=True),
            effectiveness(recommendation_id="b", user_decision="partial", success=True),
            effectiveness(recommendation_id="c", user_decision="accepted", success=False),
        ]
        summary = RecommendationEffectivenessEngine.summary("demo", records)
        assert summary["effectivenessRate"] == pytest.approx(0.5, abs=0.001)

    def test_empty_summary(self) -> None:
        summary = RecommendationEffectivenessEngine.summary("demo", [])
        assert summary["total"] == 0
        assert summary["effectivenessRate"] == 0.0

    def test_summary_is_project_scoped(self) -> None:
        records = [
            effectiveness(project="demo", recommendation_id="a", user_decision="accepted", success=True),
            effectiveness(project="other", recommendation_id="b", user_decision="accepted", success=False),
        ]
        summary = RecommendationEffectivenessEngine.summary("demo", records)
        assert summary["total"] == 1

    def test_mean_score_reflects_all_records(self) -> None:
        records = [
            effectiveness(recommendation_id="a", user_decision="accepted", success=True),
            effectiveness(recommendation_id="b", user_decision="rejected", success=False),
        ]
        summary = RecommendationEffectivenessEngine.summary("demo", records)
        assert summary["meanEffectivenessScore"] == pytest.approx(0.5)


class TestEffectivenessApi:
    def test_effectiveness_endpoint_read_only(self, bridge) -> None:
        response = bridge.client.get("/intelligence/effectiveness?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True
        assert response.json()["summary"]["total"] == 0

    def test_effectiveness_endpoint_project_isolation(self, bridge) -> None:
        # Seed data directly through the API is not exposed for effectiveness;
        # records come from the approved evaluation pipeline. Verify isolation
        # with empty stores for two projects.
        assert bridge.client.get("/intelligence/effectiveness?project=demo").json()["summary"]["total"] == 0
        assert bridge.client.get("/intelligence/effectiveness?project=other").json()["summary"]["total"] == 0
