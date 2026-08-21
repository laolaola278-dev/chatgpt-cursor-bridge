"""Phase 31 · OpenAI provider adapter (GPT-5 / GPT-4 series)."""

from __future__ import annotations

import os
from typing import Any

from ..models import ChatMessage, ChatResult, StreamEvent, ToolCall
from .base import HTTPProviderMixin, ProviderError, _parse_tool_calls

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODELS = (
    {"id": "gpt-5", "provider": "openai", "displayName": "GPT-5", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 275_000},
    {"id": "gpt-5-mini", "provider": "openai", "displayName": "GPT-5 mini", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 128_000},
    {"id": "gpt-4o", "provider": "openai", "displayName": "GPT-4o", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 128_000},
    {"id": "gpt-4.1", "provider": "openai", "displayName": "GPT-4.1", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 1_000_000},
    {"id": "gpt-4-turbo", "provider": "openai", "displayName": "GPT-4 Turbo", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 128_000},
)


class OpenAIProvider(HTTPProviderMixin):
    name = "openai"
    base_url = OPENAI_BASE_URL

    def __init__(self, *, api_key: str = "", transport: Any = None) -> None:
        super().__init__(api_key=api_key, transport=transport)

    def _key_env(self) -> str:
        return "OPENAI_API_KEY"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def list_models(self) -> list[dict[str, Any]]:
        return [dict(model, enabled=self.enabled) for model in OPENAI_MODELS]

    def chat(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> ChatResult:
        self._require_key()
        body = {
            "model": model,
            "messages": [self._to_openai(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._request_json("POST", "/chat/completions", headers=self._headers(), body=body)
        return self._from_response(data, model)

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> Any:
        self._require_key()
        body = {
            "model": model,
            "messages": [self._to_openai(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        response = self._client().stream("POST", "/chat/completions", headers=self._headers(), json=body)
        with response as stream:
            if stream.status_code >= 400:
                raise ProviderError(
                    f"openai returned HTTP {stream.status_code}", code="provider_http_error", status=stream.status_code
                )
            for line in stream.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                import json

                try:
                    event = json.loads(payload)
                except ValueError:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = (choices[0].get("delta") or {}) if isinstance(choices[0], dict) else {}
                content = delta.get("content") or ""
                if content:
                    yield StreamEvent(kind="delta", content=content, provider="openai", model=model)
                tool_calls = delta.get("tool_calls") or []
                for call in tool_calls:
                    fn = call.get("function") or {}
                    yield StreamEvent(
                        kind="tool_call",
                        tool_call=ToolCall(name=fn.get("name", ""), arguments=fn.get("arguments", ""), call_id=call.get("id", "")),
                        provider="openai",
                        model=model,
                    )
        yield StreamEvent(kind="done", provider="openai", model=model)

    @staticmethod
    def _to_openai(message: ChatMessage) -> dict[str, Any]:
        item: dict[str, Any] = {"role": message.role.value, "content": message.content}
        if message.tool_calls:
            item["tool_calls"] = [
                {
                    "id": tool.call_id or f"call_{index}",
                    "type": "function",
                    "function": {"name": tool.name, "arguments": tool.arguments},
                }
                for index, tool in enumerate(message.tool_calls)
            ]
        return item

    def _from_response(self, data: dict[str, Any], model: str) -> ChatResult:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("openai returned no choices", code="provider_empty_response")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        tool_calls: list[ToolCall] = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            tool_calls.append(
                ToolCall(name=fn.get("name", ""), arguments=fn.get("arguments", "{}"), call_id=call.get("id", ""))
            )
        if not tool_calls:
            tool_calls = _parse_tool_calls(content)
        usage = data.get("usage") or {}
        return ChatResult(
            reply=content,
            tool_calls=tuple(tool_calls),
            provider="openai",
            model=model,
            finish_reason=str(choice.get("finish_reason", "stop")),
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
            },
            simulated=False,
        )


def resolve_openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "")
