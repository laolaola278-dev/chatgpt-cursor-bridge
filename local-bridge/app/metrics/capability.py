from __future__ import annotations

from typing import Any

from .models import AgentMetrics


class AgentCapabilityMetrics:
    def compute(self, agent_id: str, *, metrics: AgentMetrics | None = None, rollback_count: int = 0, failure_patterns: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        record = metrics or AgentMetrics(agent_id=agent_id)
        total = record.tasks_completed + record.failed_tasks
        success_rate = round(record.tasks_completed / total * 100, 1) if total else 0.0
        rollback_rate = min(100.0, max(0.0, round(rollback_count / total * 100, 1))) if total else 0.0
        failures = failure_patterns or []
        return {"agentId": agent_id, "tasksCompleted": record.tasks_completed, "failedTasks": record.failed_tasks, "successRate": success_rate, "reviewScore": record.review_score, "averageQuality": record.average_quality, "rollbackRate": rollback_rate, "failurePatterns": failures, "readOnly": True}

    def aggregate(self, records: list[AgentMetrics], *, rollback_count: int = 0, failure_patterns: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        return [self.compute(record.agent_id, metrics=record, rollback_count=rollback_count, failure_patterns=failure_patterns) for record in records]
