"""Session lifecycle orchestration with no execution side effects."""

from __future__ import annotations

import secrets
from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import ApprovalStore, PermissionLevel
from app.security.sandbox import validate_project_name
from app.security.validator import ApprovalError, ResourceNotFound, ValidationFailed
from app.workflow.manager import WorkflowManager

from .models import Session, SessionStatus
from .storage import SessionStorage


_ALLOWED: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.CREATE: frozenset({SessionStatus.ACTIVE, SessionStatus.COMPLETED}),
    SessionStatus.ACTIVE: frozenset({SessionStatus.PAUSED, SessionStatus.COMPLETED}),
    SessionStatus.PAUSED: frozenset({SessionStatus.ACTIVE, SessionStatus.COMPLETED}),
    SessionStatus.COMPLETED: frozenset(),
}


class SessionManager:
    def __init__(
        self,
        *,
        storage: SessionStorage,
        workflows: WorkflowManager,
        approvals: ApprovalStore,
        audit: AuditLogger,
    ) -> None:
        self.storage = storage
        self.workflows = workflows
        self.approvals = approvals
        self.audit = audit

    def list(self, project: str | None = None) -> list[Session]:
        sessions = self.storage.all()
        if project:
            sessions = [session for session in sessions if session.project == project]
        return sorted(sessions, key=lambda session: session.updated_at, reverse=True)

    def get(self, session_id: str) -> Session:
        if not session_id.startswith("ses_"):
            raise ValidationFailed("Invalid session id")
        return self.storage.get(session_id)

    def create(
        self,
        *,
        project: str,
        workflow_id: str | None = None,
        stage_id: str | None = None,
        approval_id: str | None = None,
    ) -> Session:
        project = validate_project_name(project)
        if workflow_id and stage_id:
            workflow, _ = self.workflows.validate_binding(workflow_id, stage_id, project=project)
        elif workflow_id or stage_id:
            raise ValidationFailed("workflow_id and stage_id must be provided together")
        if approval_id:
            approval = self.approvals.get(approval_id)
            if approval.project != project:
                raise ValidationFailed("Approval project does not match session project")
        now = Session.now()
        session = Session(
            id=f"ses_{secrets.token_hex(8)}",
            project=project,
            status=SessionStatus.CREATE,
            created_at=now,
            updated_at=now,
            workflow_id=workflow_id,
            stage_id=stage_id,
            approval_id=approval_id,
            history=[{"from": "", "to": SessionStatus.CREATE.value, "at": now}],
        )
        self.storage.save(session)
        if approval_id:
            self.approvals.attach_session(approval_id, session.id)
        self._audit(session, "session_created", "Created persistent session")
        return session

    def transition(self, session_id: str, target: str) -> Session:
        session = self.get(session_id)
        try:
            next_status = SessionStatus((target or "").strip().upper())
        except ValueError as exc:
            raise ValidationFailed("Unknown session status") from exc
        if next_status not in _ALLOWED[session.status]:
            raise ApprovalError(
                f"Session {session.id} cannot transition {session.status.value} -> {next_status.value}"
            )
        now = Session.now()
        previous = session.status
        session.status = next_status
        session.updated_at = now
        session.history.append({"from": previous.value, "to": next_status.value, "at": now})
        self.storage.save(session)
        self._audit(session, "session_transition", f"{previous.value} -> {next_status.value}")
        return session

    def _audit(self, session: Session, action: str, detail: str) -> None:
        self.audit.record(
            action=action,
            path=f"{session.project}:session/{session.id}",
            permission=PermissionLevel.LEVEL_1.value,
            approved=True,
            result="success",
            detail=detail,
        )

    def context(self, project: str) -> list[dict[str, Any]]:
        return [session.as_dict() for session in self.list(project)]
