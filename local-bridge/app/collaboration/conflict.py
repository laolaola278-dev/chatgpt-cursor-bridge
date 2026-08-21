"""Conflict records never self-resolve."""
from __future__ import annotations

from datetime import datetime, timezone

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel
from app.security.validator import ApprovalError, ValidationFailed

from .models import ConflictRecord
from .storage import CollaborationStorage


class ConflictManager:
    def __init__(self, storage: CollaborationStorage, audit: AuditLogger | None = None) -> None: self.storage, self.audit = storage, audit

    def create(self, *, workflow_id: str, task_id: str, agents: list[str], issue: str, options: list[str]) -> ConflictRecord:
        conflict = ConflictRecord.create(workflow_id=workflow_id, task_id=task_id, agents=agents, issue=issue, options=options)
        self.storage.append_conflict(conflict)
        self._audit(conflict, "conflict_created", "Conflict is awaiting human review")
        return conflict

    def get(self, conflict_id: str) -> ConflictRecord: return self.storage.get_conflict(conflict_id)

    def resolve(self, conflict_id: str, resolution: str, *, human_confirmed: bool = False) -> ConflictRecord:
        conflict = self.get(conflict_id)
        if not human_confirmed: raise ApprovalError("Conflict resolution requires explicit human review")
        if conflict.status != "OPEN": raise ValidationFailed("Conflict is already resolved")
        if resolution not in conflict.options: raise ValidationFailed("Resolution must be one of the proposed options")
        conflict.resolution = resolution; conflict.status = "RESOLVED"; conflict.resolved_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.storage.append_conflict(conflict); self._audit(conflict, "conflict_resolved", "Human-selected conflict resolution")
        return conflict

    def _audit(self, conflict: ConflictRecord, action: str, detail: str) -> None:
        if self.audit: self.audit.record(action=action, path=f"conflict/{conflict.id}", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=detail)
