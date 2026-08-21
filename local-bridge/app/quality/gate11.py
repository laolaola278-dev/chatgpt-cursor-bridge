"""Quality Gate 11.0 - Engineering Intelligence integrity."""

from __future__ import annotations

from typing import Any


class QualityGate11Evaluator:
    """Evaluate intelligence quality without blocking or repairing anything."""

    def evaluate(
        self,
        *,
        observation_integrity: bool = True,
        observation_count: int = 0,
        pattern_evidence: bool = True,
        pattern_count: int = 0,
        prediction_confidence: float = 0.0,
        prediction_count: int = 0,
        recommendation_traceability: bool = True,
        recommendation_count: int = 0,
        decision_evidence: bool = True,
        decision_count: int = 0,
        outcome_completeness: bool = True,
        outcome_count: int = 0,
        knowledge_provenance: bool = True,
        knowledge_count: int = 0,
        blocking_issues: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        checks = {
            "observationIntegrity": bool(observation_integrity),
            "patternEvidence": bool(pattern_evidence),
            "predictionConfidence": round(max(0.0, min(1.0, float(prediction_confidence))), 3),
            "recommendationTraceability": bool(recommendation_traceability),
            "decisionEvidence": bool(decision_evidence),
            "outcomeCompleteness": bool(outcome_completeness),
            "knowledgeProvenance": bool(knowledge_provenance),
        }
        blocking = list(dict.fromkeys(str(item) for item in (blocking_issues or [])))
        warning_list = list(dict.fromkeys(str(item) for item in (warnings or [])))
        if not observation_integrity: blocking.append("observation_integrity")
        if pattern_count and not pattern_evidence: blocking.append("pattern_evidence_missing")
        if prediction_count and float(prediction_confidence) < 0.35: warning_list.append("prediction_confidence_low")
        if recommendation_count and not recommendation_traceability: blocking.append("recommendation_not_traceable")
        if decision_count and not decision_evidence: blocking.append("decision_evidence_missing")
        if outcome_count and not outcome_completeness: warning_list.append("outcome_incomplete")
        if knowledge_count and not knowledge_provenance: blocking.append("knowledge_provenance_missing")
        if observation_count == 0: warning_list.append("no_observations")
        if blocking: status = "BLOCK"
        elif warning_list: status = "WARN"
        else: status = "PASS"
        valid = sum(1 for value in checks.values() if value is True or (isinstance(value, (int, float)) and value >= 0.5))
        quality = round(valid / len(checks) * 100)
        return {
            "gate": "11.0", "status": status, "quality": quality,
            "checks": checks, "observationCount": max(0, int(observation_count)),
            "patternCount": max(0, int(pattern_count)), "predictionCount": max(0, int(prediction_count)),
            "recommendationCount": max(0, int(recommendation_count)), "decisionCount": max(0, int(decision_count)),
            "outcomeCount": max(0, int(outcome_count)), "knowledgeCount": max(0, int(knowledge_count)),
            "blockingIssues": list(dict.fromkeys(blocking)), "warnings": warning_list,
            "readOnly": True,
        }


IntelligenceQualityGate = QualityGate11Evaluator
