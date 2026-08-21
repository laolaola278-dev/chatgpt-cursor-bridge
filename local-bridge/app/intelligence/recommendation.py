from __future__ import annotations

from secrets import token_hex

from .models import Insight, Proposal
from .risk import IntelligenceRiskEngine
from .models import RiskFactors


class RecommendationEngine:
    def __init__(self, risk: IntelligenceRiskEngine | None = None) -> None:
        self.risk = risk or IntelligenceRiskEngine()

    def from_insight(self, insight: Insight, *, dependency_count: int = 0, changed_files: int = 0, test_coverage: int | None = None) -> Proposal:
        score = self.risk.score(RiskFactors(impact_scope=max(1, dependency_count), changed_files=changed_files, dependency_count=dependency_count, test_coverage=test_coverage, security_sensitive=insight.insight_type.value == "security_risk"))
        proposal_type = "refactor" if insight.insight_type.value in {"architecture_risk", "code_smell", "dependency_risk", "maintenance_risk"} else "improve_tests" if insight.insight_type.value == "test_gap" else "review"
        return Proposal(
            id=f"proposal_{token_hex(8)}", project=insight.project, insight_id=insight.id,
            proposal_type=proposal_type, target={"file": insight.location}, reasons=list(insight.evidence),
            expected_gain=[insight.suggestion], risk=score["risk"], risk_score=score["score"], created_at=insight.created_at,
        )

    def from_insights(self, insights: list[Insight], *, dependency_count: int = 0, changed_files: int = 0, test_coverage: int | None = None) -> list[Proposal]:
        return [self.from_insight(item, dependency_count=dependency_count, changed_files=changed_files, test_coverage=test_coverage) for item in insights]


# ---------------------------------------------------------------------------
# Phase 25 recommendation projection
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .common import bounded_confidence, ensure_project, ids, sanitize_text
from .risk_prediction.models import PredictionResult, PredictionType


@dataclass(frozen=True)
class IntelligenceRecommendation:
    recommendation_id: str
    project_id: str
    prediction_id: str
    recommendation: str
    rationale: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    risk_level: str = "medium"
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "recommendation", sanitize_text(self.recommendation, limit=2000))
        object.__setattr__(self, "rationale", sanitize_text(self.rationale, limit=2000))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "created_at", self.created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id, "recommendationId": self.recommendation_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "prediction_id": self.prediction_id, "predictionId": self.prediction_id,
            "recommendation": self.recommendation, "rationale": self.rationale,
            "evidence": list(self.evidence), "confidence": self.confidence,
            "risk_level": self.risk_level, "riskLevel": self.risk_level,
            "created_at": self.created_at, "createdAt": self.created_at,
            "readOnly": True,
        }


class IntelligenceRecommendationEngine:
    """Turn predictions into review suggestions; never creates an action."""

    _TEXT = {
        PredictionType.REGRESSION_RISK: "Review the affected module and run focused regression tests before a human decision.",
        PredictionType.BUILD_FAILURE_RISK: "Review the build boundary and verify the smallest reproducible build evidence.",
        PredictionType.TEST_FAILURE_RISK: "Review test coverage and failure history before selecting a strategy.",
        PredictionType.DEPENDENCY_RISK: "Review dependency compatibility, provenance, and rollback options.",
        PredictionType.ARCHITECTURE_RISK: "Review the architecture boundary and compare the proposed change with recorded decisions.",
        PredictionType.PERFORMANCE_RISK: "Review the performance baseline and compare the degradation evidence over time.",
    }

    def from_prediction(self, prediction: PredictionResult) -> IntelligenceRecommendation:
        text = self._TEXT[prediction.prediction_type]
        return IntelligenceRecommendation(
            recommendation_id=f"rec_{prediction.prediction_id}", project_id=prediction.project_id,
            prediction_id=prediction.prediction_id, recommendation=text,
            rationale=prediction.prediction, evidence=list(dict.fromkeys(prediction.evidence + prediction.observations)),
            confidence=prediction.confidence, risk_level=prediction.risk_level,
        )

    def generate(self, predictions: list[PredictionResult]) -> list[IntelligenceRecommendation]:
        return [self.from_prediction(item) for item in predictions]


RecommendationResult = IntelligenceRecommendation
RecommendationGenerator = IntelligenceRecommendationEngine


# ---------------------------------------------------------------------------
# Phase 26 recommendation ranking
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RankedRecommendation:
    recommendation_id: str
    project_id: str
    rank: int
    priority: float
    confidence: float
    risk_reduction: float
    effort_estimate: str
    evidence_strength: float
    recommendation: str
    reason: str
    evidence: list[str] = field(default_factory=list)
    risk_level: str = "medium"

    def as_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "recommendationId": self.recommendation_id,
            "project_id": self.project_id,
            "projectId": self.project_id,
            "rank": self.rank,
            "priority": self.priority,
            "confidence": self.confidence,
            "risk_reduction": self.risk_reduction,
            "riskReduction": self.risk_reduction,
            "effort_estimate": self.effort_estimate,
            "effortEstimate": self.effort_estimate,
            "evidence_strength": self.evidence_strength,
            "evidenceStrength": self.evidence_strength,
            "recommendation": self.recommendation,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "risk_level": self.risk_level,
            "riskLevel": self.risk_level,
            "readOnly": True,
        }


@dataclass(frozen=True)
class RecommendationRanking:
    project_id: str
    ranked: list[RankedRecommendation] = field(default_factory=list)
    recommended_action: str | None = None
    alternative_actions: list[str] = field(default_factory=list)
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "projectId": self.project_id,
            "ranked": [item.as_dict() for item in self.ranked],
            "recommendations": [item.as_dict() for item in self.ranked],
            "recommended_action": self.recommended_action,
            "recommendedAction": self.recommended_action,
            "alternative_actions": list(self.alternative_actions),
            "alternativeActions": list(self.alternative_actions),
            "reason": self.reason,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "readOnly": True,
            "humanDecisionRequired": True,
        }


class RecommendationRanker:
    """Rank review suggestions without selecting or executing one."""

    _RISK_REDUCTION = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 0.95}
    _EFFORT = {"low": 0.9, "medium": 0.6, "high": 0.3}

    @staticmethod
    def _effort(item: IntelligenceRecommendation) -> str:
        words = f"{item.recommendation} {item.rationale}".lower()
        if any(word in words for word in ("migration", "dependency", "architecture")):
            return "high"
        if any(word in words for word in ("coverage", "review", "test")):
            return "medium"
        return "low"

    def rank(self, recommendations: list[IntelligenceRecommendation]) -> RecommendationRanking:
        if not recommendations:
            return RecommendationRanking(project_id="unknown", reason="No recommendations have evidence to rank")
        projects = {item.project_id for item in recommendations}
        if len(projects) != 1:
            raise ValueError("Recommendations must belong to one project")
        project = next(iter(projects))
        candidates: list[tuple[float, IntelligenceRecommendation, str, float, float, float]] = []
        for item in recommendations:
            evidence_strength = min(1.0, len(item.evidence) / 5.0)
            reduction = self._RISK_REDUCTION.get(item.risk_level.lower(), 0.5)
            effort = self._effort(item)
            effort_score = self._EFFORT[effort]
            score = item.confidence * 0.4 + evidence_strength * 0.3 + reduction * 0.2 + effort_score * 0.1
            candidates.append((score, item, effort, reduction, evidence_strength, effort_score))
        candidates.sort(key=lambda value: (-value[0], value[1].recommendation_id))
        ranked: list[RankedRecommendation] = []
        for position, (score, item, effort, reduction, strength, _) in enumerate(candidates, start=1):
            ranked.append(RankedRecommendation(
                recommendation_id=item.recommendation_id, project_id=project, rank=position,
                priority=round(score, 3), confidence=item.confidence,
                risk_reduction=round(reduction, 3), effort_estimate=effort,
                evidence_strength=round(strength, 3), recommendation=item.recommendation,
                reason=item.rationale, evidence=item.evidence, risk_level=item.risk_level,
            ))
        first = ranked[0]
        return RecommendationRanking(
            project_id=project, ranked=ranked, recommended_action=first.recommendation,
            alternative_actions=[item.recommendation for item in ranked[1:]],
            reason="Ranked by evidence strength, bounded confidence, estimated risk reduction, and review effort; a human must decide",
            evidence=list(dict.fromkeys(item for candidate in recommendations for item in candidate.evidence)),
            confidence=round(sum(item.confidence for item in ranked) / len(ranked), 3),
        )

    def rank_predictions(self, predictions: list[PredictionResult]) -> RecommendationRanking:
        return self.rank(IntelligenceRecommendationEngine().generate(predictions))

    rank_recommendations = rank


RecommendationRankingEngine = RecommendationRanker
