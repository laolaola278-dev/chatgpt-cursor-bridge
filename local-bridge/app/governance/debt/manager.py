"""Technical debt lifecycle manager.

Enforces the strict forward chain:

    OPEN -> ANALYZING -> PROPOSED -> APPROVED -> RESOLVED -> VERIFIED

Illegal jumps are rejected. The manager never auto-approves: every status
mutation is performed only after the API layer has routed the request through
the ApprovalStore.
"""

from __future__ import annotations

from typing import Any

from app.security.validator import ValidationFailed

from ..models import DebtItem, DebtStatus
from ..storage import GovernanceStorage

_TRANSITIONS: dict[DebtStatus, set[DebtStatus]] = {
    DebtStatus.OPEN: {DebtStatus.ANALYZING},
    DebtStatus.ANALYZING: {DebtStatus.PROPOSED},
    DebtStatus.PROPOSED: {DebtStatus.APPROVED},
    DebtStatus.APPROVED: {DebtStatus.RESOLVED},
    DebtStatus.RESOLVED: {DebtStatus.VERIFIED},
    DebtStatus.VERIFIED: set(),
}

_VALID_CATEGORIES = {
    "code",
    "architecture",
    "test",
    "dependency",
    "security",
    "performance",
    "documentation",
    "process",
}
_VALID_SEVERITY = {"low", "medium", "high"}
_VALID_RISK = {"low", "medium", "high"}


class DebtManager:
    def __init__(self, storage: GovernanceStorage) -> None:
        self.storage = storage

    def create(
        self,
        project: str,
        *,
        category: str,
        severity: str,
        source: str,
        affected_components: list[str] | None = None,
        estimated_cost: int = 0,
        risk: str = "low",
    ) -> DebtItem:
        category = (category or "").strip().lower()
        severity = (severity or "").strip().lower()
        risk = (risk or "").strip().lower()
        if category not in _VALID_CATEGORIES:
            raise ValidationFailed(f"Unknown debt category '{category}'")
        if severity not in _VALID_SEVERITY:
            raise ValidationFailed(f"Unknown debt severity '{severity}'")
        if risk not in _VALID_RISK:
            raise ValidationFailed(f"Unknown debt risk '{risk}'")
        if not source.strip():
            raise ValidationFailed("Debt source is required")
        estimated_cost = max(0, int(estimated_cost or 0))

        item = DebtItem(
            id=f"debt_{project[:16]}_{DebtManager._stamp()}",
            project=project,
            category=category,
            severity=severity,
            source=source.strip(),
            affected_components=list(dict.fromkeys(affected_components or [])),
            estimated_cost=estimated_cost,
            risk=risk,
            status=DebtStatus.OPEN,
        )
        self.storage.save_debt(item)
        return item

    def transition(self, debt_id: str, status: str) -> DebtItem:
        item = self.storage.get_debt(debt_id)
        if item is None:
            raise ValidationFailed(f"Debt item '{debt_id}' was not found")
        try:
            target = DebtStatus(status.strip().upper())
        except ValueError as exc:
            raise ValidationFailed(f"Unknown debt status '{status}'") from exc
        allowed = _TRANSITIONS.get(item.status, set())
        if target not in allowed:
            raise ValidationFailed(
                f"Illegal debt transition {item.status.value} -> {target.value}"
            )
        return self.storage.update_debt_status(debt_id, target)

    def get(self, debt_id: str) -> DebtItem | None:
        return self.storage.get_debt(debt_id)

    def list(
        self, project: str | None = None, status: str | None = None, limit: int = 200
    ) -> list[DebtItem]:
        return self.storage.list_debt(project=project, status=status, limit=limit)

    @staticmethod
    def _stamp() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[-12:]
