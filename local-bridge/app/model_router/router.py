"""Deterministic task classifier and capability-aware model router."""

from __future__ import annotations

import re
from typing import Iterable

from .models import ModelCapability, ModelRoute, TaskClassification, TaskType
from .registry import CapabilityRegistry


_KEYWORDS: dict[TaskType, tuple[str, ...]] = {
    TaskType.ARCHITECTURE: ("architect", "architecture", "design", "schema", "system", "结构", "架构"),
    TaskType.CODING: ("implement", "code", "coding", "feature", "function", "代码", "实现"),
    TaskType.DEBUGGING: ("debug", "bug", "error", "failure", "fix", "crash", "修复", "错误"),
    TaskType.TESTING: ("test", "testing", "pytest", "coverage", "verify", "测试", "验证"),
    TaskType.REVIEW: ("review", "audit", "risk", "quality", "安全审查", "评审"),
}


class ModelRouter:
    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or CapabilityRegistry()

    def classify(self, task: str, task_type: str | None = None) -> TaskClassification:
        if task_type:
            try:
                return TaskClassification(TaskType(task_type.strip().lower()), 1.0, ("explicit task type",))
            except ValueError:
                pass
        normalized = (task or "").strip().lower()
        scores = {
            kind: [keyword for keyword in keywords if re.search(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])", normalized)]
            for kind, keywords in _KEYWORDS.items()
        }
        ranked = sorted(scores.items(), key=lambda item: (len(item[1]), item[0].value), reverse=True)
        selected, signals = ranked[0]
        if not signals:
            selected, signals = TaskType.CODING, ["default engineering task"]
        confidence = min(0.99, 0.55 + (0.1 * len(signals)))
        return TaskClassification(selected, confidence, tuple(signals))

    def route(self, task: str, *, task_type: str | None = None, preferred_model: str | None = None) -> ModelRoute:
        classification = self.classify(task, task_type)
        if preferred_model:
            preferred = self.registry.get(preferred_model)
            required = ModelCapability(classification.task_type.value)
            if preferred and required in preferred.capabilities:
                return ModelRoute(classification, preferred)
        candidates = self.registry.for_capability(ModelCapability(classification.task_type.value))
        if not candidates:
            candidates = self.registry.all()
        model = max(
            candidates,
            key=lambda item: (
                classification.task_type.value in item.id,
                classification.task_type.value in item.display_name.lower(),
                item.context_window,
                item.id,
            ),
        )
        return ModelRoute(classification, model)

    def descriptors(self) -> list[dict[str, object]]:
        return [model.as_dict() for model in self.registry.all()]
