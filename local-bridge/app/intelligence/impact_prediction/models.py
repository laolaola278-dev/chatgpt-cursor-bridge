from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_metadata, sanitize_text, utc_now


class ImpactRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ImpactPrediction:
    prediction_id: str
    project_id: str
    affected_files: list[str] = field(default_factory=list)
    affected_modules: list[str] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)
    risk_level: ImpactRiskLevel | str = ImpactRiskLevel.LOW
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    why_risky: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    changed_symbols: list[str] = field(default_factory=list)
    dependency_paths: list[list[str]] = field(default_factory=list)
    confidence_sources: dict[str, Any] = field(default_factory=dict)
    confidence_explanation: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        for name in ("affected_files", "affected_modules", "affected_tests", "evidence", "why_risky", "changed_files", "changed_symbols"):
            object.__setattr__(self, name, ids(getattr(self, name)))
        object.__setattr__(self, "risk_level", str(self.risk_level.value if isinstance(self.risk_level, ImpactRiskLevel) else self.risk_level).upper())
        if self.risk_level not in {item.value for item in ImpactRiskLevel}:
            object.__setattr__(self, "risk_level", ImpactRiskLevel.MEDIUM.value)
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "dependency_paths", sanitize_metadata({"paths": self.dependency_paths}).get("paths", []))
        object.__setattr__(self, "confidence_sources", sanitize_metadata(self.confidence_sources))
        object.__setattr__(self, "confidence_explanation", sanitize_text(self.confidence_explanation, limit=1000))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    @property
    def project(self) -> str:
        return self.project_id

    @property
    def risk(self) -> str:
        return self.risk_level

    def as_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id, "predictionId": self.prediction_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "affected_files": self.affected_files, "affectedFiles": self.affected_files,
            "affected_modules": self.affected_modules, "affectedModules": self.affected_modules,
            "affected_tests": self.affected_tests, "affectedTests": self.affected_tests,
            "risk_level": self.risk_level, "riskLevel": self.risk_level,
            "confidence": self.confidence, "evidence": self.evidence,
            "why_risky": self.why_risky, "whyRisky": self.why_risky,
            "changed_files": self.changed_files, "changedFiles": self.changed_files,
            "changed_symbols": self.changed_symbols, "changedSymbols": self.changed_symbols,
            "dependency_paths": self.dependency_paths, "dependencyPaths": self.dependency_paths,
            "confidence_sources": self.confidence_sources, "confidenceSources": self.confidence_sources,
            "confidence_explanation": self.confidence_explanation, "confidenceExplanation": self.confidence_explanation,
            "created_at": self.created_at, "createdAt": self.created_at,
            "readOnly": True,
        }
