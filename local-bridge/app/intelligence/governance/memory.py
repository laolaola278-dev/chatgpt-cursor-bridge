"""Phase 28 · Governance Memory.

Governance memory only stores governance findings, risk findings, quality
findings, policy violations, review outcomes, and historical governance
decisions. Every write must pass Governance Proposal -> ApprovalStore ->
Human Approval. There is no automatic governance memory write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.intelligence.common import bounded_confidence, utc_now
from app.intelligence.governance.models import (
    GOVERNANCE_MEMORY_CATEGORIES,
    GovernanceMemoryRecord,
)


@dataclass(frozen=True)
class GovernanceMemoryProposal:
    project_id: str
    category: str
    content: str
    source: str
    evidence: list[str]
    confidence: float

    def payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "category": self.category,
            "content": self.content,
            "source": self.source,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }

    def preview(self) -> str:
        return f"APPEND governance memory ({self.category}) for {self.project_id}: governance findings only; no engineering memory mutation"


class GovernanceMemory:
    def build_proposal(
        self,
        *,
        project_id: str,
        category: str,
        content: str,
        source: str = "governance_analysis",
        evidence: list[str] | None = None,
        confidence: float = 0.0,
    ) -> GovernanceMemoryProposal:
        if category not in GOVERNANCE_MEMORY_CATEGORIES:
            raise ValueError(f"Unknown governance memory category: {category}")
        return GovernanceMemoryProposal(
            project_id=project_id,
            category=category,
            content=content,
            source=source,
            evidence=list(evidence or []),
            confidence=bounded_confidence(confidence),
        )

    def apply_after_approval(
        self,
        *,
        project_id: str,
        category: str,
        content: str,
        source: str = "governance_analysis",
        evidence: list[str] | None = None,
        confidence: float = 0.0,
        approval_request_id: str = "",
    ) -> GovernanceMemoryRecord:
        if category not in GOVERNANCE_MEMORY_CATEGORIES:
            raise ValueError(f"Unknown governance memory category: {category}")
        return GovernanceMemoryRecord(
            memory_id="",
            project_id=project_id,
            category=category,
            content=content,
            source=source,
            confidence=confidence,
            evidence=list(evidence or []),
            created_at=utc_now(),
            approval_request_id=approval_request_id,
        )


GovernanceMemoryEngine = GovernanceMemory
