"""Task 3 · Recommendation Effectiveness.

Tracks what happened after a human decided on a recommendation. User rejection
is recorded as a distinct bucket and is never conflated with an AI mistake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now

from .models import EffectivenessClass, RecommendationDecision, RecommendationEffectiveness


class RecommendationEffectivenessEngine:
    @staticmethod
    def classify(*, user_decision: str, success: bool | None, failure_reason: str = "") -> tuple[str, float]:
        """Classify an effectiveness record and derive its score.

        rejected -> REJECTED (never an AI error; score 0 because it was not
            tried, and reported separately from correctness).
        accepted + success -> CORRECT (score 1.0)
        accepted + partial -> PARTIALLY_USEFUL (score 0.5)
        accepted + failure -> INCORRECT (score 0.0)
        """
        decision = str(user_decision).lower().strip()
        if decision == RecommendationDecision.REJECTED.value:
            return EffectivenessClass.REJECTED.value, 0.0
        if decision == RecommendationDecision.PARTIAL.value:
            if success is True:
                return EffectivenessClass.PARTIALLY_USEFUL.value, 0.75
            if success is False:
                return EffectivenessClass.PARTIALLY_USEFUL.value, 0.25
            return EffectivenessClass.PARTIALLY_USEFUL.value, 0.5
        # accepted
        if success is True:
            return EffectivenessClass.CORRECT.value, 1.0
        if success is False:
            return EffectivenessClass.INCORRECT.value, 0.0
        # accepted but no outcome recorded yet: keep it neutral and explicit
        return EffectivenessClass.PARTIALLY_USEFUL.value, 0.5

    def evaluate(
        self,
        *,
        project_id: str,
        recommendation_id: str,
        content: str,
        confidence: float,
        user_decision: str,
        actual_result: str,
        success: bool | None,
        failure_reason: str = "",
        decision_id: str | None = None,
        evidence: list[str] | None = None,
    ) -> RecommendationEffectiveness:
        classification, score = self.classify(user_decision=user_decision, success=success, failure_reason=failure_reason)
        if classification == EffectivenessClass.INCORRECT.value and not failure_reason:
            failure_reason = "accepted recommendation did not produce the expected result"
        return RecommendationEffectiveness(
            effectiveness_id=f"effect_{token_hex(8)}",
            project_id=project_id,
            recommendation_id=recommendation_id,
            content=content,
            confidence=bounded_confidence(confidence),
            user_decision=user_decision,
            actual_result=actual_result,
            effectiveness_score=score,
            classification=classification,
            failure_reason=failure_reason,
            decision_id=decision_id,
            evidence=ids(evidence),
            evaluated_at=utc_now(),
        )

    @staticmethod
    def summary(project_id: str, records: Iterable[RecommendationEffectiveness]) -> dict[str, Any]:
        project = ensure_project(project_id)
        items = [record for record in records if record.project_id == project]
        counted = [record for record in items if record.classification != EffectivenessClass.REJECTED.value]
        successful = sum(1 for record in counted if record.classification == EffectivenessClass.CORRECT.value)
        partially = sum(1 for record in counted if record.classification == EffectivenessClass.PARTIALLY_USEFUL.value)
        total = len(items)
        rejected = sum(1 for record in items if record.classification == EffectivenessClass.REJECTED.value)
        incorrect = sum(1 for record in items if record.classification == EffectivenessClass.INCORRECT.value)
        mean_score = (sum(record.effectiveness_score for record in items) / total) if total else 0.0
        # Effectiveness rate treats partial as half credit; rejected is excluded
        # from the denominator because "not tried" says nothing about quality.
        effectiveness_rate = ((successful + 0.5 * partially) / len(counted)) if counted else 0.0
        return {
            "projectId": project,
            "total": total,
            "correct": successful,
            "partiallyUseful": partially,
            "incorrect": incorrect,
            "rejected": rejected,
            "effectivenessRate": round(max(0.0, min(1.0, effectiveness_rate)), 3),
            "meanEffectivenessScore": round(max(0.0, min(1.0, mean_score)), 3),
            "readOnly": True,
        }


RecommendationEffectivenessEvaluator = RecommendationEffectivenessEngine
