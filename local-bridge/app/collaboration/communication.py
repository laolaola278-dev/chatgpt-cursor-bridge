"""Negotiation protocol for agent discussion and review requests."""
from __future__ import annotations

from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel

from .models import CollaborationMessage, CollaborationMessageType
from .storage import CollaborationStorage


class CollaborationCommunication:
    def __init__(self, storage: CollaborationStorage, audit: AuditLogger | None = None) -> None: self.storage, self.audit = storage, audit

    def send(self, *, message_type: CollaborationMessageType | str, sender: str, receiver: str, task_id: str, workflow_id: str, context: str) -> CollaborationMessage:
        message = CollaborationMessage.create(message_type=message_type, sender=sender, receiver=receiver, task_id=task_id, workflow_id=workflow_id, context=context)
        self.storage.append_message(message)
        if self.audit: self.audit.record(action="collaboration_message", path=f"collaboration/{message.message_id}", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=f"{message.message_type.value} {sender}->{receiver}")
        return message

    def list(self, limit: int = 100) -> list[dict[str, Any]]: return self.storage.list_messages(limit)
