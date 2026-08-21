from __future__ import annotations

from dataclasses import dataclass, field
from secrets import token_hex
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    project_id: str
    decision_id: str | None = None
    observation_ids: list[str] = field(default_factory=list)
    pattern_ids: list[str] = field(default_factory=list)
    prediction_ids: list[str] = field(default_factory=list)
    risk_ids: list[str] = field(default_factory=list)
    strategy_ids: list[str] = field(default_factory=list)
    recommendation_ids: list[str] = field(default_factory=list)
    historical_evidence: list[str] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    confidence: float = 0.0
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        for name in ("observation_ids", "pattern_ids", "prediction_ids", "risk_ids", "strategy_ids", "recommendation_ids", "historical_evidence", "provenance"):
            object.__setattr__(self, name, ids(getattr(self, name)))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    @classmethod
    def build(cls, *, project_id: str, decision_id: str | None = None, observation_ids: list[str] | None = None, pattern_ids: list[str] | None = None, prediction_ids: list[str] | None = None, risk_ids: list[str] | None = None, strategy_ids: list[str] | None = None, recommendation_ids: list[str] | None = None, historical_evidence: list[str] | None = None, provenance: list[str] | None = None, confidence: float = 0.0, bundle_id: str | None = None) -> "EvidenceBundle":
        return cls(bundle_id or f"evidence_{token_hex(8)}", project_id, decision_id, observation_ids or [], pattern_ids or [], prediction_ids or [], risk_ids or [], strategy_ids or [], recommendation_ids or [], historical_evidence or [], provenance or [], confidence)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id, "bundleId": self.bundle_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "decision_id": self.decision_id, "decisionId": self.decision_id,
            "observation_ids": self.observation_ids, "observations": self.observation_ids,
            "pattern_ids": self.pattern_ids, "patterns": self.pattern_ids,
            "prediction_ids": self.prediction_ids, "predictions": self.prediction_ids,
            "risk_ids": self.risk_ids, "risks": self.risk_ids,
            "strategy_ids": self.strategy_ids, "strategies": self.strategy_ids,
            "recommendation_ids": self.recommendation_ids, "recommendations": self.recommendation_ids,
            "historical_evidence": self.historical_evidence, "historicalEvidence": self.historical_evidence,
            "provenance": self.provenance, "confidence": self.confidence,
            "created_at": self.created_at, "createdAt": self.created_at,
            "readOnly": True,
        }
