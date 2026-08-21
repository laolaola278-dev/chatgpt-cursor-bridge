from __future__ import annotations

from typing import Any

from .models import RiskFactors


class IntelligenceRiskEngine:
    """Score an engineering proposal from bounded, explainable inputs."""

    def score(self, factors: RiskFactors) -> dict[str, Any]:
        scope = min(30, max(0, factors.impact_scope) * 3)
        changed = min(20, max(0, factors.changed_files) * 4)
        dependencies = min(20, max(0, factors.dependency_count) * 2)
        coverage = 0 if factors.test_coverage is None else max(0, min(20, (70 - factors.test_coverage) // 3))
        rollback = 0 if factors.rollback_available else 15
        security = 15 if factors.security_sensitive else 0
        score = max(0, min(100, scope + changed + dependencies + coverage + rollback + security))
        level = "high" if score >= 60 else "medium" if score >= 30 else "low"
        return {"score": score, "risk": level, "factors": factors.as_dict()}

    def score_factors(self, **kwargs: Any) -> dict[str, Any]:
        return self.score(RiskFactors(**kwargs))
