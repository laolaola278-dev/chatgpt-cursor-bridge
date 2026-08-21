from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass
class AgentMetrics:
    agent_id: str
    tasks_completed: int = 0
    failed_tasks: int = 0
    review_score: float = 0.0
    average_quality: float = 0.0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at: self.created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def as_dict(self) -> dict[str, Any]:
        return {"agentId": self.agent_id, "tasksCompleted": self.tasks_completed, "failedTasks": self.failed_tasks, "reviewScore": self.review_score, "averageQuality": self.average_quality, "createdAt": self.created_at}
