"""Phase 27 · Engineering Intelligence Validation Layer data models.

Every evaluation record is traceable, auditable, and reproducible. None of
these records authorizes an action: the validation layer only observes,
measures, and proposes. All persistent writes are queued through the existing
ApprovalStore before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from secrets import token_hex
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now
from app.security.validator import ValidationFailed


class EvaluationKind(str, Enum):
    PREDICTION = "prediction"
    RECOMMENDATION = "recommendation"
    RISK_ASSESSMENT = "risk_assessment"
    TEST_PREDICTION = "test_prediction"
    ARCHITECTURE_PREDICTION = "architecture_prediction"
    FAILURE_PREDICTION = "failure_prediction"


EVALUATION_KINDS = {item.value for item in EvaluationKind}


class EvaluationResult(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


KNOWN_EVALUATION_RESULTS = {item.value for item in EvaluationResult}
# UNKNOWN outcomes are recorded for auditability but never counted in accuracy
# denominators: they carry no truth signal.
COUNTED_EVALUATION_RESULTS = {EvaluationResult.CORRECT.value, EvaluationResult.INCORRECT.value, EvaluationResult.PARTIAL.value}


class RecommendationDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIAL = "partial"


class EffectivenessClass(str, Enum):
    """User rejection is deliberately NOT counted as an AI mistake."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIALLY_USEFUL = "partially_useful"
    REJECTED = "rejected"


class DecisionOutcomeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"


DECISION_TYPES = ("architecture", "debugging", "refactoring", "test", "dependency", "risk")


class KnowledgeImprovementStatus(str, Enum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    REJECTED = "rejected"


@dataclass(frozen=True)
class EvaluationRecord:
    """Unified evaluation record for any intelligence claim.

    Fields
    ------
    prediction_id
        The traced prediction (or recommendation/decision) this evaluation
        measures.
    evaluation_kind
        One of the supported intelligence claim kinds.
    input_context
        Sanitized context the prediction was made against.
    prediction_result
        What the intelligence claimed would happen.
    expected_outcome / actual_outcome
        What was expected to verify the claim and what actually happened.
    evaluation_result
        correct / incorrect / partial / unknown.
    confidence
        The confidence the original claim carried (bounded 0.0-1.0).
    agent_id / model_id
        Optional attribution metadata; never used to authorize anything.
    """

    evaluation_id: str
    project_id: str
    prediction_id: str
    evaluation_kind: str
    input_context: str
    prediction_result: str
    expected_outcome: str
    actual_outcome: str
    evaluation_result: str
    confidence: float
    evaluated_at: str = ""
    agent_id: str = ""
    model_id: str = ""
    decision_id: str | None = None
    recommendation_id: str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        kind = str(self.evaluation_kind).lower().strip()
        if kind not in EVALUATION_KINDS:
            raise ValidationFailed(f"Unknown evaluation kind: {kind}")
        object.__setattr__(self, "evaluation_kind", kind)
        result = str(self.evaluation_result).lower().strip()
        if result not in KNOWN_EVALUATION_RESULTS:
            raise ValidationFailed(f"Unknown evaluation result: {result}")
        object.__setattr__(self, "evaluation_result", result)
        object.__setattr__(self, "prediction_id", sanitize_text(self.prediction_id, limit=200))
        if not self.prediction_id:
            raise ValidationFailed("prediction_id is required for an evaluation")
        object.__setattr__(self, "evaluation_id", sanitize_text(self.evaluation_id, limit=200) or f"eval_{token_hex(8)}")
        for name in ("input_context", "prediction_result", "expected_outcome", "actual_outcome"):
            object.__setattr__(self, name, sanitize_text(getattr(self, name), limit=12000))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "agent_id", sanitize_text(self.agent_id, limit=200))
        object.__setattr__(self, "model_id", sanitize_text(self.model_id, limit=200))
        object.__setattr__(self, "decision_id", sanitize_text(self.decision_id or "", limit=200) or None)
        object.__setattr__(self, "recommendation_id", sanitize_text(self.recommendation_id or "", limit=200) or None)
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "evaluated_at", self.evaluated_at or utc_now())

    @property
    def correct(self) -> bool:
        return self.evaluation_result == EvaluationResult.CORRECT.value

    @property
    def counted(self) -> bool:
        return self.evaluation_result in COUNTED_EVALUATION_RESULTS

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id, "evaluationId": self.evaluation_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "prediction_id": self.prediction_id, "predictionId": self.prediction_id,
            "evaluation_kind": self.evaluation_kind, "evaluationKind": self.evaluation_kind,
            "input_context": self.input_context, "inputContext": self.input_context,
            "prediction_result": self.prediction_result, "predictionResult": self.prediction_result,
            "expected_outcome": self.expected_outcome, "expectedOutcome": self.expected_outcome,
            "actual_outcome": self.actual_outcome, "actualOutcome": self.actual_outcome,
            "evaluation_result": self.evaluation_result, "evaluationResult": self.evaluation_result,
            "correct": self.correct, "confidence": self.confidence,
            "evaluated_at": self.evaluated_at, "evaluatedAt": self.evaluated_at,
            "agent_id": self.agent_id, "agentId": self.agent_id,
            "model_id": self.model_id, "modelId": self.model_id,
            "decision_id": self.decision_id, "decisionId": self.decision_id,
            "recommendation_id": self.recommendation_id, "recommendationId": self.recommendation_id,
            "evidence": list(self.evidence), "readOnly": True,
        }


@dataclass(frozen=True)
class RecommendationEffectiveness:
    """Effectiveness of a recommendation after a human decision and outcome.

    ``classification`` distinguishes rejected (human said no - not an AI
    error), incorrect (accepted but failed), correct (accepted and worked),
    and partially_useful (accepted with partial success).
    """

    effectiveness_id: str
    project_id: str
    recommendation_id: str
    content: str
    confidence: float
    user_decision: str
    actual_result: str
    effectiveness_score: float
    classification: str
    failure_reason: str = ""
    decision_id: str | None = None
    evaluated_at: str = ""
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "effectiveness_id", sanitize_text(self.effectiveness_id, limit=200) or f"effect_{token_hex(8)}")
        object.__setattr__(self, "recommendation_id", sanitize_text(self.recommendation_id, limit=200))
        if not self.recommendation_id:
            raise ValidationFailed("recommendation_id is required")
        decision = str(self.user_decision).lower().strip()
        if decision not in {item.value for item in RecommendationDecision}:
            raise ValidationFailed(f"Unknown user decision: {decision}")
        object.__setattr__(self, "user_decision", decision)
        classification = str(self.classification).lower().strip()
        if classification not in {item.value for item in EffectivenessClass}:
            raise ValidationFailed(f"Unknown effectiveness classification: {classification}")
        object.__setattr__(self, "classification", classification)
        object.__setattr__(self, "content", sanitize_text(self.content, limit=4000))
        object.__setattr__(self, "actual_result", sanitize_text(self.actual_result, limit=12000))
        object.__setattr__(self, "failure_reason", sanitize_text(self.failure_reason, limit=2000))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "effectiveness_score", round(max(0.0, min(1.0, float(self.effectiveness_score))), 3))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "decision_id", sanitize_text(self.decision_id or "", limit=200) or None)
        object.__setattr__(self, "evaluated_at", self.evaluated_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "effectiveness_id": self.effectiveness_id, "effectivenessId": self.effectiveness_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "recommendation_id": self.recommendation_id, "recommendationId": self.recommendation_id,
            "content": self.content, "confidence": self.confidence,
            "user_decision": self.user_decision, "userDecision": self.user_decision,
            "actual_result": self.actual_result, "actualResult": self.actual_result,
            "effectiveness_score": self.effectiveness_score, "effectivenessScore": self.effectiveness_score,
            "classification": self.classification, "failure_reason": self.failure_reason,
            "failureReason": self.failure_reason, "decision_id": self.decision_id,
            "decisionId": self.decision_id, "evaluated_at": self.evaluated_at,
            "evaluatedAt": self.evaluated_at, "evidence": list(self.evidence), "readOnly": True,
        }


@dataclass(frozen=True)
class DecisionOutcome:
    """Outcome of an engineering decision measured against its expectation."""

    outcome_id: str
    project_id: str
    decision_id: str
    decision_type: str
    title: str
    expected_outcome: str
    actual_outcome: str
    status: str
    evaluated_at: str = ""
    agent_id: str = ""
    model_id: str = ""
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "decision_id", sanitize_text(self.decision_id, limit=200))
        if not self.decision_id:
            raise ValidationFailed("decision_id is required")
        decision_type = str(self.decision_type).lower().strip()
        if decision_type not in DECISION_TYPES:
            raise ValidationFailed(f"Unknown decision type: {decision_type}")
        object.__setattr__(self, "decision_type", decision_type)
        status = str(self.status).upper().strip()
        if status not in {item.value for item in DecisionOutcomeStatus}:
            raise ValidationFailed(f"Unknown decision outcome status: {status}")
        object.__setattr__(self, "status", status)
        for name in ("title", "expected_outcome", "actual_outcome"):
            object.__setattr__(self, name, sanitize_text(getattr(self, name), limit=12000))
        object.__setattr__(self, "agent_id", sanitize_text(self.agent_id, limit=200))
        object.__setattr__(self, "model_id", sanitize_text(self.model_id, limit=200))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "evaluated_at", self.evaluated_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id, "outcomeId": self.outcome_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "decision_id": self.decision_id, "decisionId": self.decision_id,
            "decision_type": self.decision_type, "decisionType": self.decision_type,
            "title": self.title, "expected_outcome": self.expected_outcome,
            "expectedOutcome": self.expected_outcome, "actual_outcome": self.actual_outcome,
            "actualOutcome": self.actual_outcome, "status": self.status,
            "evaluated_at": self.evaluated_at, "evaluatedAt": self.evaluated_at,
            "agent_id": self.agent_id, "agentId": self.agent_id,
            "model_id": self.model_id, "modelId": self.model_id,
            "evidence": list(self.evidence), "readOnly": True,
        }


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    input: str
    expected: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", sanitize_text(self.case_id, limit=200))
        object.__setattr__(self, "category", sanitize_text(self.category, limit=100))
        object.__setattr__(self, "input", sanitize_text(self.input, limit=12000))
        object.__setattr__(self, "expected", sanitize_text(self.expected, limit=12000))

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "category": self.category, "input": self.input, "expected": self.expected}


@dataclass(frozen=True)
class BenchmarkDataset:
    dataset_id: str
    name: str
    project_id: str
    category: str
    cases: list[BenchmarkCase]

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "name", sanitize_text(self.name, limit=300))
        object.__setattr__(self, "category", sanitize_text(self.category, limit=100))
        object.__setattr__(self, "cases", list(self.cases))

    def as_dict(self) -> dict[str, Any]:
        return {"dataset_id": self.dataset_id, "name": self.name, "project_id": self.project_id, "projectId": self.project_id, "category": self.category, "cases": [item.as_dict() for item in self.cases], "readOnly": True}


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case: BenchmarkCase
    predicted: str
    correct: bool
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {"case": self.case.as_dict(), "predicted": self.predicted, "correct": self.correct, "score": self.score}


@dataclass(frozen=True)
class BenchmarkRun:
    benchmark_id: str
    dataset_id: str
    dataset_name: str
    project_id: str
    category: str
    model_id: str
    score: float
    accuracy: float
    determinism_hash: str
    created_at: str = ""
    cases: list[BenchmarkCaseResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "dataset_name", sanitize_text(self.dataset_name, limit=300))
        object.__setattr__(self, "model_id", sanitize_text(self.model_id, limit=200))
        # Scores are plain proportions (a perfect benchmark is exactly 1.0);
        # the confidence ceiling does not apply to measurement results.
        object.__setattr__(self, "score", round(max(0.0, min(1.0, float(self.score))), 3))
        object.__setattr__(self, "accuracy", round(max(0.0, min(1.0, float(self.accuracy))), 3))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id, "benchmarkId": self.benchmark_id,
            "dataset_id": self.dataset_id, "datasetId": self.dataset_id,
            "dataset_name": self.dataset_name, "datasetName": self.dataset_name,
            "project_id": self.project_id, "projectId": self.project_id,
            "category": self.category, "model_id": self.model_id, "modelId": self.model_id,
            "score": self.score, "accuracy": self.accuracy,
            "determinism_hash": self.determinism_hash, "determinismHash": self.determinism_hash,
            "created_at": self.created_at, "createdAt": self.created_at,
            "cases": [item.as_dict() for item in self.cases], "readOnly": True,
        }


@dataclass(frozen=True)
class KnowledgeImprovement:
    """Validated knowledge improvement produced from evaluation feedback.

    The record is only written after a human approves the proposal. It never
    mutates IntelligenceMemory directly; the improvement content can be
    proposed for knowledge append through the existing approval flow.
    """

    improvement_id: str
    project_id: str
    evaluation_id: str
    prediction_id: str
    category: str
    content: str
    source: str
    evidence: list[str]
    confidence: float
    status: str
    created_at: str = ""
    validated_at: str = ""
    approval_request_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "evaluation_id", sanitize_text(self.evaluation_id, limit=200))
        if not self.evaluation_id:
            raise ValidationFailed("evaluation_id is required for a knowledge improvement")
        object.__setattr__(self, "prediction_id", sanitize_text(self.prediction_id, limit=200))
        if not self.prediction_id:
            raise ValidationFailed("prediction_id is required for a knowledge improvement")
        object.__setattr__(self, "category", sanitize_text(self.category, limit=100))
        if self.category not in {"patterns", "predictions", "strategies", "outcomes", "trends", "correlations", "recommendations", "evaluations"}:
            raise ValidationFailed(f"Unknown knowledge improvement category: {self.category}")
        object.__setattr__(self, "content", sanitize_text(self.content, limit=12000))
        if not self.content.strip():
            raise ValidationFailed("content is required for a knowledge improvement")
        object.__setattr__(self, "source", sanitize_text(self.source, limit=500))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        status = str(self.status).lower().strip()
        if status not in {item.value for item in KnowledgeImprovementStatus}:
            raise ValidationFailed(f"Unknown knowledge improvement status: {status}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "created_at", self.created_at or utc_now())
        object.__setattr__(self, "approval_request_id", sanitize_text(self.approval_request_id, limit=100))

    def as_dict(self) -> dict[str, Any]:
        return {
            "improvement_id": self.improvement_id, "improvementId": self.improvement_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "evaluation_id": self.evaluation_id, "evaluationId": self.evaluation_id,
            "prediction_id": self.prediction_id, "predictionId": self.prediction_id,
            "category": self.category, "content": self.content, "source": self.source,
            "evidence": list(self.evidence), "confidence": self.confidence,
            "status": self.status, "created_at": self.created_at, "createdAt": self.created_at,
            "validated_at": self.validated_at, "validatedAt": self.validated_at,
            "approval_request_id": self.approval_request_id, "approvalRequestId": self.approval_request_id,
            "readOnly": True,
        }
