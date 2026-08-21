from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_metadata, sanitize_text, utc_now


class DependencyRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DependencyRisk:
    risk_id: str
    project_id: str
    dependency: str
    risk: DependencyRiskLevel | str
    reason: str
    historical_evidence: list[str] = field(default_factory=list)
    affected_components: list[str] = field(default_factory=list)
    confidence: float = 0.0
    change_type: str = "unknown"
    old_version: str = ""
    new_version: str = ""
    transitive: bool = False
    concentration: float | None = None
    coupling: float | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "dependency", sanitize_text(self.dependency, limit=240).strip())
        object.__setattr__(self, "risk", str(self.risk.value if isinstance(self.risk, DependencyRiskLevel) else self.risk).upper())
        if self.risk not in {item.value for item in DependencyRiskLevel}:
            object.__setattr__(self, "risk", DependencyRiskLevel.MEDIUM.value)
        object.__setattr__(self, "reason", sanitize_text(self.reason, limit=2000))
        object.__setattr__(self, "historical_evidence", ids(self.historical_evidence))
        object.__setattr__(self, "affected_components", ids(self.affected_components))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "change_type", sanitize_text(self.change_type, limit=80))
        object.__setattr__(self, "old_version", sanitize_text(self.old_version, limit=100))
        object.__setattr__(self, "new_version", sanitize_text(self.new_version, limit=100))
        for name in ("concentration", "coupling"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, round(max(0.0, min(1.0, float(value))), 3))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    @property
    def project(self) -> str:
        return self.project_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id, "riskId": self.risk_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "dependency": self.dependency, "risk": self.risk,
            "reason": self.reason, "historical_evidence": self.historical_evidence,
            "historicalEvidence": self.historical_evidence,
            "affected_components": self.affected_components,
            "affectedComponents": self.affected_components,
            "confidence": self.confidence, "change_type": self.change_type,
            "changeType": self.change_type, "old_version": self.old_version,
            "oldVersion": self.old_version, "new_version": self.new_version,
            "newVersion": self.new_version, "transitive": self.transitive,
            "concentration": self.concentration, "coupling": self.coupling,
            "created_at": self.created_at, "createdAt": self.created_at,
            "readOnly": True,
        }
