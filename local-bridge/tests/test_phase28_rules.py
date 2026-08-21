"""Phase 28 · Governance Rule Engine + Policy Registry tests."""

from __future__ import annotations

import pytest

from app.intelligence.governance import (
    BUILTIN_POLICIES,
    GovernanceRuleEngine,
    find_policy,
    list_policies,
)
from app.intelligence.governance.rules import POLICY_BY_ID

evaluate = GovernanceRuleEngine().evaluate


def test_pass_when_no_rules_match():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1")
    assert result.governance_result == "PASS"
    assert result.outcomes == []
    assert not result.requires_review
    assert not result.blocking


def test_low_confidence_requires_review():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.2)
    assert result.governance_result == "REVIEW_REQUIRED"
    assert result.requires_review


def test_high_accuracy_passes():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", accuracy=0.9)
    assert result.governance_result == "PASS"


def test_low_accuracy_requires_review():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", accuracy=0.4)
    assert result.governance_result == "REVIEW_REQUIRED"


def test_high_failure_rate_requires_review():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", failure_rate=0.6)
    assert result.governance_result == "REVIEW_REQUIRED"


def test_low_failure_rate_passes():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", failure_rate=0.1)
    assert result.governance_result == "PASS"


def test_regression_above_threshold_requires_review():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", regression_rate=0.3)
    assert result.governance_result == "REVIEW_REQUIRED"


def test_high_rejection_rate_warns():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", rejection_rate=0.9)
    assert result.governance_result == "WARNING"
    assert not result.requires_review


def test_low_rejection_rate_passes():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", rejection_rate=0.2)
    assert result.governance_result == "PASS"


def test_high_risk_requires_review():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", risk_level="HIGH", risk_score=70)
    assert result.governance_result == "REVIEW_REQUIRED"
    assert result.requires_review


def test_critical_risk_blocks():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", risk_level="CRITICAL", risk_score=90)
    assert result.governance_result == "BLOCKED"
    assert result.blocking


def test_sensitive_context_warns():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", context="contains an api key")
    assert result.governance_result == "WARNING"


def test_clean_context_no_warning():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", context="refactor the parser")
    assert result.governance_result == "PASS"


def test_model_reliability_below_threshold_requires_review():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", model_reliability=0.3)
    assert result.governance_result == "REVIEW_REQUIRED"


def test_model_reliability_above_threshold_passes():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", model_reliability=0.8)
    assert result.governance_result == "PASS"


def test_matched_policies_recorded():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.2)
    assert "p_confidence_threshold" in result.matched_policies


def test_outcomes_carry_policy_metadata():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.2)
    outcome = result.outcomes[0]
    assert outcome.policy_id == "p_confidence_threshold"
    assert outcome.status == "REVIEW_REQUIRED"
    assert "0.2" in outcome.reason


def test_evaluation_is_deterministic():
    kwargs = dict(project="demo", source_kind="prediction", source_id="p1", confidence=0.2, risk_level="HIGH")
    assert evaluate(**kwargs).as_dict() == evaluate(**kwargs).as_dict()


def test_evaluation_is_readonly():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.2)
    assert result.as_dict()["readOnly"] is True


def test_disabled_policy_not_applied():
    from app.intelligence.governance.rules import PolicyRule

    disabled = PolicyRule(
        policy_id="p_test_disabled", name="Disabled", description="",
        rule_key="confidence_below_threshold", severity="warning", threshold=0.9,
        scope="global", scope_value="*", enabled=False, version=1,
    )
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.1, policies=[disabled])
    assert result.governance_result == "PASS"


def test_scope_filtered_policy_not_applied():
    from app.intelligence.governance.rules import PolicyRule

    scoped = PolicyRule(
        policy_id="p_test_scoped", name="Scoped", description="",
        rule_key="confidence_below_threshold", severity="warning", threshold=0.9,
        scope="model", scope_value="gpt-9", enabled=True, version=1,
    )
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.1, policies=[scoped])
    assert result.governance_result == "PASS"


def test_scope_match_applies():
    from app.intelligence.governance.rules import PolicyRule

    scoped = PolicyRule(
        policy_id="p_test_scoped", name="Scoped", description="",
        rule_key="confidence_below_threshold", severity="warning", threshold=0.9,
        scope="kind", scope_value="prediction", enabled=True, version=1,
    )
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.1, policies=[scoped])
    assert result.governance_result == "REVIEW_REQUIRED"


def test_warning_beats_nothing_review_beats_warning():
    warning = evaluate(project="demo", source_kind="prediction", source_id="p1", rejection_rate=0.9)
    review = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.2, rejection_rate=0.9)
    assert warning.governance_result == "WARNING"
    assert review.governance_result == "REVIEW_REQUIRED"


def test_blocked_beats_review():
    result = evaluate(
        project="demo", source_kind="prediction", source_id="p1",
        risk_level="CRITICAL", risk_score=90, confidence=0.2,
    )
    assert result.governance_result == "BLOCKED"


def test_builtin_policies_registered():
    assert len(BUILTIN_POLICIES) >= 8
    assert len(POLICY_BY_ID) == len(BUILTIN_POLICIES)


def test_find_policy():
    policy = find_policy("p_accuracy_threshold")
    assert policy is not None
    assert policy.rule_key == "accuracy_below_threshold"
    assert find_policy("p_missing") is None


def test_list_policies_global_scope():
    policies = list_policies(scope="global")
    assert all(policy.scope == "global" for policy in policies)
    assert len(policies) == len(BUILTIN_POLICIES)


def test_list_policies_model_scope():
    policies = list_policies(scope="model")
    assert all(policy.scope in ("model", "global") for policy in policies)


def test_policy_versioned():
    assert all(policy.version >= 1 for policy in BUILTIN_POLICIES)


def test_policy_has_thresholds():
    assert all(policy.threshold >= 0.0 for policy in BUILTIN_POLICIES)


def test_policy_severity_in_known_set():
    for policy in BUILTIN_POLICIES:
        assert policy.severity in ("info", "warning", "blocking")


def test_policy_as_dict_snake_and_camel():
    data = BUILTIN_POLICIES[0].as_dict()
    assert data["policy_id"] == data["policyId"]
    assert data["readOnly"] is True


def test_accuracy_threshold_value():
    assert find_policy("p_accuracy_threshold").threshold == 0.5


def test_confidence_threshold_value():
    assert find_policy("p_confidence_threshold").threshold == 0.3


def test_high_risk_threshold_value():
    assert find_policy("p_high_risk_operation").threshold == 60.0


def test_high_risk_operation_is_blocking_severity():
    assert find_policy("p_high_risk_operation").severity == "blocking"


def test_rule_engine_never_approves():
    result = evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=0.1, risk_level="CRITICAL")
    assert result.governance_result in ("PASS", "WARNING", "REVIEW_REQUIRED", "BLOCKED")
    assert "approved" not in result.governance_result.lower()


@pytest.mark.parametrize("confidence", [0.1, 0.2, 0.29])
def test_confidence_rule_boundary(confidence):
    assert evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=confidence).requires_review


@pytest.mark.parametrize("confidence", [0.3, 0.5, 0.9])
def test_confidence_rule_above_boundary(confidence):
    assert not evaluate(project="demo", source_kind="prediction", source_id="p1", confidence=confidence).requires_review


@pytest.mark.parametrize("accuracy", [0.1, 0.3, 0.49])
def test_accuracy_rule_boundary(accuracy):
    assert evaluate(project="demo", source_kind="prediction", source_id="p1", accuracy=accuracy).requires_review


@pytest.mark.parametrize("accuracy", [0.5, 0.75, 1.0])
def test_accuracy_rule_above_boundary(accuracy):
    assert not evaluate(project="demo", source_kind="prediction", source_id="p1", accuracy=accuracy).requires_review


@pytest.mark.parametrize("failure_rate", [0.41, 0.6, 0.9])
def test_failure_rate_boundary(failure_rate):
    assert evaluate(project="demo", source_kind="prediction", source_id="p1", failure_rate=failure_rate).requires_review


@pytest.mark.parametrize("failure_rate", [0.1, 0.3, 0.4])
def test_failure_rate_above_boundary(failure_rate):
    assert not evaluate(project="demo", source_kind="prediction", source_id="p1", failure_rate=failure_rate).requires_review
