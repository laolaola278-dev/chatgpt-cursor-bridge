"""Phase 28 · Governance Rule Engine and Policy Registry.

The rule engine evaluates an intelligence claim against deterministic policy
rules. It can only produce a Warning or an Approval Requirement (and therefore
a Review Proposal). It never blocks, approves, executes, or mutates anything
by itself.

Policies are versioned, read-only registry entries. The intelligence layer has
no endpoint that mutates a policy; changing governance rules remains an
operator action outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.intelligence.common import utc_now
from app.intelligence.governance.models import (
    GovernanceResult,
    PolicySeverity,
    RiskLevel,
)

_SENSITIVE_KEYWORDS = (
    "api key",
    "api_key",
    "secret",
    "credential",
    "password",
    "private key",
    "authorization",
    "bearer ",
    "token",
)


@dataclass(frozen=True)
class PolicyRule:
    """A versioned, read-only governance policy entry."""

    policy_id: str
    name: str
    description: str
    rule_key: str
    severity: str
    threshold: float
    scope: str
    scope_value: str
    enabled: bool
    version: int
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id, "policyId": self.policy_id,
            "name": self.name, "description": self.description,
            "rule_key": self.rule_key, "ruleKey": self.rule_key,
            "severity": self.severity, "threshold": self.threshold,
            "scope": self.scope, "scope_value": self.scope_value,
            "scopeValue": self.scope_value, "enabled": self.enabled,
            "version": self.version, "created_at": self.created_at,
            "createdAt": self.created_at, "updated_at": self.updated_at,
            "updatedAt": self.updated_at, "readOnly": True,
        }


def _policy(
    policy_id: str,
    name: str,
    description: str,
    rule_key: str,
    severity: str,
    threshold: float,
    scope: str = "global",
    scope_value: str = "*",
    version: int = 1,
) -> PolicyRule:
    now = utc_now()
    return PolicyRule(
        policy_id=policy_id,
        name=name,
        description=description,
        rule_key=rule_key,
        severity=severity,
        threshold=threshold,
        scope=scope,
        scope_value=scope_value,
        enabled=True,
        version=version,
        created_at=now,
        updated_at=now,
    )


BUILTIN_POLICIES: tuple[PolicyRule, ...] = (
    _policy(
        "p_confidence_threshold",
        "Confidence threshold",
        "Predictions below the confidence threshold require review",
        "confidence_below_threshold",
        PolicySeverity.WARNING.value,
        0.3,
    ),
    _policy(
        "p_accuracy_threshold",
        "Accuracy threshold",
        "Project prediction accuracy below the threshold requires review",
        "accuracy_below_threshold",
        PolicySeverity.WARNING.value,
        0.5,
    ),
    _policy(
        "p_failure_rate",
        "Failure rate threshold",
        "A high prediction failure rate requires review",
        "failure_rate_above_threshold",
        PolicySeverity.WARNING.value,
        0.4,
    ),
    _policy(
        "p_regression_threshold",
        "Regression threshold",
        "A detected regression rate above the threshold requires review",
        "regression_above_threshold",
        PolicySeverity.WARNING.value,
        0.2,
    ),
    _policy(
        "p_rejection_rate",
        "Recommendation rejection rate",
        "A very high human rejection rate is a warning signal",
        "recommendation_rejection_above",
        PolicySeverity.INFO.value,
        0.7,
    ),
    _policy(
        "p_high_risk_operation",
        "High risk operation",
        "HIGH/CRITICAL risk claims always generate a governance review proposal",
        "high_risk_detected",
        PolicySeverity.BLOCKING.value,
        60.0,
    ),
    _policy(
        "p_sensitive_context",
        "Sensitive context",
        "Claims built on credential/secret-adjacent context get a warning",
        "sensitive_context_detected",
        PolicySeverity.WARNING.value,
        1.0,
    ),
    _policy(
        "p_model_reliability",
        "Model reliability threshold",
        "Model benchmark reliability below the threshold requires review",
        "model_reliability_below",
        PolicySeverity.WARNING.value,
        0.5,
    ),
)

POLICY_BY_ID: dict[str, PolicyRule] = {policy.policy_id: policy for policy in BUILTIN_POLICIES}


def list_policies(*, scope: str | None = None, enabled_only: bool = True) -> list[PolicyRule]:
    result = [policy for policy in BUILTIN_POLICIES if (not enabled_only or policy.enabled)]
    if scope:
        result = [policy for policy in result if policy.scope == scope or policy.scope == "global"]
    return result


def find_policy(policy_id: str) -> PolicyRule | None:
    return POLICY_BY_ID.get(policy_id)


@dataclass(frozen=True)
class RuleOutcome:
    policy_id: str
    policy_name: str
    severity: str
    status: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id, "policyId": self.policy_id,
            "policy_name": self.policy_name, "policyName": self.policy_name,
            "severity": self.severity, "status": self.status,
            "reason": self.reason, "readOnly": True,
        }


@dataclass(frozen=True)
class RuleEvaluation:
    project: str
    source_kind: str
    source_id: str
    governance_result: str
    outcomes: list[RuleOutcome] = field(default_factory=list)
    matched_policies: list[str] = field(default_factory=list)
    requires_review: bool = False
    blocking: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "source_kind": self.source_kind, "sourceKind": self.source_kind,
            "source_id": self.source_id, "sourceId": self.source_id,
            "governance_result": self.governance_result, "governanceResult": self.governance_result,
            "outcomes": [item.as_dict() for item in self.outcomes],
            "matched_policies": list(self.matched_policies),
            "matchedPolicies": list(self.matched_policies),
            "requires_review": self.requires_review, "requiresReview": self.requires_review,
            "blocking": self.blocking, "readOnly": True,
        }


class GovernanceRuleEngine:
    """Deterministic evaluation of an intelligence claim against policies.

    Inputs mirror the risk analyzer inputs. The engine never writes anything;
    callers decide whether to persist a record or raise a review proposal.
    """

    def evaluate(
        self,
        *,
        project: str,
        source_kind: str,
        source_id: str,
        confidence: float = 0.5,
        risk_level: str = RiskLevel.LOW.value,
        risk_score: float = 0.0,
        accuracy: float | None = None,
        failure_rate: float | None = None,
        regression_rate: float | None = None,
        rejection_rate: float | None = None,
        model_reliability: float | None = None,
        context: str = "",
        policies: list[PolicyRule] | None = None,
    ) -> RuleEvaluation:
        policies = policies if policies is not None else list_policies()
        outcomes: list[RuleOutcome] = []
        matched: list[str] = []
        requires_review = False
        has_blocking = False

        for policy in policies:
            if not policy.enabled:
                continue
            if policy.scope != "global" and policy.scope_value not in ("*", source_kind, source_id):
                continue
            status: str | None = None
            reason = ""
            if policy.rule_key == "confidence_below_threshold":
                if confidence < policy.threshold:
                    status, reason = GovernanceResult.REVIEW_REQUIRED.value, f"Confidence {confidence} below threshold {policy.threshold}"
            elif policy.rule_key == "accuracy_below_threshold":
                if accuracy is not None and accuracy < policy.threshold:
                    status, reason = GovernanceResult.REVIEW_REQUIRED.value, f"Accuracy {accuracy} below threshold {policy.threshold}"
            elif policy.rule_key == "failure_rate_above_threshold":
                if failure_rate is not None and failure_rate > policy.threshold:
                    status, reason = GovernanceResult.REVIEW_REQUIRED.value, f"Failure rate {failure_rate} above threshold {policy.threshold}"
            elif policy.rule_key == "regression_above_threshold":
                if regression_rate is not None and regression_rate > policy.threshold:
                    status, reason = GovernanceResult.REVIEW_REQUIRED.value, f"Regression rate {regression_rate} above threshold {policy.threshold}"
            elif policy.rule_key == "recommendation_rejection_above":
                if rejection_rate is not None and rejection_rate > policy.threshold:
                    status, reason = GovernanceResult.WARNING.value, f"Rejection rate {rejection_rate} above threshold {policy.threshold}"
            elif policy.rule_key == "high_risk_detected":
                if risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value) or risk_score >= policy.threshold:
                    status, reason = GovernanceResult.REVIEW_REQUIRED.value, f"High risk operation detected ({risk_level}, score {risk_score})"
                    if risk_level == RiskLevel.CRITICAL.value or risk_score >= 80:
                        has_blocking = True
            elif policy.rule_key == "sensitive_context_detected":
                lowered = (context or "").lower()
                if any(keyword in lowered for keyword in _SENSITIVE_KEYWORDS):
                    status, reason = GovernanceResult.WARNING.value, "Sensitive context detected in claim input"
            elif policy.rule_key == "model_reliability_below":
                if model_reliability is not None and model_reliability < policy.threshold:
                    status, reason = GovernanceResult.REVIEW_REQUIRED.value, f"Model reliability {model_reliability} below threshold {policy.threshold}"
            if status is not None:
                outcomes.append(
                    RuleOutcome(
                        policy_id=policy.policy_id,
                        policy_name=policy.name,
                        severity=policy.severity,
                        status=status,
                        reason=reason,
                    )
                )
                matched.append(policy.policy_id)
                if status == GovernanceResult.REVIEW_REQUIRED.value:
                    requires_review = True

        if has_blocking:
            governance_result = GovernanceResult.BLOCKED.value
            blocking = True
        elif requires_review:
            governance_result = GovernanceResult.REVIEW_REQUIRED.value
            blocking = False
        elif outcomes:
            governance_result = GovernanceResult.WARNING.value
            blocking = False
        else:
            governance_result = GovernanceResult.PASS.value
            blocking = False

        return RuleEvaluation(
            project=project,
            source_kind=source_kind,
            source_id=source_id,
            governance_result=governance_result,
            outcomes=outcomes,
            matched_policies=matched,
            requires_review=requires_review,
            blocking=blocking,
        )


GovernanceRuleEvaluator = GovernanceRuleEngine
GovernancePolicyRegistry = list_policies
