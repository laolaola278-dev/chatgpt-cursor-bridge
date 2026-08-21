"""Agent-to-agent message protocol.

Messages are durable metadata only. They do not carry executable commands,
shell fragments, or implicit tool permissions.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AgentMessage:
    message_id: str
    from_agent: str
    to_agent: str
    task: str
    context_reference: str
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        from_agent: str,
        to_agent: str,
        task: str,
        context_reference: str,
    ) -> "AgentMessage":
        clean_task = (task or "").strip()
        clean_context = (context_reference or "").strip()
        if not clean_task or len(clean_task) > 4000:
            raise ValueError("Agent message task must contain 1-4000 characters")
        if len(clean_context) > 500:
            raise ValueError("Agent message context reference exceeds 500 characters")
        if not from_agent or not to_agent or from_agent == to_agent:
            raise ValueError("Agent message endpoints must be distinct valid agent ids")
        return cls(
            message_id=f"msg_{secrets.token_hex(8)}",
            from_agent=from_agent,
            to_agent=to_agent,
            task=clean_task,
            context_reference=clean_context,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "messageId": self.message_id,
            "fromAgent": self.from_agent,
            "toAgent": self.to_agent,
            "task": self.task,
            "contextReference": self.context_reference,
            "createdAt": self.created_at,
        }
