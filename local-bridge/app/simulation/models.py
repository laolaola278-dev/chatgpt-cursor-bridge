from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SimulationStatus(str, Enum):
    DRAFT = "DRAFT"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class ScenarioStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


@dataclass
class Simulation:
    id: str
    project: str
    problem: str
    status: SimulationStatus = SimulationStatus.DRAFT
    created_at: str = ""
    updated_at: str = ""
    history: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "project": self.project, "problem": self.problem, "status": self.status.value, "createdAt": self.created_at, "updatedAt": self.updated_at, "history": self.history, "readOnly": True}


@dataclass(frozen=True)
class Scenario:
    id: str
    simulation_id: str
    name: str
    scenario_type: str
    changes: list[str]
    affected_files: list[str]
    dependent_modules: list[str]
    affected_tests: list[str]
    workflow_stages: list[str]
    memory_impacts: list[str]
    risk_score: int
    impact_score: int
    risk: str
    status: ScenarioStatus = ScenarioStatus.CANDIDATE

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "simulationId": self.simulation_id, "name": self.name, "type": self.scenario_type, "changes": self.changes, "affectedFiles": self.affected_files, "dependentModules": self.dependent_modules, "affectedTests": self.affected_tests, "workflowStages": self.workflow_stages, "memoryImpacts": self.memory_impacts, "riskScore": self.risk_score, "impactScore": self.impact_score, "risk": self.risk, "status": self.status.value, "readOnly": True}


@dataclass(frozen=True)
class Evaluation:
    scenario_id: str
    score: int
    risk: str
    advantages: list[str]
    disadvantages: list[str]
    factors: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {"scenario": self.scenario_id, "score": self.score, "risk": self.risk, "advantages": self.advantages, "disadvantages": self.disadvantages, "factors": self.factors, "readOnly": True}


@dataclass(frozen=True)
class Plan:
    id: str
    simulation_id: str
    scenario_id: str
    content: str
    status: PlanStatus = PlanStatus.DRAFT
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "simulationId": self.simulation_id, "scenarioId": self.scenario_id, "content": self.content, "status": self.status.value, "createdAt": self.created_at, "readOnly": True}
