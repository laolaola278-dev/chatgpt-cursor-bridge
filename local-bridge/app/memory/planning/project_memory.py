from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.memory.markdown_store import sanitize_content
from app.security.sandbox import validate_project_name
from app.security.validator import ValidationFailed


class PlanningMemory:
    DOCUMENTS = {"plans": "engineering-plans.md", "architecture": "architecture-options.md", "tradeoffs": "tradeoff-history.md"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.memory_root / "planning"

    def preview(self, project: str, category: str, content: str) -> str:
        cleaned = sanitize_content(content, self.settings)
        return f"[planning memory proposal/{category}] {self._path(project, category).name}\n\n{cleaned[:1200]}"

    def _path(self, project: str, category: str, create_dir: bool = False) -> Path:
        validate_project_name(project)
        if category not in self.DOCUMENTS: raise ValidationFailed("Unknown planning memory category")
        directory = self.root / project
        if create_dir: directory.mkdir(parents=True, exist_ok=True)
        return directory / self.DOCUMENTS[category]

    def append_after_approval(self, project: str, category: str, content: str) -> dict[str, Any]:
        cleaned = sanitize_content(content, self.settings)
        path = self._path(project, category, True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = f"\n---\n\n_Entry: {now}_\n\n{cleaned}\n"
        with path.open("a", encoding="utf-8") as handle: handle.write(entry)
        return {"project": project, "category": category, "document": path.name, "path": str(path), "createdAt": now, "size": path.stat().st_size}

    def history(self, project: str, limit: int = 100) -> list[dict[str, Any]]:
        validate_project_name(project)
        directory = self.root / project
        if not directory.exists(): return []
        output = []
        for category, filename in self.DOCUMENTS.items():
            path = directory / filename
            if path.is_file(): output.append({"project": project, "category": category, "document": filename, "path": str(path.relative_to(self.root)), "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"), "size": path.stat().st_size})
        return sorted(output, key=lambda item: item["updatedAt"], reverse=True)[:limit]
