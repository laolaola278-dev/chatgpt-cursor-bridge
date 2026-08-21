from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BenchmarkStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class BenchmarkProject:
    id: str
    project: str
    repository: str
    created_at: str = field(default_factory=now)
    status: BenchmarkStatus = BenchmarkStatus.CREATED

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "project": self.project, "repository": self.repository, "createdAt": self.created_at, "status": self.status.value, "readOnly": True}


@dataclass
class BenchmarkCase:
    id: str
    benchmark_id: str
    task_type: str
    description: str
    difficulty: str
    expected_result: str

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "benchmarkId": self.benchmark_id, "taskType": self.task_type, "description": self.description, "difficulty": self.difficulty, "expectedResult": self.expected_result, "readOnly": True}


@dataclass
class BenchmarkRun:
    id: str
    case_id: str
    workflow_id: str | None = None
    execution_loop_id: str | None = None
    agent_ids: list[str] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    status: str = "RECORDED"

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "caseId": self.case_id, "workflowId": self.workflow_id, "executionLoopId": self.execution_loop_id, "agentIds": self.agent_ids, "startedAt": self.started_at, "finishedAt": self.finished_at, "status": self.status, "readOnly": True}


@dataclass
class BenchmarkResult:
    id: str
    run_id: str
    success: bool
    quality_score: float
    rollback_triggered: bool
    verification_result: dict[str, Any]
    human_rating: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "runId": self.run_id, "success": self.success, "qualityScore": self.quality_score, "rollbackTriggered": self.rollback_triggered, "verificationResult": self.verification_result, "humanRating": self.human_rating, "readOnly": True}
