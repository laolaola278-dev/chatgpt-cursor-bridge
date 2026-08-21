"""Phase 28 · Governance Review Proposals.

A review proposal is created when a high/critical risk, quality gate failure,
accuracy degradation, regression, policy violation, or model reliability
degradation is detected. Proposals only enter the ApprovalStore for human
review; there is no automatic approval path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.intelligence.common import bounded_confidence, utc_now
from app.intelligence.governance.models import (
    RISK_LEVELS,
    ReviewProposal,
    ReviewStatus,
)


@dataclass(frozen=True)
class ReviewProposalDraft:
    project_id: str
    source_id: str
    source_kind: str
    risk_level: str
    reason: str
    recommended_action: str
    confidence: float
    evidence: list[str]

    def payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }

    def preview(self) -> str:
        return f"REVIEW {self.source_kind} {self.source_id} for {self.project_id}: risk={self.risk_level} reason={self.reason}; human review required"


class GovernanceReviewEngine:
    """Builds review proposals from detected governance signals."""

    def should_propose(
        self,
        *,
        risk_level: str = "LOW",
        risk_score: float = 0.0,
        governance_result: str = "PASS",
        accuracy_degraded: bool = False,
        regression_detected: bool = False,
        violation_detected: bool = False,
        model_degraded: bool = False,
    ) -> bool:
        if risk_level in ("HIGH", "CRITICAL") or risk_score >= 60:
            return True
        if governance_result in ("REVIEW_REQUIRED", "BLOCKED"):
            return True
        return any((accuracy_degraded, regression_detected, violation_detected, model_degraded))

    def build_proposal(
        self,
        *,
        project_id: str,
        source_id: str,
        source_kind: str,
        risk_level: str,
        reason: str,
        recommended_action: str,
        confidence: float = 0.0,
        evidence: list[str] | None = None,
    ) -> ReviewProposalDraft:
        risk_level = str(risk_level).upper().strip()
        if risk_level not in RISK_LEVELS:
            risk_level = "LOW"
        return ReviewProposalDraft(
            project_id=project_id,
            source_id=source_id,
            source_kind=source_kind,
            risk_level=risk_level,
            reason=reason,
            recommended_action=recommended_action,
            confidence=bounded_confidence(confidence),
            evidence=list(evidence or []),
        )

    def create_record(self, draft: ReviewProposalDraft) -> ReviewProposal:
        """Persist the audit record for a freshly proposed review."""
        return ReviewProposal(
            proposal_id="",
            project_id=draft.project_id,
            source_id=draft.source_id,
            source_kind=draft.source_kind,
            risk_level=draft.risk_level,
            reason=draft.reason,
            recommended_action=draft.recommended_action,
            confidence=draft.confidence,
            evidence=draft.evidence,
            status=ReviewStatus.PROPOSED.value,
            created_at=utc_now(),
        )

    def apply_review(
        self,
        *,
        proposal_id: str,
        project_id: str,
        source_id: str,
        source_kind: str,
        risk_level: str,
        reason: str,
        recommended_action: str,
        confidence: float,
        evidence: list[str],
        decision: str,
        reviewer_note: str = "",
        approval_request_id: str = "",
    ) -> ReviewProposal:
        decision = str(decision).lower().strip()
        if decision not in (ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value):
            raise ValueError(f"Unknown review decision: {decision}")
        return ReviewProposal(
            proposal_id=proposal_id,
            project_id=project_id,
            source_id=source_id,
            source_kind=source_kind,
            risk_level=risk_level,
            reason=reason,
            recommended_action=recommended_action,
            confidence=confidence,
            evidence=evidence,
            status=decision,
            created_at=utc_now(),
            resolved_at=utc_now(),
            audit_request_id=approval_request_id,
            reviewer_note=reviewer_note,
        )


GovernanceReviewProposals = GovernanceReviewEngine
