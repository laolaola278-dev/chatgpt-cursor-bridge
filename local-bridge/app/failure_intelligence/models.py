from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class FailurePattern:
    id: str
    project: str
    category: str
    signature: str
    occurrences: int
    severity: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "project": self.project, "category": self.category, "signature": self.signature, "occurrences": self.occurrences, "severity": self.severity, "evidence": self.evidence, "createdAt": self.created_at, "readOnly": True}
