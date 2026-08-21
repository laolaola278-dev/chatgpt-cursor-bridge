from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.security.sandbox import validate_project_name
from app.memory.markdown_store import sanitize_content
from app.security.validator import ValidationFailed


class ProjectMemory:
    CATEGORIES = {"architecture", "decisions", "bugs", "changes"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.memory_root / "project"

    def preview(self, project: str, category: str, content: str) -> str:
        validate_project_name(project)
        if category not in self.CATEGORIES:
            raise ValidationFailed("Unknown project memory category")
        cleaned = sanitize_content(content, self.settings)
        return f"[project memory proposal/{category}]\n\n{cleaned[:1200]}"

    def append_after_approval(self, project: str, category: str, content: str) -> dict[str, Any]:
        validate_project_name(project)
        if category not in self.CATEGORIES:
            raise ValidationFailed("Unknown project memory category")
        cleaned = sanitize_content(content, self.settings)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        directory = self.root / project / category
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = directory / f"{stamp}.md"
        path.write_text(f"# {category.title()}\n\n_Recorded: {now}_\n\n{cleaned}\n", encoding="utf-8")
        return {"project": project, "category": category, "path": str(path), "createdAt": now, "size": path.stat().st_size}

    def history(self, project: str, limit: int = 100) -> list[dict[str, Any]]:
        validate_project_name(project)
        base = self.root / project
        if not base.exists():
            return []
        records: list[dict[str, Any]] = []
        for category in sorted(self.CATEGORIES):
            for path in sorted((base / category).glob("*.md"), reverse=True):
                records.append({"project": project, "category": category, "path": str(path.relative_to(base)), "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"), "size": path.stat().st_size})
        return sorted(records, key=lambda item: item["updatedAt"], reverse=True)[:limit]
