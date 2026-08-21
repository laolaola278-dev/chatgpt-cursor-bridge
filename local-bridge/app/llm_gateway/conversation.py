"""Phase 31 · Conversation and Tool-Call Proposal storage.

SQLite-backed, project-isolated. Conversations bind to a project and
optionally an agent; messages are appended only through the approval-gated
POST endpoints; tool-call proposals are records persisted only after human
approval (``approval_request_id`` is stored for audit).
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .models import (
    Conversation,
    ConversationMessage,
    ConversationStatus,
    MessageRole,
    ToolCall,
    ToolCallProposal,
    ToolCallStatus,
    dumps_json,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


class ConversationStore:
    def __init__(self, db_path: str | Path) -> None:
        self._lock = Lock()
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                title TEXT NOT NULL,
                agent TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                approval_request_id TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_call_proposals (
                proposal_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                project TEXT NOT NULL,
                message_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_request_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_project ON conversations(project, updated_at)"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_msg_conversation ON conversation_messages(conversation_id, created_at)"
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_project ON tool_call_proposals(project, created_at)"
        )
        self._connection.commit()

    # -- Conversations ---------------------------------------------------

    def create_conversation(
        self,
        *,
        project: str,
        provider: str,
        model: str,
        title: str,
        agent: str = "",
        approval_request_id: str = "",
    ) -> Conversation:
        now = _utc_now()
        conversation = Conversation(
            conversation_id=_new_id("conv"),
            project=project,
            provider=provider,
            model=model,
            title=title,
            agent=agent,
            status=ConversationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO conversations (conversation_id, project, provider, model, title, agent, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    conversation.project,
                    conversation.provider,
                    conversation.model,
                    conversation.title,
                    conversation.agent,
                    conversation.status.value,
                    conversation.created_at,
                    conversation.updated_at,
                ),
            )
            self._connection.commit()
        return conversation

    def get_conversation(self, conversation_id: str, project: str | None = None) -> Conversation | None:
        query = "SELECT * FROM conversations WHERE conversation_id=?"
        params: list[Any] = [conversation_id]
        if project:
            query += " AND project=?"
            params.append(project)
        with self._lock:
            row = self._connection.execute(query, params).fetchone()
        return self._from_conversation_row(row) if row else None

    def list_conversations(self, project: str, agent: str = "") -> list[Conversation]:
        query = "SELECT * FROM conversations WHERE project=? "
        params: list[Any] = [project]
        if agent:
            query += "AND agent=? "
            params.append(agent)
        query += "ORDER BY updated_at DESC"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._from_conversation_row(row) for row in rows]

    # -- Messages --------------------------------------------------------

    def append_message(
        self,
        *,
        conversation_id: str,
        role: MessageRole,
        content: str,
        tool_calls: tuple[ToolCall, ...] = (),
        approval_request_id: str = "",
    ) -> ConversationMessage:
        message = ConversationMessage(
            message_id=_new_id("msg"),
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            created_at=_utc_now(),
            approval_request_id=approval_request_id,
        )
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO conversation_messages (message_id, conversation_id, role, content, tool_calls_json, created_at, approval_request_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.conversation_id,
                    message.role.value,
                    message.content,
                    dumps_json([tool.as_dict() for tool in message.tool_calls]),
                    message.created_at,
                    message.approval_request_id,
                ),
            )
            self._connection.execute(
                "UPDATE conversations SET updated_at=? WHERE conversation_id=?",
                (_utc_now(), conversation_id),
            )
            self._connection.commit()
        return message

    def list_messages(self, conversation_id: str, limit: int = 200) -> list[ConversationMessage]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM conversation_messages WHERE conversation_id=? ORDER BY created_at ASC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [self._from_message_row(row) for row in rows]

    # -- Tool-call proposals ---------------------------------------------

    def save_tool_proposal(
        self,
        *,
        conversation_id: str,
        project: str,
        message_id: str,
        tool_name: str,
        arguments: str,
        reason: str,
        approval_request_id: str = "",
    ) -> ToolCallProposal:
        proposal = ToolCallProposal(
            proposal_id=_new_id("tool"),
            conversation_id=conversation_id,
            project=project,
            message_id=message_id,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            status=ToolCallStatus.RECORDED if approval_request_id else ToolCallStatus.PROPOSED,
            approval_request_id=approval_request_id,
            created_at=_utc_now(),
        )
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO tool_call_proposals (proposal_id, conversation_id, project, message_id, tool_name, arguments, reason, status, approval_request_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id,
                    proposal.conversation_id,
                    proposal.project,
                    proposal.message_id,
                    proposal.tool_name,
                    proposal.arguments,
                    proposal.reason,
                    proposal.status.value,
                    proposal.approval_request_id,
                    proposal.created_at,
                ),
            )
            self._connection.commit()
        return proposal

    def get_tool_proposal(self, proposal_id: str, project: str) -> ToolCallProposal | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM tool_call_proposals WHERE proposal_id=? AND project=?",
                (proposal_id, project),
            ).fetchone()
        return self._from_proposal_row(row) if row else None

    def list_tool_proposals(self, project: str, conversation_id: str = "") -> list[ToolCallProposal]:
        query = "SELECT * FROM tool_call_proposals WHERE project=? "
        params: list[Any] = [project]
        if conversation_id:
            query += "AND conversation_id=? "
            params.append(conversation_id)
        query += "ORDER BY created_at DESC"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._from_proposal_row(row) for row in rows]

    # -- Rows ------------------------------------------------------------

    @staticmethod
    def _from_conversation_row(row: sqlite3.Row) -> Conversation:
        return Conversation(
            conversation_id=row["conversation_id"],
            project=row["project"],
            provider=row["provider"],
            model=row["model"],
            title=row["title"],
            agent=row["agent"],
            status=ConversationStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _from_message_row(row: sqlite3.Row) -> ConversationMessage:
        raw_calls = json.loads(row["tool_calls_json"] or "[]")
        return ConversationMessage(
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            tool_calls=tuple(ToolCall.from_dict(item) for item in raw_calls),
            created_at=row["created_at"],
            approval_request_id=row["approval_request_id"],
        )

    @staticmethod
    def _from_proposal_row(row: sqlite3.Row) -> ToolCallProposal:
        return ToolCallProposal(
            proposal_id=row["proposal_id"],
            conversation_id=row["conversation_id"],
            project=row["project"],
            message_id=row["message_id"],
            tool_name=row["tool_name"],
            arguments=row["arguments"],
            reason=row["reason"],
            status=ToolCallStatus(row["status"]),
            approval_request_id=row["approval_request_id"],
            created_at=row["created_at"],
        )

    @property
    def db_path(self) -> str:
        return self._db_path


__all__ = ["ConversationStore"]
