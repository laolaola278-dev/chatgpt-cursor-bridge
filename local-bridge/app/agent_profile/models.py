from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentProfile:
    agent_id: str
    role: str = "unknown"
    domain_scores: dict[str, float] = field(default_factory=dict)
    success_rate: float = 0.0
    failure_rate: float = 0.0
    rollback_rate: float = 0.0
    average_quality: float = 0.0
    weaknesses: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, Any]:
        return {"agentId": self.agent_id, "role": self.role, "domainScores": self.domain_scores, "successRate": self.success_rate, "failureRate": self.failure_rate, "rollbackRate": self.rollback_rate, "averageQuality": self.average_quality, "weaknesses": self.weaknesses, "strengths": self.strengths, "updatedAt": self.updated_at, "readOnly": True}
