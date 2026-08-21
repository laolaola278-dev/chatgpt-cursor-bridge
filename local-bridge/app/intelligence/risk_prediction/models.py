from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now


class PredictionType(str, Enum):
    REGRESSION_RISK = "regression_risk"
    BUILD_FAILURE_RISK = "build_failure_risk"
    TEST_FAILURE_RISK = "test_failure_risk"
    DEPENDENCY_RISK = "dependency_risk"
    ARCHITECTURE_RISK = "architecture_risk"
    PERFORMANCE_RISK = "performance_risk"


@dataclass(frozen=True)
class PredictionResult:
    prediction_id: str
    project_id: str
    prediction_type: PredictionType
    prediction: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "prediction", sanitize_text(self.prediction, limit=2000))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "observations", ids(self.observations))
        object.__setattr__(self, "risk_level", str(self.risk_level or "medium").lower())
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    @property
    def project(self) -> str:
        return self.project_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "predictionId": self.prediction_id,
            "project_id": self.project_id,
            "projectId": self.project_id,
            "prediction_type": self.prediction_type.value,
            "predictionType": self.prediction_type.value,
            "prediction": self.prediction,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "observations": list(self.observations),
            "risk_level": self.risk_level,
            "riskLevel": self.risk_level,
            "created_at": self.created_at,
            "createdAt": self.created_at,
            "readOnly": True,
        }
