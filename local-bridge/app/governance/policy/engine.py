"""Engineering policy engine.

Each rule reads governance signals and emits a PolicyEvaluation with result in
{pass, warning, approval_required}. No rule can stop the execution chain: at
most it raises an approval requirement, which still must be granted by a human
through the ApprovalStore.
"""

from __future__ import annotations

from typing import Any, Callable

from app.security.validator import ValidationFailed

from ..models import PolicyEvaluation
from ..storage import GovernanceStorage

Signal = dict[str, Any]


class _Policy:
    def __init__(self, name: str, rule: Callable[[Signal], PolicyEvaluation]) -> None:
        self.name = name
        self.rule = rule

    def evaluate(self, signal: Signal) -> PolicyEvaluation:
        return self.rule(signal)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _high_risk_requires_review(signal: Signal) -> PolicyEvaluation:
    risk = str(signal.get("risk", "low")).lower()
    if risk == "high":
        return PolicyEvaluation(
            policy="high_risk_change_requires_review",
            result="approval_required",
            severity="high",
            message="High-risk change detected; mandatory human review is required before execution",
            context={"risk": risk},
        )
    return PolicyEvaluation(
        policy="high_risk_change_requires_review",
        result="pass",
        severity="low",
        message="Change risk is within policy bounds",
        context={"risk": risk},
    )


def _test_coverage_warning(signal: Signal) -> PolicyEvaluation:
    coverage = _as_float(signal.get("test_coverage"), 100.0)
    if coverage < 60:
        return PolicyEvaluation(
            policy="test_coverage_drop_warning",
            result="warning",
            severity="medium",
            message=f"Test coverage {coverage:.0f}% is below the 60% policy threshold",
            context={"test_coverage": coverage, "threshold": 60},
        )
    return PolicyEvaluation(
        policy="test_coverage_drop_warning",
        result="pass",
        severity="low",
        message="Test coverage is above the policy threshold",
        context={"test_coverage": coverage},
    )


def _architecture_drift_approval(signal: Signal) -> PolicyEvaluation:
    drift = _as_float(signal.get("drift_score"), 0.0)
    threshold = _as_float(signal.get("drift_threshold"), 50.0)
    if drift > threshold:
        return PolicyEvaluation(
            policy="architecture_drift_approval_required",
            result="approval_required",
            severity="high",
            message=f"Architecture drift {drift:.0f} exceeds threshold {threshold:.0f}; changes require approval",
            context={"drift_score": drift, "threshold": threshold},
        )
    return PolicyEvaluation(
        policy="architecture_drift_approval_required",
        result="pass",
        severity="low",
        message="Architecture drift is within the policy threshold",
        context={"drift_score": drift},
    )


def _rollback_frequency_investigation(signal: Signal) -> PolicyEvaluation:
    rollback_rate = _as_float(signal.get("rollback_rate"), 0.0)
    if rollback_rate > 0.25:
        return PolicyEvaluation(
            policy="rollback_frequency_investigation",
            result="warning",
            severity="high",
            message=f"Rollback rate {rollback_rate:.0%} exceeds 25%; open an investigation before new executions",
            context={"rollback_rate": rollback_rate},
        )
    return PolicyEvaluation(
        policy="rollback_frequency_investigation",
        result="pass",
        severity="low",
        message="Rollback frequency is within policy bounds",
        context={"rollback_rate": rollback_rate},
    )


def _debt_growth_warning(signal: Signal) -> PolicyEvaluation:
    open_debt = int(_as_float(signal.get("open_debt"), 0.0))
    threshold = int(_as_float(signal.get("debt_threshold"), 10.0))
    if open_debt >= threshold:
        return PolicyEvaluation(
            policy="debt_growth_warning",
            result="warning",
            severity="medium",
            message=f"{open_debt} open debt item(s) at or above the {threshold} policy threshold",
            context={"open_debt": open_debt, "threshold": threshold},
        )
    return PolicyEvaluation(
        policy="debt_growth_warning",
        result="pass",
        severity="low",
        message="Open technical debt is within policy bounds",
        context={"open_debt": open_debt},
    )


class PolicyEngine:
    """Registry of engineering policies; evaluation is deterministic and read-only."""

    POLICIES = [
        _Policy("high_risk_change_requires_review", _high_risk_requires_review),
        _Policy("test_coverage_drop_warning", _test_coverage_warning),
        _Policy("architecture_drift_approval_required", _architecture_drift_approval),
        _Policy("rollback_frequency_investigation", _rollback_frequency_investigation),
        _Policy("debt_growth_warning", _debt_growth_warning),
    ]

    def names(self) -> list[str]:
        return [policy.name for policy in self.POLICIES]

    def evaluate(self, signal: Signal) -> list[PolicyEvaluation]:
        if not isinstance(signal, dict):
            raise ValidationFailed("Policy signal must be an object")
        allowed_keys = {
            "risk", "test_coverage", "drift_score", "drift_threshold",
            "rollback_rate", "open_debt", "debt_threshold",
        }
        unexpected = set(signal) - allowed_keys
        if unexpected:
            raise ValidationFailed(f"Unexpected policy signal key(s): {sorted(unexpected)}")
        return [policy.evaluate(signal) for policy in self.POLICIES]

    def evaluate_and_record(
        self, project: str, signal: Signal, storage: GovernanceStorage
    ) -> list[PolicyEvaluation]:
        evaluations = self.evaluate(signal)
        for evaluation in evaluations:
            storage.record_policy_event(project, evaluation)
        return evaluations
