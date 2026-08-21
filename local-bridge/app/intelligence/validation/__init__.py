"""Phase 27 · Engineering Intelligence Validation Layer.

The validation layer observes, measures, evaluates, and proposes. It never
executes, approves, patches, or writes memory/knowledge on its own; every
persistent write is queued through the existing ApprovalStore.
"""

from .models import (
    DECISION_TYPES,
    EVALUATION_KINDS,
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkRun,
    DecisionOutcome,
    DecisionOutcomeStatus,
    EffectivenessClass,
    EvaluationKind,
    EvaluationRecord,
    EvaluationResult,
    KnowledgeImprovement,
    KnowledgeImprovementStatus,
    RecommendationDecision,
    RecommendationEffectiveness,
)
from .storage import ValidationStore
from .accuracy import AccuracyReport, AccuracySystem, CalibrationBin
from .effectiveness import RecommendationEffectivenessEngine, RecommendationEffectivenessEvaluator
from .decision_outcome import DecisionOutcomeIntelligence, DecisionOutcomeSummary, DecisionOutcomeEvaluator
from .benchmark import BenchmarkPlanner, BenchmarkRunner, BenchmarkRunner, builtin_datasets, find_builtin_dataset
from .knowledge import KnowledgeImprovementEngine, KnowledgeImprovementProposal

__all__ = [
    "DECISION_TYPES", "EVALUATION_KINDS", "BenchmarkCase", "BenchmarkDataset",
    "BenchmarkRun", "DecisionOutcome", "DecisionOutcomeStatus", "EffectivenessClass",
    "EvaluationKind", "EvaluationRecord", "EvaluationResult", "KnowledgeImprovement",
    "KnowledgeImprovementStatus", "RecommendationDecision", "RecommendationEffectiveness",
    "ValidationStore", "AccuracyReport", "AccuracySystem", "CalibrationBin",
    "RecommendationEffectivenessEngine", "RecommendationEffectivenessEvaluator",
    "DecisionOutcomeIntelligence", "DecisionOutcomeSummary", "DecisionOutcomeEvaluator",
    "BenchmarkPlanner", "BenchmarkRunner", "builtin_datasets", "find_builtin_dataset",
    "KnowledgeImprovementEngine", "KnowledgeImprovementProposal",
]
