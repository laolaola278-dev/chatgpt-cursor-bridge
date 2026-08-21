"""Phase 28 · Intelligence Risk Analyzer.

The analyzer only observes, analyzes, classifies, and proposes. It never
performs any risk handling action, never blocks, and never mutates state.
The risk score is a deterministic function of the supplied evidence factors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.intelligence.common import bounded_confidence, utc_now
from app.intelligence.governance.models import GovernanceKind, RiskFinding, RiskLevel


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 1)


def risk_level_for_score(score: float) -> str:
    if score >= 80:
        return RiskLevel.CRITICAL.value
    if score >= 55:
        return RiskLevel.HIGH.value
    if score >= 30:
        return RiskLevel.MEDIUM.value
    return RiskLevel.LOW.value


@dataclass(frozen=True)
class RiskAnalysis:
    finding: RiskFinding
    factors: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"finding": self.finding.as_dict(), "factors": list(self.factors), "readOnly": True}


class IntelligenceRiskAnalyzer:
    """Deterministic risk classification for an intelligence claim.

    Factors
    -------
    low_confidence
        confidence below 0.3.
    incorrect_prediction / partial_prediction
        the underlying evaluation result.
    high_risk_source
        the source itself was flagged HIGH/CRITICAL or scored >= 60.
    declining_accuracy
        the project's measured prior accuracy is below 0.5.
    similar_high_risk_history
        similar past cases carried HIGH/CRITICAL risk.
    model_unreliable
        the model's benchmark reliability is below 0.5.
    sensitive_context
        the input context references credentials/secrets.
    regression_observed
        a regression signal is present in the evaluation outcome.
    """

    def __init__(self) -> None:
        self._weights = {
            "low_confidence": 15.0,
            "incorrect_prediction": 25.0,
            "partial_prediction": 10.0,
            "high_risk_source": 30.0,
            "declining_accuracy": 20.0,
            "similar_high_risk_history": 25.0,
            "model_unreliable": 25.0,
            "sensitive_context": 10.0,
            "regression_observed": 20.0,
        }
        self._critical_factors = {"high_risk_source", "incorrect_prediction", "model_unreliable"}

    def analyze(
        self,
        *,
        project: str,
        source_kind: str,
        source_id: str,
        confidence: float = 0.5,
        evaluation_result: str = "",
        source_risk_level: str = RiskLevel.LOW.value,
        source_risk_score: float = 0.0,
        prior_accuracy: float | None = None,
        similar_history: list[str] | None = None,
        model_reliability: float | None = None,
        regression: bool = False,
        context: str = "",
        agent_id: str = "",
        model_id: str = "",
    ) -> RiskAnalysis:
        factors: list[str] = []
        if confidence < 0.3:
            factors.append("low_confidence")
        if evaluation_result == "incorrect":
            factors.append("incorrect_prediction")
        elif evaluation_result == "partial":
            factors.append("partial_prediction")
        if source_risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value) or source_risk_score >= 60:
            factors.append("high_risk_source")
        if prior_accuracy is not None and prior_accuracy < 0.5:
            factors.append("declining_accuracy")
        if any(item in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value) for item in (similar_history or [])):
            factors.append("similar_high_risk_history")
        if model_reliability is not None and model_reliability < 0.5:
            factors.append("model_unreliable")
        if regression:
            factors.append("regression_observed")
        lowered = (context or "").lower()
        if any(
            keyword in lowered
            for keyword in ("api key", "api_key", "secret", "credential", "password", "private key", "authorization", "token")
        ):
            factors.append("sensitive_context")

        score = 10.0
        for factor in factors:
            score += self._weights.get(factor, 5.0)
        if any(factor in self._critical_factors for factor in factors):
            score += 15.0
        score = _clamp_score(score)

        # Deterministic confidence: more, stronger factors raise confidence in
        # the classification, but it is bounded and never hard-coded.
        confidence_out = bounded_confidence(min(0.9, 0.35 + 0.08 * len(factors)))
        finding = RiskFinding(
            risk_id="",
            project_id=project,
            source_kind=source_kind,
            source_id=source_id,
            agent_id=agent_id,
            model_id=model_id,
            risk_level=risk_level_for_score(score),
            risk_score=score,
            confidence=confidence_out,
            risk_factors=factors,
            reason="; ".join(factors) if factors else "No material risk factors detected",
            similar_cases=list(dict.fromkeys(similar_history or [])),
            created_at=utc_now(),
        )
        return RiskAnalysis(finding=finding, factors=factors)


# Backwards-friendly alias used by the public API surface.
RiskAnalyzer = IntelligenceRiskAnalyzer
