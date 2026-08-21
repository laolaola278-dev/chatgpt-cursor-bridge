from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now


class PatternType(str, Enum):
    HISTORICAL_SIMILARITY = "historical_similarity"
    REPEATED_FAILURE = "repeated_failure"
    REPEATED_CHANGE = "repeated_change"
    REGRESSION = "regression_pattern"
    DEPENDENCY = "dependency_pattern"
    PERFORMANCE_DEGRADATION = "performance_degradation"


@dataclass(frozen=True)
class PatternResult:
    pattern_id: str
    project_id: str
    pattern_type: PatternType
    evidence: list[str] = field(default_factory=list)
    similar_history: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "summary", sanitize_text(self.summary, limit=2000))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    @property
    def project(self) -> str:
        return self.project_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "patternId": self.pattern_id,
            "project_id": self.project_id,
            "projectId": self.project_id,
            "pattern_type": self.pattern_type.value,
            "patternType": self.pattern_type.value,
            "evidence": list(self.evidence),
            "similar_history": self.similar_history,
            "similarHistory": self.similar_history,
            "confidence": self.confidence,
            "summary": self.summary,
            "created_at": self.created_at,
            "createdAt": self.created_at,
            "readOnly": True,
        }
