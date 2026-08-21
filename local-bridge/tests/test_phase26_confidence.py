from __future__ import annotations

import pytest

from app.intelligence.confidence import derive_confidence


@pytest.mark.parametrize("count", list(range(30)))
def test_confidence_evidence_count_matrix_is_bounded(count):
    result = derive_confidence(evidence_count=count, latest_timestamp="2026-01-01T00:00:00+00:00", historical_similarity=count / 29 if count else 0, outcome_validation=0.5, pattern_consistency=0.5)
    assert 0 <= result.score <= 0.95
    assert result.evidence_count == count
    assert result.explanation() and result.as_dict()["evidenceCount"] == count


def test_confidence_without_evidence_is_zero():
    assert derive_confidence(evidence_count=0, historical_similarity=1, outcome_validation=1, pattern_consistency=1).score == 0


def test_confidence_is_not_random():
    kwargs = {"evidence_count": 3, "latest_timestamp": "2026-01-01T00:00:00+00:00", "historical_similarity": 0.5, "outcome_validation": 0.4, "pattern_consistency": 0.7}
    assert derive_confidence(**kwargs) == derive_confidence(**kwargs)


def test_confidence_factors_are_clamped():
    result = derive_confidence(evidence_count=2, historical_similarity=9, outcome_validation=-1, pattern_consistency=8)
    assert result.historical_similarity == 1.0 and result.outcome_validation == 0.0 and result.pattern_consistency == 1.0


def test_freshness_is_explainable():
    fresh = derive_confidence(evidence_count=2, latest_timestamp="2999-01-01T00:00:00+00:00")
    old = derive_confidence(evidence_count=2, latest_timestamp="2000-01-01T00:00:00+00:00")
    assert fresh.data_freshness >= old.data_freshness
    assert "freshness" in fresh.explanation()
