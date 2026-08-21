"""Read-only composition of Phase 26 intelligence signals.

This facade intentionally performs no persistence. Explicit analysis writes and
knowledge proposals remain behind the existing ApprovalStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.config import Settings
from app.intelligence.correlation import CorrelationStore, FailureCorrelationEngine
from app.intelligence.dependency import DependencyRiskAnalyzer, DependencyRiskStore
from app.intelligence.evaluation import EvaluationStore, PredictionEvaluator, RecommendationOutcomeEvaluator
from app.intelligence.evidence_graph import EvidenceGraph, IntelligenceEvidenceGraph
from app.intelligence.impact_prediction import ImpactPredictionStore, ChangeImpactPredictionEngine
from app.intelligence.observation import ObservationStore
from app.intelligence.pattern_intelligence import PatternIntelligence, PatternStore
from app.intelligence.recommendation import IntelligenceRecommendationEngine, RecommendationRanker, RecommendationRanking
from app.intelligence.risk_prediction import PredictionEngine, PredictionStore
from app.intelligence.storage import IntelligenceStorage
from app.intelligence.trends import EngineeringTrendEngine, TrendStore
from app.intelligence.outcome import OutcomeStore
from app.memory.intelligence import IntelligenceMemory


@dataclass(frozen=True)
class Phase26Snapshot:
    project: str
    observations: list[Any]
    patterns: list[Any]
    predictions: list[Any]
    trends: list[Any]
    correlations: list[Any]
    impact: list[Any]
    dependencies: list[Any]
    recommendations: list[Any]
    ranking: RecommendationRanking
    outcomes: list[Any]
    evaluations: list[dict[str, Any]]
    evaluation_metrics: Any
    graph: EvidenceGraph
    knowledge: list[dict[str, Any]]
    decisions: list[Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "observations": [item.as_dict() for item in self.observations],
            "patterns": [item.as_dict() for item in self.patterns],
            "predictions": [item.as_dict() for item in self.predictions],
            "trends": [item.as_dict() for item in self.trends],
            "correlations": [item.as_dict() for item in self.correlations],
            "impact": [item.as_dict() for item in self.impact],
            "dependencies": [item.as_dict() for item in self.dependencies],
            "recommendations": [item.as_dict() for item in self.recommendations],
            "ranking": self.ranking.as_dict(),
            "outcomes": [item.as_dict() for item in self.outcomes],
            "evaluations": list(self.evaluations),
            "evaluationMetrics": self.evaluation_metrics.as_dict(),
            "evidenceGraph": self.graph.as_dict(),
            "knowledge": list(self.knowledge),
            "decisions": [item.as_dict() for item in self.decisions],
            "readOnly": True,
        }


def _as_list(value: Iterable[Any]) -> list[Any]:
    return list(value)


def build_phase26_snapshot(
    settings: Settings,
    project: str,
    *,
    limit: int = 1000,
    changed_files: Iterable[str] = (),
    changed_symbols: Iterable[str] = (),
) -> Phase26Snapshot:
    observations = ObservationStore(settings.intelligence_db_path).list(project, limit=limit)
    pattern_store = PatternStore(settings.intelligence_db_path)
    patterns = pattern_store.list(project, limit=limit) or PatternIntelligence().detect(project, observations)
    prediction_store = PredictionStore(settings.intelligence_db_path)
    predictions = prediction_store.list(project, limit=limit) or PredictionEngine().predict(project, patterns, observations)
    trend_store = TrendStore(settings.intelligence_db_path)
    trends = trend_store.list(project, limit=limit) or EngineeringTrendEngine().analyze(project, observations)
    correlation_store = CorrelationStore(settings.intelligence_db_path)
    correlations = correlation_store.list(project, limit=limit) or FailureCorrelationEngine().analyze(project, observations)
    impact_store = ImpactPredictionStore(settings.intelligence_db_path)
    impact = impact_store.list(project, limit=limit)
    if not impact and (changed_files or changed_symbols or observations):
        impact = [ChangeImpactPredictionEngine().predict(project, observations, changed_files=changed_files, changed_symbols=changed_symbols, historical_failures=observations)]
    dependency_store = DependencyRiskStore(settings.intelligence_db_path)
    dependencies = dependency_store.list(project, limit=limit) or DependencyRiskAnalyzer().analyze(project, observations, historical_failures=observations)
    recommendations = IntelligenceRecommendationEngine().generate(predictions)
    ranking = RecommendationRanker().rank(recommendations) if recommendations else RecommendationRanking(project_id=project, reason="No recommendations have evidence to rank")
    outcomes = OutcomeStore(settings.intelligence_db_path).list(project, limit=limit)
    evaluation_store = EvaluationStore(settings.intelligence_db_path)
    evaluations = evaluation_store.list(project, limit=limit)
    if not evaluations and outcomes:
        prediction_evals = PredictionEvaluator().evaluate_many(predictions, outcomes)
        recommendation_evals = RecommendationOutcomeEvaluator().evaluate_many(recommendations, outcomes)
        evaluations = [item.as_dict() for item in [*prediction_evals, *recommendation_evals]]
    evaluation_metrics = evaluation_store.metrics(project, limit=limit)
    if evaluations and evaluation_metrics.predictions == 0:
        # The derived fallback is intentionally calculated from returned
        # historical records and is not persisted or presented as a benchmark.
        from app.intelligence.evaluation.models import EvaluationMetrics
        prediction_evals = [item for item in evaluations if "prediction_id" in item]
        recommendation_evals = [item for item in evaluations if "recommendation_id" in item]
        correct = sum(1 for item in prediction_evals if item.get("correct"))
        total = len(prediction_evals)
        evaluation_metrics = EvaluationMetrics(
            project_id=project, predictions=total, correct=correct, incorrect=total - correct,
            accuracy=correct / total if total else 0.0, precision=0.0, recall=0.0,
            false_positive_rate=0.0, false_negative_rate=0.0,
            recommendation_count=len(recommendation_evals),
            recommendation_successes=sum(1 for item in recommendation_evals if item.get("success")),
            recommendation_success_rate=(sum(1 for item in recommendation_evals if item.get("success")) / len(recommendation_evals)) if recommendation_evals else 0.0,
        )
    knowledge = IntelligenceMemory(settings).list(project, limit=limit)
    decisions = IntelligenceStorage(settings.intelligence_db_path).list_decisions(project=project, limit=limit)
    graph = IntelligenceEvidenceGraph().build(
        project, observations=observations, patterns=patterns, trends=trends,
        correlations=correlations, predictions=predictions, impact_predictions=impact,
        recommendations=recommendations, decisions=decisions, outcomes=outcomes,
        knowledge=knowledge, evaluations=evaluations,
    )
    return Phase26Snapshot(
        project=project, observations=observations, patterns=patterns, predictions=predictions,
        trends=trends, correlations=correlations, impact=impact, dependencies=dependencies,
        recommendations=recommendations, ranking=ranking, outcomes=outcomes,
        evaluations=evaluations, evaluation_metrics=evaluation_metrics, graph=graph,
        knowledge=knowledge, decisions=decisions,
    )


Phase26Intelligence = build_phase26_snapshot
Phase26Manager = build_phase26_snapshot
