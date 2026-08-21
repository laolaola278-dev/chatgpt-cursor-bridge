from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from .models import TimelineEntry


class EvolutionTimeline:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, project: str) -> Path:
        return self.root / project / "evolution.jsonl"

    def append_after_approval(self, project: str, kind: str, title: str, content: str, source_id: str | None = None) -> dict[str, Any]:
        entry = TimelineEntry(f"evo_{secrets.token_hex(8)}", project, kind, title, content, source_id)
        path = self._path(project); path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.as_dict(), ensure_ascii=False) + "\n")
        return entry.as_dict()

    def list(self, project: str, limit: int = 200) -> list[dict[str, Any]]:
        path = self._path(project)
        if not path.exists(): return []
        entries: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip(): entries.append(json.loads(line))
        return entries[-limit:][::-1]

    def derive(self, project: str, *, decisions: list[Any] = [], loops: list[Any] = [], failures: list[Any] = []) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in decisions:
            item_id = item.get("id") if isinstance(item, dict) else getattr(item, "id", "")
            title = item.get("title") if isinstance(item, dict) else getattr(item, "title", "Decision")
            entries.append(TimelineEntry(f"decision:{item_id}", project, "decision", title, "Engineering decision", item_id).as_dict())
        for item in loops:
            item_id = item.get("id") if isinstance(item, dict) else getattr(item, "id", "")
            status = item.get("status") if isinstance(item, dict) else getattr(item, "status", "")
            status = getattr(status, "value", status)
            entries.append(TimelineEntry(f"execution:{item_id}", project, "execution", f"Execution {item_id}", f"Status: {status}", item_id).as_dict())
        for item in failures:
            item_id = item.get("id") if isinstance(item, dict) else getattr(item, "id", "")
            entries.append(TimelineEntry(f"failure:{item_id}", project, "failure", f"Failure {item_id}", "Failure pattern detected", item_id).as_dict())
        return entries
