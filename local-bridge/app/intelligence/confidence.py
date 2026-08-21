"""Deterministic confidence accounting for Phase 26 intelligence results.

Confidence is a transparent summary of evidence quality. It is never random,
never a certainty claim, and never authorizes an action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .common import bounded_confidence


@dataclass(frozen=True)
class ConfidenceBreakdown:
    evidence_count: int
    historical_similarity: float
    data_freshness: float
    outcome_validation: float
    pattern_consistency: float
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidenceCount": self.evidence_count,
            "historicalSimilarity": round(self.historical_similarity, 3),
            "dataFreshness": round(self.data_freshness, 3),
            "outcomeValidation": round(self.outcome_validation, 3),
            "patternConsistency": round(self.pattern_consistency, 3),
            "score": self.score,
        }

    def explanation(self) -> str:
        return (
            f"confidence={self.score:.3f}; evidence={self.evidence_count}, "
            f"historical_similarity={self.historical_similarity:.3f}, "
            f"freshness={self.data_freshness:.3f}, "
            f"outcome_validation={self.outcome_validation:.3f}, "
            f"pattern_consistency={self.pattern_consistency:.3f}"
        )


def _freshness(timestamp: str | None) -> float:
    if not timestamp:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400.0)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, 1.0 / (1.0 + age_days / 30.0))), 3)


def derive_confidence(
    *,
    evidence_count: int,
    latest_timestamp: str | None = None,
    historical_similarity: float = 0.0,
    outcome_validation: float = 0.0,
    pattern_consistency: float = 0.0,
) -> ConfidenceBreakdown:
    """Calculate a bounded score from explicit, inspectable factors."""
    count = max(0, int(evidence_count))
    evidence_strength = min(1.0, count / 5.0)
    similarity_score = max(0.0, min(1.0, float(historical_similarity)))
    validation_score = max(0.0, min(1.0, float(outcome_validation)))
    consistency_score = max(0.0, min(1.0, float(pattern_consistency)))
    freshness_score = _freshness(latest_timestamp)
    if count == 0:
        score = 0.0
    else:
        score = (
            evidence_strength * 0.25
            + similarity_score * 0.20
            + freshness_score * 0.20
            + validation_score * 0.20
            + consistency_score * 0.15
        )
    return ConfidenceBreakdown(
        evidence_count=count,
        historical_similarity=similarity_score,
        data_freshness=freshness_score,
        outcome_validation=validation_score,
        pattern_consistency=consistency_score,
        score=bounded_confidence(score),
    )
