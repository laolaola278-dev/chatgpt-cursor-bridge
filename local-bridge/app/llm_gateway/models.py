"""Phase 31 · LLM Gateway models.

Unified message protocol (system / user / assistant / tool), conversation and
tool-proposal records used by the provider-agnostic LLM Gateway.

Security model: every role is a plain data carrier. ``tool`` messages always
carry a proposal reference and are never executed by this layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECORDED = "recorded"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the model.

    It is a proposal, never an execution order. ``arguments`` is a JSON object
    string kept opaque to the gateway; only the approval-gated runtime may
    interpret it.
    """

    name: str
    arguments: str
    call_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "callId": self.call_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ToolCall":
        return cls(
            name=str(raw.get("name", "")),
            arguments=str(raw.get("arguments", "")),
            call_id=str(raw.get("callId", raw.get("call_id", ""))),
        )


@dataclass(frozen=True)
class ChatMessage:
    """One message in the unified protocol."""

    role: MessageRole
    content: str
    name: str = ""
    tool_calls: tuple[ToolCall, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "name": self.name,
            "toolCalls": [tool.as_dict() for tool in self.tool_calls],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ChatMessage":
        role_raw = str(raw.get("role", "user")).lower()
        try:
            role = MessageRole(role_raw)
        except ValueError:
            role = MessageRole.USER
        tool_calls = tuple(
            ToolCall.from_dict(item) for item in raw.get("toolCalls", raw.get("tool_calls", []))
        )
        return cls(
            role=role,
            content=str(raw.get("content", "")),
            name=str(raw.get("name", "")),
            tool_calls=tool_calls,
        )


@dataclass(frozen=True)
class ChatRequest:
    project: str
    messages: tuple[ChatMessage, ...]
    model: str = "local/simulator-v1"
    provider: str = ""
    agent: str = ""
    temperature: float = 0.4
    max_tokens: int = 2048
    stream: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "messages": [message.as_dict() for message in self.messages],
            "model": self.model,
            "provider": self.provider,
            "agent": self.agent,
            "temperature": self.temperature,
            "maxTokens": self.max_tokens,
            "stream": self.stream,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ChatRequest":
        return cls(
            project=str(raw.get("project", "")),
            messages=tuple(ChatMessage.from_dict(item) for item in raw.get("messages", [])),
            model=str(raw.get("model", "local/simulator-v1")),
            provider=str(raw.get("provider", "")),
            agent=str(raw.get("agent", "")),
            temperature=float(raw.get("temperature", 0.4)),
            max_tokens=int(raw.get("maxTokens", raw.get("max_tokens", 2048))),
            stream=bool(raw.get("stream", False)),
        )


@dataclass(frozen=True)
class ChatResult:
    """Stateless chat reply. ``tool_calls`` are proposals for the caller to
    route through ApprovalStore; this gateway never executes them."""

    reply: str
    tool_calls: tuple[ToolCall, ...] = ()
    provider: str = "local"
    model: str = "local/simulator-v1"
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    simulated: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "toolCalls": [tool.as_dict() for tool in self.tool_calls],
            "provider": self.provider,
            "model": self.model,
            "finishReason": self.finish_reason,
            "usage": self.usage,
            "simulated": self.simulated,
            "readOnly": True,
        }


@dataclass(frozen=True)
class StreamEvent:
    kind: str  # "delta" | "tool_call" | "done" | "error"
    content: str = ""
    tool_call: ToolCall | None = None
    provider: str = ""
    model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "content": self.content,
            "toolCall": self.tool_call.as_dict() if self.tool_call else None,
            "provider": self.provider,
            "model": self.model,
        }


@dataclass
class Conversation:
    """Persisted conversation bound to a project and optionally an agent."""

    conversation_id: str
    project: str
    provider: str
    model: str
    title: str
    agent: str = ""
    status: ConversationStatus = ConversationStatus.ACTIVE
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "conversationId": self.conversation_id,
            "project": self.project,
            "provider": self.provider,
            "model": self.model,
            "title": self.title,
            "agent": self.agent,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "readOnly": True,
        }


@dataclass
class ConversationMessage:
    message_id: str
    conversation_id: str
    role: MessageRole
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    created_at: str = ""
    approval_request_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "messageId": self.message_id,
            "conversationId": self.conversation_id,
            "role": self.role.value,
            "content": self.content,
            "toolCalls": [tool.as_dict() for tool in self.tool_calls],
            "createdAt": self.created_at,
            "approvalRequestId": self.approval_request_id,
            "readOnly": True,
        }


@dataclass
class ToolCallProposal:
    """A model-requested tool call recorded only after human approval.

    The gateway stores it as a record with the approval request id; executing
    the tool is out of scope for Phase 31 and stays in the existing
    approval-gated controlled runtime.
    """

    proposal_id: str
    conversation_id: str
    project: str
    message_id: str
    tool_name: str
    arguments: str
    reason: str
    status: ToolCallStatus
    approval_request_id: str = ""
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposalId": self.proposal_id,
            "conversationId": self.conversation_id,
            "project": self.project,
            "messageId": self.message_id,
            "toolName": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "status": self.status.value,
            "approvalRequestId": self.approval_request_id,
            "createdAt": self.created_at,
            "executed": False,
            "readOnly": True,
        }


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
