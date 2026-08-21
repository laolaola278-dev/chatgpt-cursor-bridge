"""Phase 31 · LLM Gateway.

Resolves providers/models through the registries and executes chat / streaming
against the unified message protocol. Tool calls returned by a model always
surface as proposals — the gateway never executes them.

``chat``/``stream`` are stateless computations: they do not persist anything
and never modify system state. Conversation persistence and tool-proposal
recording are separate, approval-gated operations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from .conversation import ConversationStore
from .models import (
    ChatMessage,
    ChatRequest,
    ChatResult,
    Conversation,
    ConversationMessage,
    MessageRole,
    StreamEvent,
    ToolCall,
    ToolCallProposal,
    ToolCallStatus,
)
from .registry import ProviderRegistry


def default_llm_db_path() -> Path:
    from app.config import get_settings

    return get_settings().workspace_root.parent / "llm" / "llm.db"


class LLMGateway:
    def __init__(
        self,
        providers: ProviderRegistry | None = None,
        store: ConversationStore | None = None,
        *,
        llm_db_path: str | Path | None = None,
    ) -> None:
        self.providers = providers or ProviderRegistry()
        if store is None:
            store = ConversationStore(llm_db_path or default_llm_db_path())
        self.store = store

    # -- Provider / model introspection ----------------------------------

    def providers_info(self) -> list[dict[str, Any]]:
        return self.providers.providers()

    def models(self, provider: str = "") -> list[dict[str, Any]]:
        return self.providers.models(provider or None)

    # -- Chat -------------------------------------------------------------

    def chat(self, request: ChatRequest) -> ChatResult:
        provider_name = request.provider or _provider_for_model(self.providers, request.model)
        provider, _entry = self.providers.resolve(provider_name, request.model)
        if not provider.enabled:
            raise _not_configured(provider_name)
        messages = list(request.messages)
        if not messages or all(message.role is not MessageRole.USER for message in messages):
            messages = [ChatMessage(role=MessageRole.USER, content="(empty request)")] + messages
        return provider.chat(
            messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    def stream(self, request: ChatRequest) -> Iterable[StreamEvent]:
        provider_name = request.provider or _provider_for_model(self.providers, request.model)
        provider, _entry = self.providers.resolve(provider_name, request.model)
        if not provider.enabled:
            raise _not_configured(provider_name)
        messages = list(request.messages)
        if not messages or all(message.role is not MessageRole.USER for message in messages):
            messages = [ChatMessage(role=MessageRole.USER, content="(empty request)")] + messages
        yield from provider.stream(
            messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    # -- Conversation persistence (approval-gated callers) ---------------

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
        return self.store.create_conversation(
            project=project,
            provider=provider,
            model=model,
            title=title,
            agent=agent,
            approval_request_id=approval_request_id,
        )

    def append_message(
        self,
        *,
        conversation_id: str,
        project: str,
        role: MessageRole,
        content: str,
        tool_calls: tuple[ToolCall, ...] = (),
        approval_request_id: str = "",
    ) -> ConversationMessage:
        conversation = self.store.get_conversation(conversation_id, project)
        if conversation is None:
            raise ValueError(f"Conversation '{conversation_id}' not found for project '{project}'")
        return self.store.append_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            approval_request_id=approval_request_id,
        )

    def record_tool_proposal(
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
        return self.store.save_tool_proposal(
            conversation_id=conversation_id,
            project=project,
            message_id=message_id,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
            approval_request_id=approval_request_id,
        )

    def conversation_history(self, conversation_id: str, project: str, limit: int = 200) -> list[ConversationMessage]:
        conversation = self.store.get_conversation(conversation_id, project)
        if conversation is None:
            raise ValueError(f"Conversation '{conversation_id}' not found for project '{project}'")
        return self.store.list_messages(conversation_id, limit=limit)


def _provider_for_model(providers: ProviderRegistry, model: str) -> str:
    for name in providers.names():
        for entry in providers.models(name):
            if entry["id"] == model:
                return name
    return "local"


def _not_configured(provider_name: str) -> Exception:
    from .providers.base import ProviderError

    env = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}.get(
        provider_name, ""
    )
    hint = f"set {env} to enable it." if env else "select a configured provider."
    return ProviderError(
        f"Provider '{provider_name}' is not configured; {hint}",
        code="provider_not_configured",
        status=422,
    )


def resolve_key_env(name: str) -> str:
    return os.getenv({"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}.get(name, ""), "")


__all__ = ["LLMGateway", "ToolCallStatus", "default_llm_db_path"]
