"""Phase 28 · Quality Gate 14.0 tests."""

from __future__ import annotations

import pytest

from app.quality.gate14 import QualityGate14Evaluator

evaluate = QualityGate14Evaluator().evaluate


def test_empty_data_warns_not_fails():
    report = evaluate()
    assert report["status"] == "WARNING"
    assert "no_evaluations_recorded" in report["warnings"]


def test_healthy_data_passes():
    report = evaluate(
        prediction_quality=0.85, prediction_count=100,
        evaluation_quality=True, evaluation_count=100,
        recommendation_effectiveness=0.8, effectiveness_count=50,
        decision_success_rate=0.9, decision_count=40,
        max_risk_level="LOW", max_risk_score=10.0,
        confidence_calibration=0.05,
        regression_rate=0.1, benchmark_score=0.85, benchmark_count=3,
        policy_compliance=True, violation_count=0, audit_complete=True,
    )
    assert report["status"] == "PASS"


def test_critical_risk_blocks():
    report = evaluate(max_risk_level="CRITICAL", max_risk_score=90)
    assert report["status"] == "BLOCKED"
    assert "critical_risk_detected" in report["blockingIssues"]


def test_high_risk_requires_review():
    report = evaluate(max_risk_level="HIGH", max_risk_score=70)
    assert report["status"] == "REVIEW_REQUIRED"


def test_low_risk_allows_pass():
    report = evaluate(max_risk_level="LOW", max_risk_score=10)
    assert report["status"] in ("PASS", "WARNING")


def test_low_accuracy_blocks():
    report = evaluate(prediction_quality=0.2, prediction_count=50)
    assert report["status"] == "BLOCKED"
    assert "prediction_quality_below_block_threshold" in report["blockingIssues"]


def test_mid_accuracy_requires_review():
    report = evaluate(prediction_quality=0.4, prediction_count=50)
    assert report["status"] == "REVIEW_REQUIRED"


def test_high_accuracy_does_not_block():
    report = evaluate(prediction_quality=0.9, prediction_count=50)
    assert report["status"] in ("PASS", "WARNING")


def test_low_benchmark_blocks():
    report = evaluate(benchmark_score=0.3, benchmark_count=2)
    assert report["status"] == "BLOCKED"
    assert "benchmark_below_block_threshold" in report["blockingIssues"]


def test_medium_benchmark_requires_review():
    report = evaluate(benchmark_score=0.5, benchmark_count=2)
    assert report["status"] == "REVIEW_REQUIRED"


def test_high_benchmark_passes():
    report = evaluate(benchmark_score=0.9, benchmark_count=2)
    assert report["status"] in ("PASS", "WARNING")


def test_policy_violation_blocks_when_non_compliant():
    report = evaluate(policy_compliance=False, violation_count=1)
    assert report["status"] == "BLOCKED"
    assert "blocking_policy_violation" in report["blockingIssues"]


def test_violation_without_blocking_severity_requires_review():
    report = evaluate(policy_compliance=True, violation_count=2)
    assert report["status"] == "REVIEW_REQUIRED"


def test_audit_incomplete_blocks():
    report = evaluate(evaluation_count=5, audit_complete=False)
    assert report["status"] == "BLOCKED"
    assert "audit_incomplete" in report["blockingIssues"]


def test_audit_complete_passes_with_data():
    report = evaluate(
        prediction_quality=0.8, prediction_count=5, evaluation_count=5,
        audit_complete=True, benchmark_score=0.9, benchmark_count=1,
    )
    assert report["status"] == "PASS"


def test_regression_rate_above_threshold_requires_review():
    report = evaluate(regression_rate=0.3)
    assert report["status"] == "REVIEW_REQUIRED"


def test_regression_rate_below_threshold_passes():
    report = evaluate(regression_rate=0.05)
    assert report["status"] in ("PASS", "WARNING")


def test_high_calibration_error_warns():
    report = evaluate(confidence_calibration=0.35)
    assert "confidence_calibration_error_high" in report["warnings"]


def test_low_calibration_error_no_warning():
    report = evaluate(confidence_calibration=0.05)
    assert "confidence_calibration_error_high" not in report["warnings"]


def test_gate_version():
    assert evaluate()["gate"] == "14.0"


def test_gate_readonly():
    assert evaluate()["readOnly"] is True


def test_quality_score_present():
    report = evaluate()
    assert 0 <= report["quality"] <= 100


def test_counts_reported():
    report = evaluate(prediction_count=10, evaluation_count=5, benchmark_count=2, violation_count=3)
    assert report["predictionCount"] == 10
    assert report["evaluationCount"] == 5
    assert report["benchmarkCount"] == 2
    assert report["violationCount"] == 3


def test_risk_reported():
    report = evaluate(max_risk_level="HIGH", max_risk_score=72.0)
    assert report["maxRiskLevel"] == "HIGH"
    assert report["maxRiskScore"] == 72.0


def test_checks_exposed():
    report = evaluate()
    assert report["checks"]["auditComplete"] is True
    assert report["checks"]["policyCompliance"] is True


def test_blocking_issues_deduplicated():
    report = evaluate(max_risk_level="CRITICAL", blocking_issues=["x", "x"])
    assert report["blockingIssues"].count("x") == 1


def test_warnings_deduplicated():
    report = evaluate(warnings=["w", "w"])
    assert report["warnings"].count("w") == 1


def test_no_benchmark_runs_warns():
    report = evaluate(benchmark_count=0)
    assert "no_benchmark_runs" in report["warnings"]


def test_no_predictions_warns():
    report = evaluate(prediction_count=0)
    assert "no_predictions_recorded" in report["warnings"]


def test_status_priority_blocked_over_review():
    report = evaluate(max_risk_level="CRITICAL", prediction_quality=0.4, prediction_count=10)
    assert report["status"] == "BLOCKED"


def test_status_priority_review_over_warning():
    report = evaluate(max_risk_level="HIGH", benchmark_count=0)
    assert report["status"] == "REVIEW_REQUIRED"


def test_prediction_quality_optional():
    report = evaluate(prediction_count=5)
    assert report["predictionQuality"] is None


def test_gate_does_not_mutate():
    before = evaluate()
    after = evaluate()
    assert before == after


@pytest.mark.parametrize("benchmark_score", [0.0, 0.2, 0.39])
def test_benchmark_block_zone(benchmark_score):
    assert evaluate(benchmark_score=benchmark_score, benchmark_count=1)["status"] == "BLOCKED"


@pytest.mark.parametrize("benchmark_score", [0.4, 0.5, 0.59])
def test_benchmark_review_zone(benchmark_score):
    assert evaluate(benchmark_score=benchmark_score, benchmark_count=1)["status"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("benchmark_score", [0.6, 0.8, 1.0])
def test_benchmark_pass_zone(benchmark_score):
    assert evaluate(benchmark_score=benchmark_score, benchmark_count=1)["status"] in ("PASS", "WARNING")


@pytest.mark.parametrize("prediction_quality", [0.0, 0.1, 0.29])
def test_accuracy_block_zone(prediction_quality):
    assert evaluate(prediction_quality=prediction_quality, prediction_count=10)["status"] == "BLOCKED"


@pytest.mark.parametrize("prediction_quality", [0.3, 0.4, 0.49])
def test_accuracy_review_zone(prediction_quality):
    assert evaluate(prediction_quality=prediction_quality, prediction_count=10)["status"] == "REVIEW_REQUIRED"
