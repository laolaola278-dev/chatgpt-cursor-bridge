"""Phase 31 · Anthropic provider adapter (Claude series)."""

from __future__ import annotations

import os
from typing import Any

from ..models import ChatMessage, ChatResult, StreamEvent, ToolCall
from .base import HTTPProviderMixin, ProviderError, _parse_tool_calls

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MODELS = (
    {"id": "claude-4-sonnet", "provider": "anthropic", "displayName": "Claude Sonnet 4", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 200_000},
    {"id": "claude-3-7-sonnet", "provider": "anthropic", "displayName": "Claude 3.7 Sonnet", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 200_000},
    {"id": "claude-3-5-sonnet", "provider": "anthropic", "displayName": "Claude 3.5 Sonnet", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 200_000},
    {"id": "claude-3-5-haiku", "provider": "anthropic", "displayName": "Claude 3.5 Haiku", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 200_000},
)


class AnthropicProvider(HTTPProviderMixin):
    name = "anthropic"
    base_url = ANTHROPIC_BASE_URL

    def __init__(self, *, api_key: str = "", transport: Any = None) -> None:
        super().__init__(api_key=api_key, transport=transport)

    def _key_env(self) -> str:
        return "ANTHROPIC_API_KEY"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    def list_models(self) -> list[dict[str, Any]]:
        return [dict(model, enabled=self.enabled) for model in ANTHROPIC_MODELS]

    def chat(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> ChatResult:
        self._require_key()
        system = "\n".join(message.content for message in messages if message.role.value == "system")
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [self._to_anthropic(message) for message in messages if message.role.value != "system"],
        }
        if system:
            body["system"] = system
        data = self._request_json("POST", "/messages", headers=self._headers(), body=body)
        return self._from_response(data, model)

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> Any:
        self._require_key()
        system = "\n".join(message.content for message in messages if message.role.value == "system")
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "messages": [self._to_anthropic(message) for message in messages if message.role.value != "system"],
        }
        if system:
            body["system"] = system
        response = self._client().stream("POST", "/messages", headers=self._headers(), json=body)
        with response as stream:
            if stream.status_code >= 400:
                raise ProviderError(
                    f"anthropic returned HTTP {stream.status_code}", code="provider_http_error", status=stream.status_code
                )
            for line in stream.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                import json

                try:
                    event = json.loads(payload)
                except ValueError:
                    continue
                event_type = event.get("type", "")
                if event_type == "content_block_delta":
                    delta = event.get("delta") or {}
                    text = delta.get("text") or ""
                    if text:
                        yield StreamEvent(kind="delta", content=text, provider="anthropic", model=model)
                elif event_type == "content_block_start":
                    block = event.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        tool = ToolCall(
                            name=block.get("name", ""),
                            arguments="",
                            call_id=block.get("id", ""),
                        )
                        yield StreamEvent(kind="tool_call", tool_call=tool, provider="anthropic", model=model)
        yield StreamEvent(kind="done", provider="anthropic", model=model)

    @staticmethod
    def _to_anthropic(message: ChatMessage) -> dict[str, Any]:
        return {"role": "user" if message.role.value == "tool" else message.role.value, "content": message.content}

    def _from_response(self, data: dict[str, Any], model: str) -> ChatResult:
        content = data.get("content") or []
        parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                import json as _json

                tool_calls.append(
                    ToolCall(name=block.get("name", ""), arguments=_json.dumps(block.get("input") or {}), call_id=block.get("id", ""))
                )
        reply = "\n".join(parts)
        if not tool_calls:
            tool_calls = _parse_tool_calls(reply)
        usage = data.get("usage") or {}
        return ChatResult(
            reply=reply,
            tool_calls=tuple(tool_calls),
            provider="anthropic",
            model=model,
            finish_reason=str(data.get("stop_reason", "end_turn")),
            usage={
                "prompt_tokens": int(usage.get("input_tokens", 0)),
                "completion_tokens": int(usage.get("output_tokens", 0)),
            },
            simulated=False,
        )


def resolve_anthropic_key() -> str:
    return os.getenv("ANTHROPIC_API_KEY", "")
