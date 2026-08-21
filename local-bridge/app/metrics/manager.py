from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel
from app.security.validator import ResourceNotFound, ValidationFailed
from .models import AgentMetrics


class MetricsManager:
    def __init__(self, root: str | Path, audit: AuditLogger | None = None) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True); self.audit = audit; self._lock = Lock()

    def _path(self, agent_id: str) -> Path: return self.root / f"{agent_id}.json"
    def get(self, agent_id: str) -> AgentMetrics:
        if not agent_id.startswith("ag_"): raise ValidationFailed("Invalid agent id")
        path = self._path(agent_id)
        if not path.exists(): return AgentMetrics(agent_id=agent_id)
        try:
            value = json.loads(path.read_text(encoding="utf-8")); return AgentMetrics(agent_id=value["agentId"], tasks_completed=int(value.get("tasksCompleted", 0)), failed_tasks=int(value.get("failedTasks", 0)), review_score=float(value.get("reviewScore", 0)), average_quality=float(value.get("averageQuality", 0)), created_at=value.get("createdAt", ""))
        except (OSError, ValueError, KeyError) as exc: raise ValueError("Metrics record is corrupted") from exc

    def save(self, metrics: AgentMetrics) -> AgentMetrics:
        with self._lock: self._path(metrics.agent_id).write_text(json.dumps(metrics.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if self.audit: self.audit.record(action="agent_metrics_updated", path=f"agent/{metrics.agent_id}/metrics", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail="Metrics only; permissions unchanged")
        return metrics

    def record_task(self, agent_id: str, *, completed: bool, quality: float | None = None) -> AgentMetrics:
        metrics = self.get(agent_id)
        if completed: metrics.tasks_completed += 1
        else: metrics.failed_tasks += 1
        if quality is not None:
            total = metrics.tasks_completed + metrics.failed_tasks
            metrics.average_quality = ((metrics.average_quality * max(0, total - 1)) + max(0, min(100, quality))) / max(1, total)
        return self.save(metrics)

    def record_review(self, agent_id: str, score: float) -> AgentMetrics:
        metrics = self.get(agent_id); metrics.review_score = max(0, min(100, float(score))); return self.save(metrics)

    def list(self) -> list[AgentMetrics]:
        return [self.get(path.stem) for path in sorted(self.root.glob("ag_*.json"))]
