"""Architecture drift models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DriftIssue:
    issue_type: str  # unrecorded_dependency | module_boundary_change | circular_dependency | design_decision_drift | deprecated_component_usage
    severity: str  # low | medium | high
    location: str
    evidence: list[str] = field(default_factory=list)
    recommendation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.issue_type,
            "severity": self.severity,
            "location": self.location,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
        }


@dataclass
class ArchitectureDriftReport:
    project: str
    drift_score: int  # 0 (clean) .. 100 (heavy drift)
    issues: list[DriftIssue] = field(default_factory=list)
    risk_level: str = "low"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "driftScore": self.drift_score,
            "riskLevel": self.risk_level,
            "issues": [issue.as_dict() for issue in self.issues],
            "createdAt": self.created_at,
            "readOnly": True,
        }
