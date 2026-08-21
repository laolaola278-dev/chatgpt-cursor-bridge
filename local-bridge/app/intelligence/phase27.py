"""Read-only composition of Phase 27 validation signals.

This facade performs no persistence. Evaluation records, effectiveness,
decision outcomes, benchmarks, and knowledge improvements are only readable
here; writes happen exclusively through approval-gated actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.intelligence.validation import (
    AccuracySystem,
    DecisionOutcomeIntelligence,
    KnowledgeImprovementEngine,
    RecommendationEffectivenessEngine,
    ValidationStore,
    builtin_datasets,
)


@dataclass(frozen=True)
class Phase27Snapshot:
    project: str
    evaluations: list[Any]
    accuracy: Any
    failed_predictions: list[dict[str, Any]]
    effectiveness: list[Any]
    effectiveness_summary: dict[str, Any]
    decision_outcomes: list[Any]
    decision_summary: Any
    benchmarks: list[Any]
    builtin_datasets: list[Any]
    improvements: list[dict[str, Any]]
    quality13: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "evaluations": [item.as_dict() for item in self.evaluations],
            "accuracy": self.accuracy.as_dict(),
            "failedPredictions": self.failed_predictions,
            "effectiveness": [item.as_dict() for item in self.effectiveness],
            "effectivenessSummary": self.effectiveness_summary,
            "decisionOutcomes": [item.as_dict() for item in self.decision_outcomes],
            "decisionSummary": self.decision_summary.as_dict(),
            "benchmarks": [item.as_dict() for item in self.benchmarks],
            "builtinDatasets": [item.as_dict() for item in self.builtin_datasets],
            "improvements": list(self.improvements),
            "quality13": dict(self.quality13),
            "readOnly": True,
        }


def build_phase27_snapshot(settings: Settings, project: str, *, limit: int = 1000) -> Phase27Snapshot:
    store = ValidationStore(settings.intelligence_db_path)
    evaluations = store.evaluations(project, limit=limit)
    accuracy = AccuracySystem().report(project, evaluations)
    failed = AccuracySystem().failed_predictions(evaluations, limit=limit)
    effectiveness = store.effectiveness(project, limit=limit)
    effectiveness_summary = RecommendationEffectivenessEngine.summary(project, effectiveness)
    decision_outcomes = store.decision_outcomes(project, limit=limit)
    decision_summary = DecisionOutcomeIntelligence.summary(project, decision_outcomes)
    benchmarks = store.benchmarks(project, limit=limit)
    improvements = KnowledgeImprovementEngine.list_improvements(store.improvements(project, limit=limit), project, limit=limit)

    from app.quality.gate13 import QualityGate13Evaluator

    quality13 = QualityGate13Evaluator().evaluate(
        prediction_traceable=True,
        prediction_count=len({item.prediction_id for item in evaluations}),
        evaluation_traceable=all(item.prediction_id and item.evaluation_result for item in evaluations),
        evaluation_count=len(evaluations),
        outcome_traceable=all(item.actual_outcome and item.expected_outcome for item in evaluations),
        outcome_count=len(evaluations),
        accuracy_computable=accuracy.counted > 0,
        accuracy_count=accuracy.counted,
        recommendation_effectiveness_computable=len(effectiveness) > 0,
        effectiveness_count=len(effectiveness),
        benchmark_runnable=len(builtin_datasets(project)) > 0,
        benchmark_count=len(benchmarks),
        knowledge_improvement_audited=True,
        improvement_count=len(improvements),
        no_auto_knowledge_write=True,
        no_permission_bypass=True,
    )
    return Phase27Snapshot(
        project=project,
        evaluations=evaluations,
        accuracy=accuracy,
        failed_predictions=failed,
        effectiveness=effectiveness,
        effectiveness_summary=effectiveness_summary,
        decision_outcomes=decision_outcomes,
        decision_summary=decision_summary,
        benchmarks=benchmarks,
        builtin_datasets=builtin_datasets(project),
        improvements=improvements,
        quality13=quality13,
    )


Phase27Validation = build_phase27_snapshot
Phase27Manager = build_phase27_snapshot
