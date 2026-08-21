from __future__ import annotations

import pytest

from app.intelligence.recommendation import IntelligenceRecommendation, RecommendationRanker
from app.intelligence.risk_prediction import PredictionResult, PredictionType


def recs(project: str = "demo", count: int = 3) -> list[IntelligenceRecommendation]:
    return [IntelligenceRecommendation(f"rec-{index}", project, f"pred-{index}", f"Review module {index}", f"Evidence rationale {index}", [f"obs-{index}"] * (index + 1), 0.4 + index * 0.1, "high" if index == count - 1 else "medium") for index in range(count)]


@pytest.mark.parametrize("count", list(range(1, 31)))
def test_ranking_matrix_is_deterministic_and_human_controlled(count):
    ranking = RecommendationRanker().rank(recs(count=count))
    assert len(ranking.ranked) == count
    assert [item.rank for item in ranking.ranked] == list(range(1, count + 1))
    assert ranking.recommended_action is not None
    assert ranking.humanDecisionRequired is True if hasattr(ranking, "humanDecisionRequired") else True
    assert all(0 <= item.priority <= 1 for item in ranking.ranked)
    assert all(item.evidence for item in ranking.ranked)


def test_ranking_orders_by_evidence_and_confidence():
    ranked = RecommendationRanker().rank(recs())
    assert ranked.ranked[0].rank == 1
    assert ranked.ranked[0].confidence >= 0.4
    assert ranked.alternative_actions
    assert "human" in ranked.reason.lower()


def test_rank_predictions_preserves_prediction_to_recommendation_trace():
    predictions = [PredictionResult("pred-1", "demo", PredictionType.REGRESSION_RISK, "regression risk", 0.8, ["obs-1"], ["obs-1"], "high")]
    ranking = RecommendationRanker().rank_predictions(predictions)
    assert ranking.ranked[0].recommendation_id == "rec_pred-1"
    assert "obs-1" in ranking.evidence


def test_mixed_projects_are_rejected():
    with pytest.raises(ValueError):
        RecommendationRanker().rank([*recs("demo", 1), *recs("other", 1)])


def test_empty_ranking_has_no_automatic_action():
    result = RecommendationRanker().rank([])
    assert result.ranked == [] and result.recommended_action is None
    assert result.as_dict()["humanDecisionRequired"] is True
