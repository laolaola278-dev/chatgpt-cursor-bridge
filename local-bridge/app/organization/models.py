"""Organization Engineering Intelligence domain models (Phase 22).

Company -> Teams -> Projects -> Services -> Repositories, plus org-level
architecture decisions and incidents, a cross-project pattern library and
aggregated organization health. All analysis is read-only with respect to
project source code; every user-visible write flows through the ApprovalStore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OrgEntityType(str, Enum):
    COMPANY = "COMPANY"
    TEAM = "TEAM"
    PROJECT = "PROJECT"
    SERVICE = "SERVICE"
    REPOSITORY = "REPOSITORY"
    ARCHITECTURE_DECISION = "ARCHITECTURE_DECISION"
    INCIDENT = "INCIDENT"


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"


class PatternCategory(str, Enum):
    SUCCESSFUL_REFACTOR = "successful_refactor"
    BAD_MIGRATION = "bad_migration"
    DEPLOYMENT_FAILURE = "deployment_failure"
    ARCHITECTURE_SUCCESS = "architecture_success"


@dataclass
class OrgEntity:
    entity_type: OrgEntityType
    name: str
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"org_{self.entity_type.value.lower()[:4]}_{_now()[:19].replace('-', '').replace(':', '').replace('T', '')}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.entity_type.value,
            "name": self.name,
            "parentId": self.parent_id,
            "metadata": self.metadata,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrgGraph:
    company: dict[str, Any] | None = None
    teams: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    repositories: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    incidents: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "teams": self.teams,
            "projects": self.projects,
            "services": self.services,
            "repositories": self.repositories,
            "decisions": self.decisions,
            "incidents": self.incidents,
            "readOnly": True,
        }


@dataclass
class OrgDecision:
    project: str
    title: str
    context: str
    decision: str
    consequence: str
    status: str = "APPROVED"
    id: str = ""
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"orgd_{_now()[:19].replace('-', '').replace(':', '').replace('T', '')}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "title": self.title,
            "context": self.context,
            "decision": self.decision,
            "consequence": self.consequence,
            "status": self.status,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrgIncident:
    project: str
    title: str
    summary: str
    severity: str = "medium"
    service: str = ""
    signature: str = ""
    status: IncidentStatus = IncidentStatus.OPEN
    id: str = ""
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"inci_{_now()[:19].replace('-', '').replace(':', '').replace('T', '')}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "service": self.service,
            "title": self.title,
            "summary": self.summary,
            "severity": self.severity,
            "signature": self.signature,
            "status": self.status.value,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrgPattern:
    category: PatternCategory
    name: str
    summary: str
    project: str
    tags: list[str] = field(default_factory=list)
    id: str = ""
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"pat_{_now()[:19].replace('-', '').replace(':', '').replace('T', '')}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category.value,
            "name": self.name,
            "summary": self.summary,
            "project": self.project,
            "tags": self.tags,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class OrgFailurePattern:
    project: str
    category: str
    signature: str
    occurrences: int = 1
    severity: str = "low"
    id: str = ""
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"fp_{_now()[:19].replace('-', '').replace(':', '').replace('T', '')}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "category": self.category,
            "signature": self.signature,
            "occurrences": self.occurrences,
            "severity": self.severity,
            "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass
class SimilarFailureMatch:
    source_project: str
    target_project: str
    category: str
    signature: str
    match_score: float
    message: str = ""

    def __post_init__(self) -> None:
        if not self.message:
            self.message = f"Similar failure detected from {self.source_project}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "sourceProject": self.source_project,
            "targetProject": self.target_project,
            "category": self.category,
            "signature": self.signature,
            "matchScore": round(self.match_score, 3),
            "message": self.message,
            "readOnly": True,
        }


@dataclass
class OrgHealthReport:
    org: str
    org_health_score: int
    project_count: int
    health_by_project: list[dict[str, Any]] = field(default_factory=list)
    debt_ranking: list[dict[str, Any]] = field(default_factory=list)
    risk_trends: list[dict[str, Any]] = field(default_factory=list)
    failure_patterns: list[dict[str, Any]] = field(default_factory=list)
    agent_effectiveness: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "org": self.org,
            "orgHealthScore": self.org_health_score,
            "projectCount": self.project_count,
            "healthByProject": self.health_by_project,
            "debtRanking": self.debt_ranking,
            "riskTrends": self.risk_trends,
            "failurePatterns": self.failure_patterns,
            "agentEffectiveness": self.agent_effectiveness,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "createdAt": self.created_at,
            "readOnly": True,
        }
