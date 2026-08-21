from __future__ import annotations

from typing import Any


class ProviderCapabilityRegistry:
    def __init__(self) -> None:
        self._models = [
            {"model": "gpt-4o", "provider": "openai", "capabilities": ["chat", "analyze", "review"], "latency": "unknown", "cost": "unknown", "enabled": False},
            {"model": "claude-3-5-sonnet", "provider": "anthropic", "capabilities": ["chat", "analyze", "review"], "latency": "unknown", "cost": "unknown", "enabled": False},
            {"model": "deepseek-chat", "provider": "deepseek", "capabilities": ["chat", "analyze", "review"], "latency": "unknown", "cost": "unknown", "enabled": False},
        ]

    def all(self) -> list[dict[str, Any]]: return [dict(model) for model in self._models]
    def capabilities(self, model: str | None = None) -> list[dict[str, Any]]: return [item for item in self.all() if not model or item["model"] == model]
