"""Quality evaluation response models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityReport:
    quality_score: int
    risk: str
    blocking_issues: list[str]
    checks: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"qualityScore": self.quality_score, "risk": self.risk, "blockingIssues": self.blocking_issues, "checks": self.checks}
