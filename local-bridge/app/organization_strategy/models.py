"""Organization Engineering Strategy domain models (Phase 24).

Upgrades the organization graph into an engineering strategy layer: cross-
project impact reports, risk propagation reports, candidate engineering
strategies with comparison evaluations, organization decisions with a strict
lifecycle, strategy simulations and strategic recommendations. Every
user-visible write flows through the ApprovalStore; all analysis is read-only
with respect to project source code and memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    stamp = _now()[:19].replace("-", "").replace(":", "").replace("T", "")
    return f"{prefix}_{stamp}"


class StrategyType(str, Enum):
    REFACTOR = "REFACTOR"
    MIGRATION = "MIGRATION"
    STANDARDIZATION = "STANDARDIZATION"
    DEPRECATION = "DEPRECATION"
    TEST_IMPROVEMENT = "TEST_IMPROVEMENT"
    ARCHITECTURE_ALIGNMENT = "ARCHITECTURE_ALIGNMENT"
    RISK_REDUCTION = "RISK_REDUCTION"


class StrategyStatus(str, Enum):
    PROPOSED = "PROPOSED"
    EVALUATED = "EVALUATED"
    SELECTED = "SELECTED"


# Strict lifecycle for organization decisions. Terminal states (REJECTED /
# CANCELLED / SUPERSEDED) accept no further transitions.
DECISION_TRANSITIONS: dict[str, frozenset[str]] = {
    "PROPOSED": frozenset({"ANALYZING"}),
    "ANALYZING": frozenset({"REVIEW_REQUIRED", "REJECTED", "CANCELLED"}),
    "REVIEW_REQUIRED": frozenset({"APPROVAL_REQUIRED", "REJECTED", "CANCELLED"}),
    "APPROVAL_REQUIRED": frozenset({"APPROVED", "REJECTED", "CANCELLED"}),
    "APPROVED": frozenset({"IMPLEMENTATION_PLANNED", "SUPERSEDED", "CANCELLED"}),
    "IMPLEMENTATION_PLANNED": frozenset({"VERIFIED", "SUPERSEDED"}),
    "VERIFIED": frozenset({"SUPERSEDED"}),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
    "SUPERSEDED": frozenset(),
}

STRATEGY_TRANSITIONS: dict[str, frozenset[str]] = {
    "PROPOSED": frozenset({"EVALUATED"}),
    "EVALUATED": frozenset({"SELECTED"}),
    "SELECTED": frozenset(),
}


class DecisionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ANALYZING = "ANALYZING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    IMPLEMENTATION_PLANNED = "IMPLEMENTATION_PLANNED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


@dataclass
class OrganizationImpactReport:
    source_node: str
    affected_projects: list[str] = field(default_factory=list)
    affected_teams: list[str] = field(default_factory=list)
    affected_services: list[str] = field(default_factory=list)
    dependency_paths: list[list[str]] = field(default_factory=list)
    risk_level: str = "low"
    impact_score: int = 0
    confidence: float = 0.0
    blocking_issues: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: _id("orgimp"))
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_node": self.source_node,
            "affected_projects": self.affected_projects,
            "affected_teams": self.affected_teams,
            "affected_services": self.affected_services,
            "dependency_paths": self.dependency_paths,
            "risk_level": self.risk_level,
            "impact_score": self.impact_score,
            "confidence": round(self.confidence, 3),
            "blocking_issues": self.blocking_issues,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrganizationRiskReport:
    source: str
    severity: str
    likelihood: str
    propagation_path: list[dict[str, Any]] = field(default_factory=list)
    affected_nodes: list[dict[str, Any]] = field(default_factory=list)
    affected_projects: list[str] = field(default_factory=list)
    affected_teams: list[str] = field(default_factory=list)
    affected_services: list[str] = field(default_factory=list)
    impact: str = "low"
    confidence: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: _id("orgrisk"))
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.id,
            "source": self.source,
            "severity": self.severity,
            "likelihood": self.likelihood,
            "propagation_path": self.propagation_path,
            "affected_nodes": self.affected_nodes,
            "affected_projects": self.affected_projects,
            "affected_teams": self.affected_teams,
            "affected_services": self.affected_services,
            "impact": self.impact,
            "confidence": round(self.confidence, 3),
            "recommendations": self.recommendations,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class EngineeringStrategy:
    strategy_type: StrategyType
    title: str
    problem: str
    affected_projects: list[str] = field(default_factory=list)
    affected_teams: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    estimated_effort: str = ""
    confidence: float = 0.0
    priority: str = "medium"
    alternatives: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    status: StrategyStatus = StrategyStatus.PROPOSED
    id: str = field(default_factory=lambda: _id("ostrat"))
    created_at: str = field(default_factory=_now)

    def transition(self, target: str) -> None:
        allowed = STRATEGY_TRANSITIONS.get(self.status.value, frozenset())
        if target not in allowed:
            raise ValueError(f"Invalid strategy transition {self.status.value} -> {target}")
        self.status = StrategyStatus(target)

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.id,
            "strategy_type": self.strategy_type.value,
            "title": self.title,
            "problem": self.problem,
            "affected_projects": self.affected_projects,
            "affected_teams": self.affected_teams,
            "benefits": self.benefits,
            "risks": self.risks,
            "estimated_effort": self.estimated_effort,
            "confidence": round(self.confidence, 3),
            "priority": self.priority,
            "alternatives": self.alternatives,
            "evidence": self.evidence,
            "status": self.status.value,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class StrategyEvaluation:
    strategy_id: str
    criteria: dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0
    recommended: bool = False
    id: str = field(default_factory=lambda: _id("osteval"))
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.id,
            "strategy_id": self.strategy_id,
            "criteria": {key: round(value, 3) for key, value in self.criteria.items()},
            "composite_score": round(self.composite_score, 3),
            "recommended": self.recommended,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrganizationDecision:
    organization_id: str
    title: str
    source_graph_nodes: list[str] = field(default_factory=list)
    selected_strategy: str = ""
    alternatives: list[str] = field(default_factory=list)
    confidence: float = 0.0
    impact_report: dict[str, Any] = field(default_factory=dict)
    risk_report: dict[str, Any] = field(default_factory=dict)
    status: DecisionStatus = DecisionStatus.PROPOSED
    history: list[dict[str, str]] = field(default_factory=list)
    id: str = field(default_factory=lambda: _id("ostdec"))
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.history:
            self.history = [{"from": "", "to": self.status.value, "at": self.created_at}]

    def transition(self, target: str) -> None:
        allowed = DECISION_TRANSITIONS.get(self.status.value, frozenset())
        if target not in allowed:
            raise ValueError(f"Invalid decision transition {self.status.value} -> {target}")
        previous = self.status.value
        self.status = DecisionStatus(target)
        self.history.append({"from": previous, "to": target, "at": _now()})

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.id,
            "organization_id": self.organization_id,
            "title": self.title,
            "source_graph_nodes": self.source_graph_nodes,
            "impact_report": self.impact_report,
            "risk_report": self.risk_report,
            "selected_strategy": self.selected_strategy,
            "alternatives": self.alternatives,
            "confidence": round(self.confidence, 3),
            "status": self.status.value,
            "history": self.history,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrganizationStrategySimulation:
    strategy_id: str
    strategy_type: str
    predictions: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: _id("ostsim"))
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.id,
            "strategy_id": self.strategy_id,
            "strategy_type": self.strategy_type,
            "predictions": self.predictions,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class StrategicRecommendation:
    problem: str
    evidence: list[str] = field(default_factory=list)
    recommendation: str = ""
    expected_benefit: str = ""
    risk: str = "low"
    confidence: float = 0.0
    affected_projects: list[str] = field(default_factory=list)
    affected_teams: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: _id("ostrec"))
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.id,
            "problem": self.problem,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "expected_benefit": self.expected_benefit,
            "risk": self.risk,
            "confidence": round(self.confidence, 3),
            "affected_projects": self.affected_projects,
            "affected_teams": self.affected_teams,
            "alternatives": self.alternatives,
            "createdAt": self.created_at,
            "readOnly": True,
        }
