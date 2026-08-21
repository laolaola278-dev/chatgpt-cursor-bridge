from __future__ import annotations

import secrets
from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel

from .models import BenchmarkCase, BenchmarkProject, BenchmarkStatus
from .storage import BenchmarkStorage

_ALLOWED = {
    BenchmarkStatus.CREATED: {BenchmarkStatus.RUNNING, BenchmarkStatus.CANCELLED},
    BenchmarkStatus.RUNNING: {BenchmarkStatus.COMPLETED, BenchmarkStatus.FAILED, BenchmarkStatus.CANCELLED},
    BenchmarkStatus.COMPLETED: set(), BenchmarkStatus.FAILED: set(), BenchmarkStatus.CANCELLED: set(),
}


class BenchmarkManager:
    def __init__(self, storage: BenchmarkStorage, audit: AuditLogger | None = None) -> None:
        self.storage = storage; self.audit = audit

    def create(self, project: str, repository: str, cases: list[dict[str, Any]]) -> BenchmarkProject:
        benchmark = BenchmarkProject(f"bench_{secrets.token_hex(8)}", project, repository)
        self.storage.save_project(benchmark)
        records = [BenchmarkCase(f"case_{secrets.token_hex(6)}", benchmark.id, str(item.get("taskType", "engineering")), str(item.get("description", "")), str(item.get("difficulty", "medium")), str(item.get("expectedResult", ""))) for item in cases]
        self.storage.save_cases(records)
        self._audit("benchmark_created", project, f"{benchmark.id} with {len(records)} case(s)")
        return benchmark

    def transition(self, benchmark_id: str, status: str) -> BenchmarkProject:
        current = self.storage.get(benchmark_id)
        if current is None: raise KeyError(benchmark_id)
        target = BenchmarkStatus(status)
        if target not in _ALLOWED[current.status]: raise ValueError(f"Invalid benchmark transition {current.status.value} -> {target.value}")
        updated = self.storage.update_status(benchmark_id, target)
        self._audit("benchmark_transition", updated.project, f"{benchmark_id}: {current.status.value} -> {target.value}")
        return updated

    def _audit(self, action: str, project: str, detail: str) -> None:
        if self.audit: self.audit.record(action=action, path=f"{project}:benchmark", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=detail)
