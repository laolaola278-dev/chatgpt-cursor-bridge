"""Phase 31 · Provider boundary.

Providers translate the unified message protocol to their vendor formats.
Every provider accepts an optional ``httpx.BaseTransport`` so tests can inject
a mock transport; no provider ever touches the network unless a real transport
is in use. Responses are always translated back into gateway models and tool
calls always surface as proposals.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx

from ..models import ChatMessage, ChatResult, StreamEvent, ToolCall, dumps_json

DEFAULT_TIMEOUT = 60.0


class ProviderError(Exception):
    """Raised when a provider cannot fulfil a request (config or upstream)."""

    def __init__(self, message: str, *, code: str = "provider_error", status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class LLMProvider(Protocol):
    name: str
    enabled: bool

    def list_models(self) -> list[dict[str, Any]]: ...

    def chat(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> ChatResult: ...

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> Any: ...


def _render_messages(messages: list[ChatMessage]) -> str:
    """Deterministic textual rendering of the unified protocol."""
    lines: list[str] = []
    for message in messages:
        if message.role.value == "system":
            lines.append(f"[system] {message.content}")
        elif message.role.value == "tool":
            calls = ", ".join(f"{tool.name}({tool.arguments})" for tool in message.tool_calls)
            lines.append(f"[tool] {message.content} {calls}".strip())
        elif message.role.value == "assistant":
            calls = ", ".join(f"{tool.name}({tool.arguments})" for tool in message.tool_calls)
            lines.append(f"[assistant] {message.content} {calls}".strip())
        else:
            lines.append(f"[user] {message.content}")
    return "\n".join(lines)


def _parse_tool_calls(content: str) -> list[ToolCall]:
    """Extract ``@tool(name {"json":"args"})`` directives from model text.

    Deterministic and vendor-agnostic; used by the local simulator and as a
    fallback for providers that return tool calls in text form.
    """
    calls: list[ToolCall] = []
    pattern = re.compile(r"@tool\(([A-Za-z0-9_.-]+)\s*(\{.*?\})?\s*\)", re.DOTALL)
    for index, match in enumerate(pattern.finditer(content)):
        name = match.group(1)
        arguments = (match.group(2) or "{}").strip()
        calls.append(ToolCall(name=name, arguments=arguments, call_id=f"tool_{index + 1}"))
    return calls


class HTTPProviderMixin:
    """Shared httpx plumbing for vendor providers.

    ``api_key`` may be empty; the provider is then disabled and chat/stream
    raise ``ProviderError`` with a clear configuration message.
    """

    name = ""
    api_key = ""
    base_url = ""
    _transport: httpx.BaseTransport | None = None

    def __init__(self, *, api_key: str = "", transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {"timeout": DEFAULT_TIMEOUT, "base_url": self.base_url}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderError(
                f"Provider '{self.name}' is not configured: set {self._key_env()} to enable it.",
                code="provider_not_configured",
                status=422,
            )

    def _key_env(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _request_json(
        self, method: str, path: str, *, headers: dict[str, str], body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = self._client().request(method, path, headers=headers, json=body)
        except ProviderError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name} request failed: {exc}", code="provider_unreachable") from exc
        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} returned HTTP {response.status_code}: {response.text[:400]}",
                code="provider_http_error",
                status=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} returned invalid JSON", code="provider_bad_response") from exc


def build_http_provider_openai(*, api_key: str, transport: httpx.BaseTransport | None = None) -> Any:
    from .openai import OpenAIProvider

    return OpenAIProvider(api_key=api_key, transport=transport)


def build_http_provider_anthropic(*, api_key: str, transport: httpx.BaseTransport | None = None) -> Any:
    from .anthropic import AnthropicProvider

    return AnthropicProvider(api_key=api_key, transport=transport)


def build_http_provider_deepseek(*, api_key: str, transport: httpx.BaseTransport | None = None) -> Any:
    from .deepseek import DeepSeekProvider

    return DeepSeekProvider(api_key=api_key, transport=transport)


__all__ = [
    "DEFAULT_TIMEOUT",
    "HTTPProviderMixin",
    "LLMProvider",
    "ProviderError",
    "build_http_provider_anthropic",
    "build_http_provider_deepseek",
    "build_http_provider_openai",
    "dumps_json",
    "json",
]
