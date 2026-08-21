from __future__ import annotations

from pathlib import Path

from app.intelligence.validation import ValidationStore
from app.intelligence.validation.models import EvaluationRecord, RecommendationEffectiveness


def evaluation(
    *,
    project: str = "demo",
    prediction_id: str = "pred-1",
    kind: str = "prediction",
    result: str = "correct",
    confidence: float = 0.7,
    agent_id: str = "agent-1",
    model_id: str = "router",
) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_id="", project_id=project, prediction_id=prediction_id,
        evaluation_kind=kind, input_context="context", prediction_result="claim",
        expected_outcome="expected", actual_outcome="actual", evaluation_result=result,
        confidence=confidence, agent_id=agent_id, model_id=model_id,
    )


def effectiveness(
    *,
    project: str = "demo",
    recommendation_id: str = "rec-1",
    user_decision: str = "accepted",
    success: bool | None = True,
    classification: str | None = None,
) -> RecommendationEffectiveness:
    from app.intelligence.validation.effectiveness import RecommendationEffectivenessEngine

    if classification is None:
        classification, score = RecommendationEffectivenessEngine.classify(user_decision=user_decision, success=success)
    else:
        _, score = RecommendationEffectivenessEngine.classify(user_decision=user_decision, success=success)
    return RecommendationEffectiveness(
        effectiveness_id="", project_id=project, recommendation_id=recommendation_id,
        content="review parser tests", confidence=0.7, user_decision=user_decision,
        actual_result="tests passed", effectiveness_score=score, classification=classification,
    )


def store(db: Path) -> ValidationStore:
    return ValidationStore(db)
