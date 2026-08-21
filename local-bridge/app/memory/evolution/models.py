from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TimelineEntry:
    id: str
    project: str
    kind: str
    title: str
    content: str
    source_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "project": self.project, "kind": self.kind, "title": self.title, "content": self.content, "sourceId": self.source_id, "createdAt": self.created_at, "readOnly": True}
