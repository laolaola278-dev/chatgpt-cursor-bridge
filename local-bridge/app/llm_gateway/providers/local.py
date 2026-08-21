"""Phase 31 · Local simulator provider.

A deterministic, credential-free provider so the gateway is usable out of the
box and fully testable. It renders the unified message protocol into text and
produces stable replies; ``@tool(name {...})`` directives in the *user* message
surface as tool-call proposals in the reply, which keeps the human-in-the-loop
path exercisable without any external provider.
"""

from __future__ import annotations

from typing import Any

from ..models import ChatMessage, ChatResult, StreamEvent, ToolCall
from .base import _parse_tool_calls, _render_messages

MODEL_IDS = ("local/simulator-v1", "local/architect-v1")


class LocalSimulatorProvider:
    name = "local"
    enabled = True

    def list_models(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "local/simulator-v1",
                "provider": "local",
                "displayName": "Local Simulator",
                "capabilities": ["chat", "stream", "tool_calling"],
                "contextWindow": 32_000,
                "enabled": True,
            },
            {
                "id": "local/architect-v1",
                "provider": "local",
                "displayName": "Local Architect (offline)",
                "capabilities": ["chat", "stream"],
                "contextWindow": 64_000,
                "enabled": True,
            },
        ]

    def chat(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> ChatResult:
        prompt = _render_messages(messages)
        last_user = next((message.content for message in reversed(messages) if message.role.value == "user"), "")
        tool_calls = _parse_tool_calls(last_user)
        if tool_calls:
            reply = f"[simulated] Detected {len(tool_calls)} tool call proposal(s); routing to ApprovalStore. No tool executed."
            return ChatResult(
                reply=reply,
                tool_calls=tuple(tool_calls),
                provider="local",
                model=model,
                finish_reason="tool_calls",
                usage={"prompt_tokens": max(1, len(prompt) // 4), "completion_tokens": max(1, len(reply) // 4)},
                simulated=True,
            )
        reply = (
            f"[simulated:{model}] Received {len(messages)} message(s). "
            f"Last user message ({len(last_user)} chars) acknowledged. "
            "Connect a provider (openai / anthropic / deepseek) for live inference."
        )
        return ChatResult(
            reply=reply,
            provider="local",
            model=model,
            finish_reason="stop",
            usage={"prompt_tokens": max(1, len(prompt) // 4), "completion_tokens": max(1, len(reply) // 4)},
            simulated=True,
        )

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float, max_tokens: int) -> Any:
        result = self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)
        words = result.reply.split(" ")
        for word in words[:-1]:
            yield StreamEvent(kind="delta", content=word + " ", provider="local", model=model)
        if words:
            yield StreamEvent(kind="delta", content=words[-1], provider="local", model=model)
        for tool in result.tool_calls:
            yield StreamEvent(kind="tool_call", tool_call=tool, provider="local", model=model)
        yield StreamEvent(kind="done", provider="local", model=model)


__all__ = ["LocalSimulatorProvider"]
