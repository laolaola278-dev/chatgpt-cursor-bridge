"""Organization Decision Manager (Phase 24).

Manages the organization decision lifecycle over the existing ApprovalStore
boundary: creating or transitioning a decision only happens after a human
approves the corresponding request. The state machine is strict - illegal
transitions are rejected - and every decision binds its source graph nodes,
impact report, risk report, selected strategy, alternatives and confidence.
"""

from __future__ import annotations

from typing import Any

from app.security.validator import ResourceNotFound, ValidationFailed

from .models import DECISION_TRANSITIONS, OrganizationDecision
from .storage import OrganizationStrategyStorage


class OrganizationDecisionManager:
    def __init__(self, storage: OrganizationStrategyStorage) -> None:
        self.storage = storage

    def create(
        self,
        *,
        organization_id: str,
        title: str,
        source_graph_nodes: list[str],
        selected_strategy: str,
        alternatives: list[str],
        confidence: float,
        impact_report: dict[str, Any],
        risk_report: dict[str, Any],
    ) -> OrganizationDecision:
        title = (title or "").strip()
        if not title:
            raise ValidationFailed("Decision title must not be empty")
        decision = OrganizationDecision(
            organization_id=(organization_id or "organization").strip(),
            title=title,
            source_graph_nodes=source_graph_nodes,
            selected_strategy=selected_strategy,
            alternatives=alternatives,
            confidence=max(0.0, min(1.0, float(confidence))),
            impact_report=impact_report,
            risk_report=risk_report,
        )
        self.storage.save_decision(decision)
        return decision

    def get(self, decision_id: str) -> OrganizationDecision:
        decision = self.storage.get_decision(decision_id)
        if decision is None:
            raise ResourceNotFound(f"Organization decision '{decision_id}' was not found")
        return decision

    def transition(self, decision_id: str, target: str) -> OrganizationDecision:
        decision = self.get(decision_id)
        cleaned = (target or "").strip().upper()
        if cleaned not in DECISION_TRANSITIONS:
            raise ValidationFailed(f"Unknown decision status '{target}'")
        try:
            decision.transition(cleaned)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
        self.storage.save_decision(decision)
        return decision
