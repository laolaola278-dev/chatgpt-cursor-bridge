"""Quality Gate 9.0 - governance quality gate.

Combines engineering health, architecture risk, technical debt and policy
violations into a single read-only score. Compatible with earlier gates: all
outputs are additive and it never gates or blocks execution by itself.
"""

from __future__ import annotations

from typing import Any


class QualityGate9Evaluator:
    """Governance quality gate over health, drift, debt and policy signals."""

    def evaluate(
        self,
        *,
        health_score: int = 100,
        architecture_risk: str = "low",
        debt_score: int = 0,
        policy_violations: int = 0,
        recommendations: list[str] | None = None,
        blocking_issues: list[str] | None = None,
    ) -> dict[str, Any]:
        health_score = max(0, min(100, int(health_score)))
        debt_score = max(0, min(100, int(debt_score)))
        policy_violations = max(0, int(policy_violations))
        risk = (architecture_risk or "low").lower()
        if risk not in {"low", "medium", "high"}:
            risk = "high"

        blocking: list[str] = list(blocking_issues or [])
        if health_score < 50:
            blocking.append("health_critical")
        if risk == "high":
            blocking.append("architecture_risk_high")
        if debt_score >= 60:
            blocking.append("debt_score_high")
        if policy_violations >= 2:
            blocking.append("policy_violations")

        penalty = min(
            100,
            (100 - health_score) * 0.5
            + debt_score * 0.3
            + policy_violations * 5
            + (20 if risk == "high" else 10 if risk == "medium" else 0),
        )
        quality = max(0, min(100, int(round(health_score - penalty))))

        return {
            "healthScore": health_score,
            "architectureRisk": risk,
            "debtScore": debt_score,
            "policyViolations": policy_violations,
            "recommendations": list(dict.fromkeys(recommendations or [])),
            "blockingIssues": list(dict.fromkeys(blocking)),
            "quality": quality,
            "readOnly": True,
        }
