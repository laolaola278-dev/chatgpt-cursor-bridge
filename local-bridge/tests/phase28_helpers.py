from __future__ import annotations

from pathlib import Path

from app.intelligence.governance import (
    GovernanceMemoryRecord,
    GovernanceRecord,
    GovernanceStore,
    PolicyViolation,
    ReviewProposal,
    RiskFinding,
)
from app.intelligence.validation import ValidationStore
from app.intelligence.validation.models import (
    BenchmarkRun,
    DecisionOutcome,
    EvaluationRecord,
    RecommendationEffectiveness,
)
from app.intelligence.validation.effectiveness import RecommendationEffectivenessEngine


def governance_store(db: Path) -> GovernanceStore:
    return GovernanceStore(db)


def validation_store(db: Path) -> ValidationStore:
    return ValidationStore(db)


def record(
    *,
    project: str = "demo",
    source_kind: str = "prediction",
    source_id: str = "pred-1",
    risk_level: str = "LOW",
    risk_score: float = 10.0,
    confidence: float = 0.7,
    governance_result: str = "PASS",
    agent_id: str = "agent-1",
    model_id: str = "router",
    evaluation_result: str = "",
    audit_request_id: str = "req_test",
    evidence: list[str] | None = None,
    created_at: str = "",
    reason: str = "test governance record",
) -> GovernanceRecord:
    return GovernanceRecord(
        governance_id="",
        project_id=project,
        source_kind=source_kind,
        source_id=source_id,
        risk_level=risk_level,
        risk_score=risk_score,
        confidence=confidence,
        governance_result=governance_result,
        agent_id=agent_id,
        model_id=model_id,
        policy_ids=[],
        evaluation_result=evaluation_result,
        reason=reason,
        evidence=evidence or [],
        audit_request_id=audit_request_id,
        created_at=created_at,
    )


def risk_finding(
    *,
    project: str = "demo",
    source_kind: str = "prediction",
    source_id: str = "pred-1",
    risk_level: str = "LOW",
    risk_score: float = 10.0,
    confidence: float = 0.6,
    factors: list[str] | None = None,
    agent_id: str = "agent-1",
    model_id: str = "router",
) -> RiskFinding:
    return RiskFinding(
        risk_id="",
        project_id=project,
        source_kind=source_kind,
        source_id=source_id,
        risk_level=risk_level,
        risk_score=risk_score,
        confidence=confidence,
        risk_factors=factors or [],
        reason="test finding",
        agent_id=agent_id,
        model_id=model_id,
    )


def violation(
    *,
    project: str = "demo",
    policy_id: str = "p_high_risk_operation",
    source_id: str = "pred-1",
    source_kind: str = "prediction",
    severity: str = "blocking",
    confidence: float = 0.7,
) -> PolicyViolation:
    return PolicyViolation(
        violation_id="",
        policy_id=policy_id,
        project_id=project,
        source_id=source_id,
        source_kind=source_kind,
        severity=severity,
        reason="test violation",
        confidence=confidence,
    )


def proposal(
    *,
    project: str = "demo",
    source_id: str = "pred-1",
    source_kind: str = "prediction",
    risk_level: str = "HIGH",
    status: str = "proposed",
    recommended_action: str = "Human review required",
    reason: str = "test review",
) -> ReviewProposal:
    return ReviewProposal(
        proposal_id="",
        project_id=project,
        source_id=source_id,
        source_kind=source_kind,
        risk_level=risk_level,
        reason=reason,
        recommended_action=recommended_action,
        confidence=0.7,
        status=status,
    )


def memory_record(
    *,
    project: str = "demo",
    category: str = "finding",
    content: str = "governance finding",
    approval_request_id: str = "req_test",
) -> GovernanceMemoryRecord:
    return GovernanceMemoryRecord(
        memory_id="",
        project_id=project,
        category=category,
        content=content,
        source="governance_analysis",
        confidence=0.7,
        approval_request_id=approval_request_id,
    )


def evaluation(
    *,
    project: str = "demo",
    prediction_id: str = "pred-1",
    kind: str = "prediction",
    result: str = "correct",
    confidence: float = 0.7,
    agent_id: str = "agent-1",
    model_id: str = "router",
    evaluated_at: str = "",
) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_id="", project_id=project, prediction_id=prediction_id,
        evaluation_kind=kind, input_context="context", prediction_result="claim",
        expected_outcome="expected", actual_outcome="actual", evaluation_result=result,
        confidence=confidence, evaluated_at=evaluated_at, agent_id=agent_id, model_id=model_id,
    )


def effectiveness(
    *,
    project: str = "demo",
    recommendation_id: str = "rec-1",
    user_decision: str = "accepted",
    success: bool | None = True,
    evaluated_at: str = "",
) -> RecommendationEffectiveness:
    classification, score = RecommendationEffectivenessEngine.classify(user_decision=user_decision, success=success)
    return RecommendationEffectiveness(
        effectiveness_id="", project_id=project, recommendation_id=recommendation_id,
        content="review parser tests", confidence=0.7, user_decision=user_decision,
        actual_result="tests passed", effectiveness_score=score, classification=classification,
        evaluated_at=evaluated_at,
    )


def decision_outcome(
    *,
    project: str = "demo",
    decision_id: str = "dec-1",
    decision_type: str = "refactoring",
    status: str = "SUCCESS",
    evaluated_at: str = "",
) -> DecisionOutcome:
    from secrets import token_hex

    return DecisionOutcome(
        outcome_id=f"out_{token_hex(8)}", project_id=project, decision_id=decision_id,
        decision_type=decision_type, title="refactor service",
        expected_outcome="expected", actual_outcome="actual", status=status,
        evaluated_at=evaluated_at,
    )


def benchmark_run(
    *,
    project: str = "demo",
    dataset_id: str = "ds-bug",
    model_id: str = "router",
    score: float = 0.8,
    accuracy: float = 0.8,
) -> BenchmarkRun:
    return BenchmarkRun(
        benchmark_id="", dataset_id=dataset_id, dataset_name="Bug prediction",
        project_id=project, category="bug_prediction", model_id=model_id,
        score=score, accuracy=accuracy, determinism_hash="deadbeef",
    )
