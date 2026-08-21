"""Phase 31 · Provider Registry and Model Registry.

Providers are registered by name; controllers and the gateway resolve through
the registry instead of branching on provider names. The local simulator is
always registered and enabled, so the gateway works without credentials.
Vendor providers register as enabled only when their API key env var is set.
"""

from __future__ import annotations

import os
from typing import Any

from .models import ChatMessage, ChatResult, StreamEvent
from .providers.anthropic import AnthropicProvider
from .providers.base import ProviderError
from .providers.deepseek import DeepSeekProvider
from .providers.local import LocalSimulatorProvider
from .providers.openai import OpenAIProvider

KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


class ProviderRegistry:
    """Name → provider instance registry with a fixed allowlist."""

    def __init__(self, providers: dict[str, Any] | None = None) -> None:
        if providers is None:
            providers = {
                "local": LocalSimulatorProvider(),
                "openai": OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY", "")),
                "anthropic": AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY", "")),
                "deepseek": DeepSeekProvider(api_key=os.getenv("DEEPSEEK_API_KEY", "")),
            }
        self._providers: dict[str, Any] = dict(providers)

    def register(self, name: str, provider: Any) -> None:
        if name in self._providers:
            raise ValueError(f"Provider '{name}' is already registered")
        self._providers[name] = provider

    def get(self, name: str) -> Any:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderError(f"Unknown provider '{name}'", code="unknown_provider", status=404) from exc

    def names(self) -> list[str]:
        return sorted(self._providers)

    def providers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "enabled": bool(provider.enabled),
                "keyEnv": KEY_ENV.get(name, ""),
                "models": [model["id"] for model in provider.list_models()],
            }
            for name, provider in sorted(self._providers.items())
        ]

    def models(self, provider: str | None = None) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for name, instance in sorted(self._providers.items()):
            if provider and name != provider:
                continue
            models.extend(instance.list_models())
        return models

    def resolve(self, provider: str, model: str) -> tuple[Any, dict[str, Any]]:
        """Return the provider instance and its model entry for ``model``."""
        instance = self.get(provider)
        for entry in instance.list_models():
            if entry["id"] == model:
                return instance, entry
        raise ProviderError(
            f"Model '{model}' is not available from provider '{provider}'",
            code="unknown_model",
            status=404,
        )


class ModelRegistry:
    """Flat model catalogue derived from the provider registry."""

    def __init__(self, providers: ProviderRegistry | None = None) -> None:
        self._providers = providers or ProviderRegistry()

    def all(self) -> list[dict[str, Any]]:
        return self._providers.models()

    def by_provider(self, provider: str) -> list[dict[str, Any]]:
        return self._providers.models(provider)

    def get(self, model_id: str) -> dict[str, Any] | None:
        return next((model for model in self.all() if model["id"] == model_id), None)

    def providers(self) -> list[dict[str, Any]]:
        return self._providers.providers()


__all__ = ["KEY_ENV", "ModelRegistry", "ProviderRegistry"]
