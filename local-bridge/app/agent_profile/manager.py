from __future__ import annotations

from typing import Any

from app.metrics.capability import AgentCapabilityMetrics
from app.metrics.models import AgentMetrics

from .models import AgentProfile
from .storage import AgentProfileStorage


class AgentProfileManager:
    def __init__(self, storage: AgentProfileStorage) -> None: self.storage = storage

    def derive(self, metrics: AgentMetrics, *, role: str = "unknown", failures: list[dict[str, Any]] | None = None) -> AgentProfile:
        capability = AgentCapabilityMetrics().compute(metrics.agent_id, metrics=metrics)
        failures = failures or []
        strengths: list[str] = []
        weaknesses: list[str] = []
        if capability["successRate"] >= 80: strengths.append("reliable execution")
        if capability["reviewScore"] >= 80: strengths.append("strong review quality")
        if capability["failurePatterns"]: weaknesses.append("recurring failure patterns")
        if capability["rollbackRate"] > 20: weaknesses.append("rollback frequency")
        return AgentProfile(metrics.agent_id, role, {"engineering": capability["averageQuality"]}, capability["successRate"], 100 - capability["successRate"], capability["rollbackRate"], capability["averageQuality"], weaknesses, strengths)

    def ranking(self) -> list[AgentProfile]:
        return sorted(self.storage.list(), key=lambda profile: (profile.success_rate, profile.average_quality, profile.review_score), reverse=True)
