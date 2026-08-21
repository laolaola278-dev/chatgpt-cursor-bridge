from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.intelligence.common import ensure_project, safe_source, sanitize_metadata, sanitize_text, utc_now


class ObservationType(str, Enum):
    CODE_CHANGE = "code_change"
    TEST_RESULT = "test_result"
    BUILD_RESULT = "build_result"
    GIT_DIFF = "git_diff"
    DEPENDENCY_CHANGE = "dependency_change"
    ERROR_EVENT = "error_event"
    PERFORMANCE_EVENT = "performance_event"
    ARCHITECTURE_EVENT = "architecture_event"


class ObservationRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Observation:
    id: str
    project_id: str
    timestamp: str
    type: ObservationType
    source: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    risk_level: str = ObservationRisk.LOW.value

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "source", safe_source(self.source))
        object.__setattr__(self, "summary", sanitize_text(self.summary, limit=4000).strip())
        object.__setattr__(self, "metadata", sanitize_metadata(self.metadata))
        risk = str(self.risk_level or ObservationRisk.LOW.value).lower()
        if risk not in {item.value for item in ObservationRisk}:
            risk = ObservationRisk.MEDIUM.value
        object.__setattr__(self, "risk_level", risk)

    @property
    def project(self) -> str:
        """Compatibility alias used by older project intelligence code."""
        return self.project_id

    @classmethod
    def build(
        cls,
        *,
        project_id: str,
        type: ObservationType | str,
        source: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
        risk_level: str = ObservationRisk.LOW.value,
        observation_id: str | None = None,
        timestamp: str | None = None,
    ) -> "Observation":
        from secrets import token_hex

        try:
            parsed = type if isinstance(type, ObservationType) else ObservationType(str(type).lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported observation type: {type}") from exc
        return cls(
            id=observation_id or f"obs_{token_hex(8)}",
            project_id=project_id,
            timestamp=timestamp or utc_now(),
            type=parsed,
            source=source,
            summary=summary,
            metadata=metadata or {},
            risk_level=risk_level,
        )

    def as_dict(self) -> dict[str, Any]:
        # Keep the canonical snake_case fields from the Phase 25 contract and
        # camelCase aliases for the existing extension API convention.
        return {
            "id": self.id,
            "project_id": self.project_id,
            "projectId": self.project_id,
            "timestamp": self.timestamp,
            "type": self.type.value,
            "source": self.source,
            "summary": self.summary,
            "metadata": self.metadata,
            "risk_level": self.risk_level,
            "riskLevel": self.risk_level,
            "readOnly": True,
        }

    @classmethod
    def from_row(cls, row: Any) -> "Observation":
        import json

        return cls(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            timestamp=str(row["timestamp"]),
            type=ObservationType(str(row["type"])),
            source=str(row["source"]),
            summary=str(row["summary"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
            risk_level=str(row["risk_level"]),
        )
