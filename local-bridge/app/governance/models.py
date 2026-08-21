"""Governance domain models.

All governance analysis is read-only with respect to project source code and
memory. Writes are restricted to governance telemetry (health/drift snapshots,
debt items, policy events) and every user-visible mutation flows through the
ApprovalStore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DebtStatus(str, Enum):
    """Technical debt item lifecycle (strict forward chain)."""

    OPEN = "OPEN"
    ANALYZING = "ANALYZING"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    RESOLVED = "RESOLVED"
    VERIFIED = "VERIFIED"


@dataclass
class GovernanceWarning:
    code: str
    severity: str  # low | medium | high
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass
class GovernanceRecommendation:
    code: str
    priority: str  # low | medium | high
    suggestion: str

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "priority": self.priority, "suggestion": self.suggestion}


@dataclass
class HealthTrend:
    dimension: str
    delta: float
    direction: str  # improving | declining | stable

    def as_dict(self) -> dict[str, Any]:
        return {"dimension": self.dimension, "delta": round(self.delta, 1), "direction": self.direction}


@dataclass
class EngineeringHealthReport:
    project: str
    health_score: int
    risk_level: str
    components: dict[str, Any] = field(default_factory=dict)
    trends: list[HealthTrend] = field(default_factory=list)
    warnings: list[GovernanceWarning] = field(default_factory=list)
    recommendations: list[GovernanceRecommendation] = field(default_factory=list)
    created_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "healthScore": self.health_score,
            "riskLevel": self.risk_level,
            "components": self.components,
            "trends": [trend.as_dict() for trend in self.trends],
            "warnings": [warning.as_dict() for warning in self.warnings],
            "recommendations": [rec.as_dict() for rec in self.recommendations],
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class DebtItem:
    id: str
    project: str
    category: str
    severity: str
    source: str
    affected_components: list[str] = field(default_factory=list)
    estimated_cost: int = 0
    risk: str = "low"
    status: DebtStatus = DebtStatus.OPEN
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "category": self.category,
            "severity": self.severity,
            "source": self.source,
            "affectedComponents": self.affected_components,
            "estimatedCost": self.estimated_cost,
            "risk": self.risk,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "readOnly": True,
        }


@dataclass
class PolicyEvaluation:
    policy: str
    result: str  # pass | warning | approval_required
    severity: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "result": self.result,
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
            "createdAt": self.created_at,
            "readOnly": True,
        }
