from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_metadata, sanitize_text, utc_now


class TrendDirection(str, Enum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    VOLATILE = "volatile"


class TrendMetric(str, Enum):
    TEST_FAILURE = "test_failure_trend"
    BUILD_FAILURE = "build_failure_trend"
    ERROR_FREQUENCY = "error_frequency"
    DEPENDENCY_CHANGES = "dependency_changes"
    PERFORMANCE = "performance_trend"
    RISK = "risk_trend"
    CODE_CHANGES = "code_change_frequency"
    REGRESSION = "regression_frequency"


@dataclass(frozen=True)
class TrendResult:
    trend_id: str
    project_id: str
    metric: str
    period: str
    direction: TrendDirection
    change_rate: float
    confidence: float
    evidence: list[str] = field(default_factory=list)
    sample_count: int = 0
    values: list[dict[str, Any]] = field(default_factory=list)
    confidence_sources: dict[str, Any] = field(default_factory=dict)
    confidence_explanation: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "metric", sanitize_text(self.metric, limit=80))
        object.__setattr__(self, "period", sanitize_text(self.period, limit=40))
        object.__setattr__(self, "change_rate", round(float(self.change_rate), 4))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "sample_count", max(0, int(self.sample_count)))
        object.__setattr__(self, "values", sanitize_metadata({"values": self.values}).get("values", []))
        object.__setattr__(self, "confidence_sources", sanitize_metadata(self.confidence_sources))
        object.__setattr__(self, "confidence_explanation", sanitize_text(self.confidence_explanation, limit=1000))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    @property
    def project(self) -> str:
        return self.project_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "trend_id": self.trend_id,
            "trendId": self.trend_id,
            "project_id": self.project_id,
            "projectId": self.project_id,
            "metric": self.metric,
            "period": self.period,
            "direction": self.direction.value,
            "change_rate": self.change_rate,
            "changeRate": self.change_rate,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "sample_count": self.sample_count,
            "sampleCount": self.sample_count,
            "values": self.values,
            "confidence_sources": self.confidence_sources,
            "confidenceSources": self.confidence_sources,
            "confidence_explanation": self.confidence_explanation,
            "confidenceExplanation": self.confidence_explanation,
            "created_at": self.created_at,
            "createdAt": self.created_at,
            "readOnly": True,
        }
