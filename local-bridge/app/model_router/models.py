"""Models used by the local, provider-agnostic model router."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    ARCHITECTURE = "architecture"
    CODING = "coding"
    DEBUGGING = "debugging"
    TESTING = "testing"
    REVIEW = "review"


class ModelCapability(str, Enum):
    ARCHITECTURE = "architecture"
    CODING = "coding"
    DEBUGGING = "debugging"
    TESTING = "testing"
    REVIEW = "review"
    TOOL_USE = "tool_use"
    LONG_CONTEXT = "long_context"


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    provider: str
    display_name: str
    capabilities: frozenset[ModelCapability]
    context_window: int = 32_000
    enabled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "displayName": self.display_name,
            "capabilities": sorted(capability.value for capability in self.capabilities),
            "contextWindow": self.context_window,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class TaskClassification:
    task_type: TaskType
    confidence: float
    signals: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "taskType": self.task_type.value,
            "confidence": self.confidence,
            "signals": list(self.signals),
        }


@dataclass(frozen=True)
class ModelRoute:
    classification: TaskClassification
    model: ModelDescriptor

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.as_dict(),
            "model": self.model.as_dict(),
        }
