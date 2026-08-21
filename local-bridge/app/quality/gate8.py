from __future__ import annotations

from typing import Any


class QualityGate8Evaluator:
    """Quality Gate 8.0 for the approval-controlled execution loop.

    Blocking conditions: no approval, no snapshot, verification failed, or
    risk level HIGH. Evaluation is read-only and deterministic.
    """

    def evaluate(
        self,
        *,
        approval_present: bool = False,
        snapshot_present: bool = False,
        verification_status: str | None = None,
        risk_level: str = "low",
        rollback_capability: bool = False,
        test_result: str | None = None,
        confidence: int = 0,
    ) -> dict[str, Any]:
        issues: list[str] = []
        if not approval_present:
            issues.append("no_approval")
        if not snapshot_present:
            issues.append("no_snapshot")
        if verification_status is not None and verification_status != "PASS":
            issues.append(f"verification_{verification_status.lower()}")
        risk = (risk_level or "low").lower()
        if risk not in {"low", "medium", "high"}:
            risk = "high"
        if risk == "high":
            issues.append("risk_high")
        if test_result is not None and test_result != "passed":
            issues.append("tests_failed")

        confidence = max(0, min(100, confidence))
        penalty = min(100, len(issues) * 20 + (30 if risk == "high" else 0))
        quality = max(0, min(100, confidence - penalty))
        execution_ready = not issues
        recommendation = (
            "loop_ready"
            if execution_ready
            else "resolve_blocking_issues"
            if risk != "high"
            else "do_not_execute"
        )
        return {
            "quality": quality,
            "executionReady": execution_ready,
            "confidence": confidence,
            "riskLevel": risk,
            "blockingIssues": issues,
            "rollbackCapability": bool(rollback_capability),
            "testResult": test_result,
            "recommendation": recommendation,
            "readOnly": True,
        }
