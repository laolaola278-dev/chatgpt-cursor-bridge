from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_hex

from app.security.validator import ValidationFailed

from .models import Decision, DecisionStatus
from .storage import IntelligenceStorage


_ALLOWED: dict[DecisionStatus, set[DecisionStatus]] = {
    DecisionStatus.DRAFT: {DecisionStatus.REVIEWING, DecisionStatus.REJECTED, DecisionStatus.ARCHIVED},
    DecisionStatus.REVIEWING: {DecisionStatus.APPROVED, DecisionStatus.REJECTED, DecisionStatus.ARCHIVED},
    DecisionStatus.APPROVED: {DecisionStatus.IMPLEMENTED, DecisionStatus.ARCHIVED},
    DecisionStatus.REJECTED: {DecisionStatus.ARCHIVED},
    DecisionStatus.IMPLEMENTED: {DecisionStatus.ARCHIVED},
    DecisionStatus.ARCHIVED: set(),
}


class DecisionManager:
    def __init__(self, storage: IntelligenceStorage) -> None:
        self.storage = storage

    def create(self, *, project: str, proposal_id: str, title: str, context: str, options: list[dict[str, str]], recommendation: str, simulation_id: str | None = None, selected_scenario: str | None = None, confidence: float | None = None, alternatives: list[str] | None = None, implementation_plan_id: str | None = None, execution_status: str | None = None) -> Decision:
        proposal = self.storage.get_proposal(proposal_id)
        if proposal is None:
            raise ValidationFailed(f"Proposal '{proposal_id}' was not found")
        if proposal.project != project:
            raise ValidationFailed("Decision project does not match proposal project")
        cleaned = [{"name": str(item.get("name", "")).strip(), "risk": str(item.get("risk", "")).strip()} for item in options]
        if len(cleaned) < 2 or any(not item["name"] or not item["risk"] for item in cleaned):
            raise ValidationFailed("Decision options require name and risk")
        if not any(item["name"] == recommendation for item in cleaned):
            raise ValidationFailed("Recommendation must match one decision option")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if confidence is not None and not 0 <= confidence <= 1:
            raise ValidationFailed("Decision confidence must be between 0 and 1")
        decision = Decision(f"decision_{token_hex(8)}", project, proposal_id, title.strip(), context.strip(), cleaned, recommendation.strip(), simulation_id=simulation_id, selected_scenario=selected_scenario, confidence=confidence, alternatives=alternatives or [], implementation_plan_id=implementation_plan_id, execution_status=execution_status, created_at=now, updated_at=now, history=[{"status": DecisionStatus.DRAFT.value, "at": now}])
        self.storage.save_decision(decision)
        return decision

    def transition(self, decision_id: str, target: str) -> Decision:
        decision = self.storage.get_decision(decision_id)
        if decision is None:
            raise ValidationFailed(f"Decision '{decision_id}' was not found")
        try:
            next_status = DecisionStatus(target.upper())
        except ValueError as exc:
            raise ValidationFailed("Unknown decision status") from exc
        if next_status not in _ALLOWED[decision.status]:
            raise ValidationFailed(f"Illegal decision transition {decision.status.value} -> {next_status.value}")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        decision.status = next_status
        decision.updated_at = now
        decision.history.append({"status": next_status.value, "at": now})
        self.storage.save_decision(decision)
        return decision

    @staticmethod
    def memory_content(decision: Decision) -> str:
        options = "\n".join(f"- {item['name']} (risk: {item['risk']})" for item in decision.options)
        return f"## {decision.title}\n\nContext: {decision.context}\n\nOptions:\n{options}\n\nRecommendation: {decision.recommendation}\n\nDecision status: {decision.status.value}\n"
