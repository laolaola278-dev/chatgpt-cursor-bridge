"""Task 6 · Knowledge Improvement Engine.

Closes the validation loop: Prediction -> Outcome -> Evaluation -> Knowledge
Update Proposal -> Human Approval -> Knowledge Improvement.

There is deliberately no automatic path from an evaluation to a memory or
knowledge write. A validated improvement is only a record; converting it into
intelligence knowledge still requires a separate, human-approved knowledge
proposal through the existing ApprovalStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now

from .models import KnowledgeImprovement, KnowledgeImprovementStatus


@dataclass(frozen=True)
class KnowledgeImprovementProposal:
    """Payload of a knowledge improvement proposal awaiting human approval."""

    project_id: str
    evaluation_id: str
    prediction_id: str
    category: str
    content: str
    source: str
    evidence: list[str]
    confidence: float
    reason: str = ""

    def preview(self) -> str:
        return (
            f"[knowledge improvement proposal/{self.category}] "
            f"evaluation={self.evaluation_id} prediction={self.prediction_id} "
            f"confidence={bounded_confidence(self.confidence)} evidence={len(self.evidence)} "
            f"source={sanitize_text(self.source, limit=200)}\n\n"
            f"{sanitize_text(self.content, limit=1200)}"
        )

    def payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "evaluation_id": self.evaluation_id,
            "prediction_id": self.prediction_id,
            "category": self.category,
            "content": self.content,
            "source": self.source,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }


class KnowledgeImprovementEngine:
    def build_proposal(
        self,
        *,
        project_id: str,
        evaluation_id: str,
        prediction_id: str,
        category: str,
        content: str,
        source: str = "evaluation_feedback",
        evidence: list[str] | None = None,
        confidence: float = 0.0,
        reason: str = "",
    ) -> KnowledgeImprovementProposal:
        # Validate eagerly so a malformed proposal never reaches the approval
        # queue; no persistence happens here.
        KnowledgeImprovement(
            improvement_id="proposal_check",
            project_id=project_id,
            evaluation_id=evaluation_id,
            prediction_id=prediction_id,
            category=category,
            content=content,
            source=source,
            evidence=evidence or [],
            confidence=confidence,
            status=KnowledgeImprovementStatus.PROPOSED.value,
            approval_request_id="",
        )
        return KnowledgeImprovementProposal(
            project_id=ensure_project(project_id),
            evaluation_id=sanitize_text(evaluation_id, limit=200),
            prediction_id=sanitize_text(prediction_id, limit=200),
            category=sanitize_text(category, limit=100),
            content=sanitize_text(content, limit=12000),
            source=sanitize_text(source, limit=500),
            evidence=ids(evidence),
            confidence=bounded_confidence(confidence),
            reason=sanitize_text(reason, limit=500),
        )

    def apply_after_approval(
        self,
        *,
        project_id: str,
        evaluation_id: str,
        prediction_id: str,
        category: str,
        content: str,
        source: str,
        evidence: list[str] | None,
        confidence: float,
        approval_request_id: str,
    ) -> KnowledgeImprovement:
        """Persist the improvement record only after a human approval."""
        return KnowledgeImprovement(
            improvement_id=f"improve_{token_hex(8)}",
            project_id=project_id,
            evaluation_id=evaluation_id,
            prediction_id=prediction_id,
            category=category,
            content=content,
            source=source,
            evidence=evidence or [],
            confidence=confidence,
            status=KnowledgeImprovementStatus.VALIDATED.value,
            validated_at=utc_now(),
            approval_request_id=approval_request_id,
        )

    @staticmethod
    def list_improvements(records: Iterable[KnowledgeImprovement], project_id: str, *, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        project = ensure_project(project_id)
        items = [
            record for record in records
            if record.project_id == project and (status is None or record.status == status)
        ]
        items.sort(key=lambda record: record.created_at, reverse=True)
        return [record.as_dict() for record in items[: max(1, min(int(limit), 1000))]]
