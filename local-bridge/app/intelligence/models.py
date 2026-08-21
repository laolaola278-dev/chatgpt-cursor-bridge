from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InsightType(str, Enum):
    ARCHITECTURE_RISK = "architecture_risk"
    CODE_SMELL = "code_smell"
    DEPENDENCY_RISK = "dependency_risk"
    TEST_GAP = "test_gap"
    SECURITY_RISK = "security_risk"
    PERFORMANCE_RISK = "performance_risk"
    MAINTENANCE_RISK = "maintenance_risk"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class DecisionStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IMPLEMENTED = "IMPLEMENTED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class RiskFactors:
    impact_scope: int = 0
    changed_files: int = 0
    dependency_count: int = 0
    test_coverage: int | None = None
    rollback_available: bool = True
    security_sensitive: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "impactScope": self.impact_scope,
            "changedFiles": self.changed_files,
            "dependencyCount": self.dependency_count,
            "testCoverage": self.test_coverage,
            "rollbackAvailable": self.rollback_available,
            "securitySensitive": self.security_sensitive,
        }


@dataclass(frozen=True)
class Insight:
    id: str
    project: str
    insight_type: InsightType
    severity: Severity
    title: str
    location: str
    evidence: list[str]
    suggestion: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "type": self.insight_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "location": self.location,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
            "createdAt": self.created_at,
        }


@dataclass(frozen=True)
class Proposal:
    id: str
    project: str
    insight_id: str
    proposal_type: str
    target: dict[str, str]
    reasons: list[str]
    expected_gain: list[str]
    risk: str
    risk_score: int
    status: ProposalStatus = ProposalStatus.DRAFT
    created_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "insightId": self.insight_id,
            "type": self.proposal_type,
            "target": self.target,
            "reason": self.reasons,
            "expectedGain": self.expected_gain,
            "risk": self.risk,
            "riskScore": self.risk_score,
            "status": self.status.value,
            "createdAt": self.created_at,
        }


@dataclass
class Decision:
    id: str
    project: str
    proposal_id: str
    title: str
    context: str
    options: list[dict[str, str]]
    recommendation: str
    simulation_id: str | None = None
    selected_scenario: str | None = None
    confidence: float | None = None
    alternatives: list[str] = field(default_factory=list)
    implementation_plan_id: str | None = None
    execution_status: str | None = None
    status: DecisionStatus = DecisionStatus.DRAFT
    created_at: str = ""
    updated_at: str = ""
    history: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "proposalId": self.proposal_id,
            "title": self.title,
            "context": self.context,
            "options": self.options,
            "recommendation": self.recommendation,
            "simulationId": self.simulation_id,
            "selectedScenario": self.selected_scenario,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "implementationPlanId": self.implementation_plan_id,
            "executionStatus": self.execution_status,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "history": self.history,
        }
