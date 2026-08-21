"""Quality Gate 14.0 - Intelligence Governance integrity.

The gate only evaluates and reports. A BLOCKED result must prevent the
downstream flow of the corresponding intelligence proposal, but the gate
itself never performs or authorizes any write and never bypasses the
existing permission boundary.
"""

from __future__ import annotations

from typing import Any


class QualityGate14Evaluator:
    def evaluate(
        self,
        *,
        prediction_quality: float | None = None,
        prediction_count: int = 0,
        evaluation_quality: bool = True,
        evaluation_count: int = 0,
        recommendation_effectiveness: float | None = None,
        effectiveness_count: int = 0,
        decision_success_rate: float | None = None,
        decision_count: int = 0,
        max_risk_level: str = "LOW",
        max_risk_score: float = 0.0,
        confidence_calibration: float | None = None,
        regression_rate: float | None = None,
        benchmark_score: float | None = None,
        benchmark_count: int = 0,
        policy_compliance: bool = True,
        violation_count: int = 0,
        audit_complete: bool = True,
        blocking_issues: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        blocking = list(dict.fromkeys(str(item) for item in (blocking_issues or [])))
        warning_list = list(dict.fromkeys(str(item) for item in (warnings or [])))

        risk_level = str(max_risk_level or "LOW").upper().strip()
        risk_score = round(max(0.0, min(100.0, float(max_risk_score or 0.0))), 1)

        checks = {
            "predictionQualityComputable": prediction_quality is not None,
            "evaluationQuality": bool(evaluation_quality),
            "recommendationEffectivenessComputable": recommendation_effectiveness is not None,
            "decisionSuccessComputable": decision_success_rate is not None,
            "confidenceCalibrationComputable": confidence_calibration is not None,
            "benchmarkComputable": benchmark_score is not None,
            "policyCompliance": bool(policy_compliance),
            "auditComplete": bool(audit_complete),
        }

        # BLOCKED: the gate must stop the downstream flow of a proposal.
        if risk_level == "CRITICAL" or risk_score >= 80:
            blocking.append("critical_risk_detected")
        if benchmark_score is not None and benchmark_score < 0.4:
            blocking.append("benchmark_below_block_threshold")
        if prediction_quality is not None and prediction_count and prediction_quality < 0.3:
            blocking.append("prediction_quality_below_block_threshold")
        if violation_count and not policy_compliance:
            blocking.append("blocking_policy_violation")
        if (evaluation_count or decision_count or effectiveness_count) and not audit_complete:
            blocking.append("audit_incomplete")

        # REVIEW_REQUIRED: elevated but not blocking signals.
        review_required = False
        if risk_level == "HIGH" or risk_score >= 55:
            review_required = True
        if prediction_quality is not None and prediction_count and prediction_quality < 0.5:
            review_required = True
        if regression_rate is not None and regression_rate > 0.2:
            review_required = True
        if benchmark_score is not None and benchmark_score < 0.6:
            review_required = True
        if violation_count:
            review_required = True

        if evaluation_count == 0:
            warning_list.append("no_evaluations_recorded")
        if prediction_count == 0:
            warning_list.append("no_predictions_recorded")
        if benchmark_count == 0:
            warning_list.append("no_benchmark_runs")
        if confidence_calibration is not None and confidence_calibration > 0.2:
            warning_list.append("confidence_calibration_error_high")

        if blocking:
            status = "BLOCKED"
        elif review_required:
            status = "REVIEW_REQUIRED"
        elif warning_list:
            status = "WARNING"
        else:
            status = "PASS"

        valid = sum(1 for value in checks.values() if value)
        quality = round(valid / len(checks) * 100) if checks else 0
        return {
            "gate": "14.0",
            "status": status,
            "quality": quality,
            "checks": checks,
            "predictionQuality": prediction_quality,
            "predictionCount": max(0, int(prediction_count)),
            "evaluationCount": max(0, int(evaluation_count)),
            "effectivenessCount": max(0, int(effectiveness_count)),
            "decisionCount": max(0, int(decision_count)),
            "maxRiskLevel": risk_level,
            "maxRiskScore": risk_score,
            "confidenceCalibration": confidence_calibration,
            "regressionRate": regression_rate,
            "benchmarkScore": benchmark_score,
            "benchmarkCount": max(0, int(benchmark_count)),
            "violationCount": max(0, int(violation_count)),
            "blockingIssues": blocking,
            "warnings": warning_list,
            "readOnly": True,
        }


IntelligenceGovernanceQualityGate = QualityGate14Evaluator
