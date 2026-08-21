"""Phase 31 · DeepSeek provider adapter (DeepSeek Chat / Reasoner)."""

from __future__ import annotations

import os
from typing import Any

from ..models import ChatMessage, ChatResult, StreamEvent, ToolCall
from .base import HTTPProviderMixin, ProviderError, _parse_tool_calls

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODELS = (
    {"id": "deepseek-chat", "provider": "deepseek", "displayName": "DeepSeek Chat", "capabilities": ["chat", "stream", "tool_calling"], "contextWindow": 64_000},
    {"id": "deepseek-reasoner", "provider": "deepseek", "displayName": "DeepSeek Reasoner", "capabilities": ["chat", "stream"], "contextWindow": 64_000},
)


class DeepSeekProvider(HTTPProviderMixin):
    name = "deepseek"
    base_url = DEEPSEEK_BASE_URL

    def __init__(self, *, api_key: str = "", transport: Any = None) -> None:
        super().__init__(api_key=api_key, transport=transport)

    def _key_env(self) -> str:
        return "DEEPSEEK_API_KEY"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def list_models(self) -> list[dict[str, Any]]:
        return [dict(model, enabled=self.enabled) for model in DEEPSEEK_MODELS]

    def chat(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> ChatResult:
        self._require_key()
        body = {
            "model": model,
            "messages": [{"role": message.role.value, "content": message.content} for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self._request_json("POST", "/chat/completions", headers=self._headers(), body=body)
        return self._from_response(data, model)

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> Any:
        self._require_key()
        body = {
            "model": model,
            "messages": [{"role": message.role.value, "content": message.content} for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        response = self._client().stream("POST", "/chat/completions", headers=self._headers(), json=body)
        with response as stream:
            if stream.status_code >= 400:
                raise ProviderError(
                    f"deepseek returned HTTP {stream.status_code}", code="provider_http_error", status=stream.status_code
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
                    yield StreamEvent(kind="delta", content=content, provider="deepseek", model=model)
        yield StreamEvent(kind="done", provider="deepseek", model=model)

    def _from_response(self, data: dict[str, Any], model: str) -> ChatResult:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("deepseek returned no choices", code="provider_empty_response")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        tool_calls = _parse_tool_calls(content)
        usage = data.get("usage") or {}
        return ChatResult(
            reply=content,
            tool_calls=tuple(tool_calls),
            provider="deepseek",
            model=model,
            finish_reason=str(choice.get("finish_reason", "stop")),
            usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
            },
            simulated=False,
        )


def resolve_deepseek_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "")
