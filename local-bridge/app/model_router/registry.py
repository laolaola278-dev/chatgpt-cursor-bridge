"""Capability registry and provider abstraction.

The bridge deliberately ships with metadata-only providers. This phase selects
models but does not invoke a remote provider or require credentials.
"""

from __future__ import annotations

from typing import Protocol

from .models import ModelCapability, ModelDescriptor


class ModelProvider(Protocol):
    """Provider boundary for a future execution adapter.

    Routing never calls this protocol. A future adapter must still receive an
    approved action before it can perform any tool or model operation.
    """

    @property
    def name(self) -> str: ...

    def list_models(self) -> list[ModelDescriptor]: ...


class CapabilityRegistry:
    def __init__(self, models: list[ModelDescriptor] | None = None) -> None:
        self._models = models or [
            ModelDescriptor(
                id="local/architect-v1",
                provider="local",
                display_name="Local Architect",
                capabilities=frozenset({
                    ModelCapability.ARCHITECTURE,
                    ModelCapability.REVIEW,
                    ModelCapability.LONG_CONTEXT,
                }),
                context_window=64_000,
            ),
            ModelDescriptor(
                id="local/coder-v1",
                provider="local",
                display_name="Local Coder",
                capabilities=frozenset({
                    ModelCapability.CODING,
                    ModelCapability.DEBUGGING,
                    ModelCapability.TOOL_USE,
                }),
            ),
            ModelDescriptor(
                id="local/tester-v1",
                provider="local",
                display_name="Local Tester",
                capabilities=frozenset({
                    ModelCapability.TESTING,
                    ModelCapability.DEBUGGING,
                    ModelCapability.TOOL_USE,
                }),
            ),
            ModelDescriptor(
                id="local/reviewer-v1",
                provider="local",
                display_name="Local Reviewer",
                capabilities=frozenset({
                    ModelCapability.REVIEW,
                    ModelCapability.TESTING,
                    ModelCapability.LONG_CONTEXT,
                }),
            ),
        ]

    def all(self) -> list[ModelDescriptor]:
        return [model for model in self._models if model.enabled]

    def get(self, model_id: str) -> ModelDescriptor | None:
        return next((model for model in self.all() if model.id == model_id), None)

    def for_capability(self, capability: ModelCapability) -> list[ModelDescriptor]:
        return [model for model in self.all() if capability in model.capabilities]
