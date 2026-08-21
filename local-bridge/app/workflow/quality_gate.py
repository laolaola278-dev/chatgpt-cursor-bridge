"""Quality gate validation for the final human approval boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.security.validator import ValidationFailed


_ALLOWED_RISK = {"low", "medium", "high"}


def build_quality_gate(
    *,
    review_status: str,
    test_passed: bool,
    risk_level: str,
    risk_assessment: str,
    reviewer_agent_id: str,
    tester_agent_id: str,
) -> dict[str, Any]:
    review = (review_status or "").strip().lower()
    risk = (risk_level or "").strip().lower()
    assessment = (risk_assessment or "").strip()
    if review not in {"approved", "passed"}:
        raise ValidationFailed("Quality gate review must be approved")
    if not test_passed:
        raise ValidationFailed("Quality gate requires a passing test result")
    if risk not in _ALLOWED_RISK:
        raise ValidationFailed("Quality gate risk level must be low, medium or high")
    if not assessment or len(assessment) > 4000:
        raise ValidationFailed("Quality gate risk assessment must contain 1-4000 characters")
    if not reviewer_agent_id.startswith("ag_") or not tester_agent_id.startswith("ag_"):
        raise ValidationFailed("Quality gate must reference reviewer and tester agents")
    return {
        "reviewStatus": "approved",
        "testPassed": True,
        "riskLevel": risk,
        "riskAssessment": assessment,
        "reviewerAgentId": reviewer_agent_id,
        "testerAgentId": tester_agent_id,
        "readyForHumanApproval": True,
        "submittedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
