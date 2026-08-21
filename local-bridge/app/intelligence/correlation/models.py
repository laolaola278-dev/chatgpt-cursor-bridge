from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_metadata, sanitize_text, utc_now


class CorrelationRelationship(str, Enum):
    TEMPORAL_ASSOCIATION = "temporal_association"
    DEPENDENCY_CHANGE_FOLLOWED_FAILURE = "dependency_change_followed_failure"
    CODE_CHANGE_FOLLOWED_REGRESSION = "code_change_followed_regression"
    TEST_FAILURE_FOLLOWED_BUILD_FAILURE = "test_failure_followed_build_failure"
    PERFORMANCE_CHANGE_ASSOCIATED_WITH_ERROR = "performance_change_associated_with_error"
    RELATED_ENGINEERING_EVENTS = "related_engineering_events"


@dataclass(frozen=True)
class CorrelationResult:
    correlation_id: str
    project_id: str
    events: list[str] = field(default_factory=list)
    relationship: str = CorrelationRelationship.TEMPORAL_ASSOCIATION.value
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    event_details: list[dict[str, Any]] = field(default_factory=list)
    interpretation: str = "correlation_only"
    causation_claim: bool = False
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "events", ids(self.events))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "relationship", sanitize_text(self.relationship, limit=100))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "event_details", sanitize_metadata({"items": self.event_details}).get("items", []))
        object.__setattr__(self, "interpretation", "correlation_only")
        object.__setattr__(self, "causation_claim", False)
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    @property
    def project(self) -> str:
        return self.project_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "correlationId": self.correlation_id,
            "project_id": self.project_id,
            "projectId": self.project_id,
            "events": list(self.events),
            "event_ids": list(self.events),
            "relationship": self.relationship,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "event_details": self.event_details,
            "eventDetails": self.event_details,
            "interpretation": self.interpretation,
            "causation_claim": False,
            "causationClaim": False,
            "created_at": self.created_at,
            "createdAt": self.created_at,
            "readOnly": True,
        }
