"""Phase 32 · Credential-backed provider registry.

Phase 31 builds providers from environment variables. Phase 32 keeps that
behaviour as the fallback and layers the encrypted store on top: when the user
has saved (and approved) a credential for a provider, the key is decrypted in
memory for the duration of one request and injected into a fresh provider
instance. The plaintext never leaves this call stack.

Nothing here executes tools, writes files, or approves anything: it only builds
provider clients for the existing Phase 31 gateway.
"""

from __future__ import annotations

import os
from typing import Any

from app.llm_gateway.providers.base import ProviderError
from app.llm_gateway.registry import KEY_ENV, ProviderRegistry

from .errors import ProviderTestOutcome, connected, not_configured, safe_provider_failure
from .store import AssistantSettingsStore

# The Phase 32 Settings page offers exactly these providers (spec §3). The
# allowlist is fixed; unknown providers are rejected with 404.
VENDOR_PROVIDERS = ("openai", "anthropic", "deepseek")
SELECTABLE_PROVIDERS = ("local",) + VENDOR_PROVIDERS


def _build_vendor(provider: str, *, api_key: str, base_url: str, transport: Any = None) -> Any:
    from app.llm_gateway.providers.anthropic import AnthropicProvider
    from app.llm_gateway.providers.deepseek import DeepSeekProvider
    from app.llm_gateway.providers.openai import OpenAIProvider

    builders = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "deepseek": DeepSeekProvider}
    factory = builders.get(provider)
    if factory is None:
        raise ProviderError(f"Unknown provider '{provider}'", code="unknown_provider", status=404)
    instance = factory(api_key=api_key, transport=transport)
    if base_url:
        # Instance-level override only; the class default stays untouched.
        instance.base_url = base_url
    return instance


def build_registry(
    store: AssistantSettingsStore,
    *,
    transport: Any = None,
    provider_override: str = "",
    api_key_override: str = "",
) -> ProviderRegistry:
    """Provider registry using stored credentials, then env vars, then empty."""
    from app.llm_gateway.providers.local import LocalSimulatorProvider

    providers: dict[str, Any] = {"local": LocalSimulatorProvider()}
    for name in VENDOR_PROVIDERS:
        record = store.active_credential(name)
        if provider_override == name and api_key_override:
            api_key = api_key_override
        else:
            api_key = store.reveal_api_key(name) if record is not None else ""
        if not api_key:
            api_key = os.getenv(KEY_ENV.get(name, ""), "")
        base_url = record.base_url if record is not None else ""
        providers[name] = _build_vendor(name, api_key=api_key, base_url=base_url, transport=transport)
    return ProviderRegistry(providers)


def provider_catalog(store: AssistantSettingsStore, *, transport: Any = None) -> list[dict[str, Any]]:
    """Provider list for the Settings page: status + models, never key values."""
    registry = build_registry(store, transport=transport)
    catalog: list[dict[str, Any]] = []
    for name in SELECTABLE_PROVIDERS:
        instance = registry.get(name)
        record = store.active_credential(name)
        if name == "local":
            status = "connected"
        elif record is not None and record.has_key:
            status = record.connection_status or "connected"
        elif getattr(instance, "enabled", False):
            status = "connected"  # key supplied through the environment
        else:
            status = "not_configured"
        catalog.append(
            {
                "provider": name,
                "displayName": name.capitalize() if name != "openai" else "OpenAI",
                "status": status,
                "requiresApiKey": name != "local",
                "keyEnv": KEY_ENV.get(name, ""),
                "hasStoredKey": bool(record is not None and record.has_key),
                "keyHint": record.key_hint if record is not None else "",
                "keyFingerprint": record.key_fingerprint if record is not None else "",
                "baseUrl": record.base_url if record is not None else getattr(instance, "base_url", ""),
                "selectedModel": record.model if record is not None else "",
                "lastTestedAt": record.last_tested_at if record is not None else "",
                "models": [model["id"] for model in instance.list_models()],
            }
        )
    return catalog


def validate_provider(provider: str) -> str:
    if provider not in SELECTABLE_PROVIDERS:
        raise ProviderError(f"Unknown provider '{provider}'", code="unknown_provider", status=404)
    return provider


def validate_model(store: AssistantSettingsStore, provider: str, model: str, *, transport: Any = None) -> str:
    """Reject a model that the selected provider does not publish."""
    validate_provider(provider)
    if not model:
        return model
    registry = build_registry(store, transport=transport)
    registry.resolve(provider, model)  # raises unknown_model (404)
    return model


def test_provider(
    store: AssistantSettingsStore,
    *,
    provider: str,
    model: str = "",
    transport: Any = None,
    api_key_override: str = "",
) -> ProviderTestOutcome:
    """One minimal round-trip to prove the credential works.

    Returns Connected / Failed / Not configured only; every failure path is
    funnelled through :func:`safe_provider_failure` so no vendor text, header or
    key material can escape.
    """
    validate_provider(provider)
    if provider == "local":
        return connected(provider)
    registry = build_registry(
        store, transport=transport, provider_override=provider, api_key_override=api_key_override
    )
    instance = registry.get(provider)
    if not getattr(instance, "enabled", False):
        return not_configured(provider)
    target_model = model or (instance.list_models()[0]["id"] if instance.list_models() else "")
    if not target_model:
        return not_configured(provider)
    from app.llm_gateway.models import ChatMessage, MessageRole

    probe = [ChatMessage(role=MessageRole.USER, content="ping")]
    try:
        registry.resolve(provider, target_model)
        instance.chat(probe, model=target_model, temperature=0.0, max_tokens=1)
    except Exception as exc:  # noqa: BLE001 - mapped to a safe outcome
        outcome = safe_provider_failure(provider, exc)
        store.record_connection_status(provider, outcome.status)
        return outcome
    store.record_connection_status(provider, "connected")
    return connected(provider)


__all__ = [
    "SELECTABLE_PROVIDERS",
    "VENDOR_PROVIDERS",
    "build_registry",
    "provider_catalog",
    "test_provider",
    "validate_model",
    "validate_provider",
]
