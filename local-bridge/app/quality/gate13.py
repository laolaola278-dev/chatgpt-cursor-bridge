"""Quality Gate 13.0 - Engineering Intelligence Validation integrity.

The gate only evaluates and reports. A BLOCK result must prevent release, but
the gate itself never performs or authorizes any write.
"""

from __future__ import annotations

from typing import Any


class QualityGate13Evaluator:
    def evaluate(
        self,
        *,
        prediction_traceable: bool = True,
        prediction_count: int = 0,
        evaluation_traceable: bool = True,
        evaluation_count: int = 0,
        outcome_traceable: bool = True,
        outcome_count: int = 0,
        accuracy_computable: bool = True,
        accuracy_count: int = 0,
        recommendation_effectiveness_computable: bool = True,
        effectiveness_count: int = 0,
        benchmark_runnable: bool = True,
        benchmark_count: int = 0,
        knowledge_improvement_audited: bool = True,
        improvement_count: int = 0,
        no_auto_knowledge_write: bool = True,
        no_permission_bypass: bool = True,
        blocking_issues: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        checks = {
            "predictionTraceable": bool(prediction_traceable),
            "evaluationTraceable": bool(evaluation_traceable),
            "outcomeTraceable": bool(outcome_traceable),
            "accuracyComputable": bool(accuracy_computable),
            "recommendationEffectivenessComputable": bool(recommendation_effectiveness_computable),
            "benchmarkRunnable": bool(benchmark_runnable),
            "knowledgeImprovementAudited": bool(knowledge_improvement_audited),
            "noAutoKnowledgeWrite": bool(no_auto_knowledge_write),
            "noPermissionBypass": bool(no_permission_bypass),
        }
        blocking = list(dict.fromkeys(str(item) for item in (blocking_issues or [])))
        warning_list = list(dict.fromkeys(str(item) for item in (warnings or [])))
        if prediction_count and not prediction_traceable:
            blocking.append("prediction_not_traceable")
        if evaluation_count and not evaluation_traceable:
            blocking.append("evaluation_not_traceable")
        if outcome_count and not outcome_traceable:
            blocking.append("outcome_not_traceable")
        if accuracy_count and not accuracy_computable:
            blocking.append("accuracy_not_computable")
        if effectiveness_count and not recommendation_effectiveness_computable:
            blocking.append("recommendation_effectiveness_not_computable")
        if benchmark_count and not benchmark_runnable:
            blocking.append("benchmark_not_runnable")
        if improvement_count and not knowledge_improvement_audited:
            blocking.append("knowledge_improvement_not_audited")
        if not no_auto_knowledge_write:
            blocking.append("automatic_knowledge_write")
        if not no_permission_bypass:
            blocking.append("permission_bypass")
        if evaluation_count == 0:
            warning_list.append("no_evaluations_recorded")
        if accuracy_count == 0:
            warning_list.append("no_accuracy_data")
        if blocking:
            status = "BLOCK"
        elif warning_list:
            status = "WARN"
        else:
            status = "PASS"
        valid = sum(1 for value in checks.values() if value is True)
        quality = round(valid / len(checks) * 100)
        return {
            "gate": "13.0",
            "status": status,
            "quality": quality,
            "checks": checks,
            "predictionCount": max(0, int(prediction_count)),
            "evaluationCount": max(0, int(evaluation_count)),
            "outcomeCount": max(0, int(outcome_count)),
            "accuracyCount": max(0, int(accuracy_count)),
            "effectivenessCount": max(0, int(effectiveness_count)),
            "benchmarkCount": max(0, int(benchmark_count)),
            "improvementCount": max(0, int(improvement_count)),
            "blockingIssues": list(dict.fromkeys(blocking)),
            "warnings": warning_list,
            "readOnly": True,
        }


IntelligenceValidationQualityGate = QualityGate13Evaluator
