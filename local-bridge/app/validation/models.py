from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ValidationStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ValidationScenarioType(str, Enum):
    BUG_FIX = "BUG_FIX"
    FEATURE = "FEATURE"
    REFACTOR = "REFACTOR"
    ARCHITECTURE_CHANGE = "ARCHITECTURE_CHANGE"


@dataclass
class ValidationProject:
    id: str
    project: str
    repository: str
    language: str = "unknown"
    framework: str = "unknown"
    created_at: str = field(default_factory=now)
    status: ValidationStatus = ValidationStatus.CREATED

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "project": self.project, "repository": self.repository, "language": self.language, "framework": self.framework, "createdAt": self.created_at, "status": self.status.value, "readOnly": True}


@dataclass
class ValidationScenario:
    id: str
    validation_id: str
    scenario_type: ValidationScenarioType
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "validationId": self.validation_id, "scenarioType": self.scenario_type.value, "description": self.description, "readOnly": True}


@dataclass
class ValidationRun:
    id: str
    scenario_id: str
    workflow_id: str | None = None
    execution_loop_id: str | None = None
    agents: list[str] = field(default_factory=list)
    result: str = "RECORDED"
    human_rating: float | None = None
    created_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "scenarioId": self.scenario_id, "workflowId": self.workflow_id, "executionLoopId": self.execution_loop_id, "agents": self.agents, "result": self.result, "humanRating": self.human_rating, "createdAt": self.created_at, "readOnly": True}
