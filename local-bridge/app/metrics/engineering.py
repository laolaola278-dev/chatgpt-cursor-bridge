from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit.logger import AuditLogger
from app.execution_loop import ExecutionLoopOrchestrator
from app.execution_loop.models import LoopStatus
from app.security.permissions import PermissionLevel


class EngineeringMetricsManager:
    """Aggregate loop outcomes into read-only engineering metrics.

    Metrics are derived from persisted loop metadata. They never influence
    permissions and never trigger any action.
    """

    def __init__(self, orchestrator: ExecutionLoopOrchestrator, audit: AuditLogger | None = None, root: str | Path | None = None) -> None:
        self.orchestrator = orchestrator
        self.audit = audit
        self.root = Path(root) if root else Path(".")

    def compute(self, *, project: str | None = None) -> dict[str, Any]:
        loops = self.orchestrator.list_loops(project=project, limit=1000)
        total = len(loops)
        counts = {status.value: 0 for status in LoopStatus}
        completed = failed = rolled_back = recovered = cancelled = 0
        quality_values: list[int] = []
        risk_values: list[str] = []
        durations: list[int] = []
        for loop in loops:
            counts[loop.status.value] = counts.get(loop.status.value, 0) + 1
            if loop.status.value == "COMPLETED":
                completed += 1
            if loop.status.value == "FAILED":
                failed += 1
            if loop.status.value == "ROLLED_BACK":
                rolled_back += 1
            if loop.status.value == "RECOVERED":
                recovered += 1
            if loop.status.value == "CANCELLED":
                cancelled += 1
            quality = loop.quality.get("quality")
            if isinstance(quality, (int, float)):
                quality_values.append(int(quality))
            risk = self._loop_risk(loop)
            if risk:
                risk_values.append(risk)
            duration = loop.verification.get("evidence", {}).get("durationMs") if isinstance(loop.verification, dict) else None
            if isinstance(duration, (int, float)):
                durations.append(int(duration))
        terminal = completed + failed + rolled_back + cancelled
        success_rate = round(completed / terminal * 100, 1) if terminal else 0.0
        rollback_rate = round(rolled_back / terminal * 100, 1) if terminal else 0.0
        avg_quality = round(sum(quality_values) / len(quality_values), 1) if quality_values else 0.0
        avg_duration = round(sum(durations) / len(durations)) if durations else 0
        risk_distribution = {
            "low": risk_values.count("low"),
            "medium": risk_values.count("medium"),
            "high": risk_values.count("high"),
        }
        return {
            "project": project or "*",
            "totalLoops": total,
            "statusCounts": counts,
            "completed": completed,
            "failed": failed,
            "rolledBack": rolled_back,
            "recovered": recovered,
            "cancelled": cancelled,
            "successRate": success_rate,
            "rollbackRate": rollback_rate,
            "averageQuality": avg_quality,
            "averageDurationMs": avg_duration,
            "riskDistribution": risk_distribution,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "readOnly": True,
        }

    def _loop_risk(self, loop) -> str:
        try:
            task = self.orchestrator.execution_manager.storage.get_task(loop.task_ids[0]) if loop.task_ids else None
        except Exception:  # pragma: no cover - defensive
            task = None
        return task.risk if task and task.risk else "medium"

    def snapshot(self, path: str | Path, *, project: str | None = None) -> dict[str, Any]:
        report = self.compute(project=project)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.audit:
            self.audit.record(
                action="engineering_metrics_snapshot",
                path=str(target),
                permission=PermissionLevel.LEVEL_0.value,
                approved=True,
                result="success",
                detail=f"{report['totalLoops']} loop(s) aggregated",
            )
        return report
