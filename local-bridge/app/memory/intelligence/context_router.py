"""Role-aware read-only context routing."""
from __future__ import annotations

from typing import Any

from app.config import Settings
from .context_builder import ContextBuilder


class ContextRouter:
    DOCUMENTS: dict[str, tuple[str, ...]] = {
        "PLANNER": ("requirements", "tasks"),
        "ARCHITECT": ("requirements", "decisions", "architecture"),
        "CODER": ("architecture", "code diff"),
        "TESTER": ("implementation", "bugs", "test history"),
        "REVIEWER": ("all reports", "quality score"),
    }

    def __init__(self, settings: Settings) -> None: self.builder = ContextBuilder(settings)

    def route(self, *, project: str, agent_role: str, current_task: str = "") -> dict[str, Any]:
        role = agent_role.strip().upper()
        if role not in self.DOCUMENTS: raise ValueError("Unknown agent role")
        bundle = self.builder.build(project=project, agent_role=role, current_task=current_task)
        return {**bundle, "route": list(self.DOCUMENTS[role]), "readOnly": True}
