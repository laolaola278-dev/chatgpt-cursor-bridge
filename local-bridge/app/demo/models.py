from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class DemoScenario:
    id: str
    name: str
    issue: str
    stages: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "issue": self.issue, "stages": self.stages, "createdAt": self.created_at, "readOnly": True}
