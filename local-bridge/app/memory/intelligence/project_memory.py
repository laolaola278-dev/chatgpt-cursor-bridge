"""Approval-only storage for durable Phase 13 engineering knowledge.

This module intentionally exposes a write method named ``append_after_approval``
so callers must place it behind the existing ApprovalStore. Read access remains
available through ``history`` and never changes memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.memory.markdown_store import sanitize_content
from app.security.sandbox import validate_project_name
from app.security.validator import ValidationFailed


class ProjectIntelligenceMemory:
    """Persist approved engineering insight/decision history as append-only Markdown."""

    DOCUMENTS = {
        "architecture": "architecture-insights.md",
        "decisions": "engineering-decisions.md",
        "risk": "risk-history.md",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.memory_root / "project" / "intelligence"

    def _path(self, project: str, category: str, *, create_dir: bool = False) -> Path:
        validate_project_name(project)
        try:
            filename = self.DOCUMENTS[category]
        except KeyError as exc:
            raise ValidationFailed("Unknown intelligence memory category") from exc
        directory = self.root / project
        if create_dir:
            directory.mkdir(parents=True, exist_ok=True)
        return directory / filename

    def preview(self, project: str, category: str, content: str) -> str:
        cleaned = sanitize_content(content, self.settings)
        path = self._path(project, category)
        return f"[intelligence memory proposal/{category}] {path.name}\n\n{cleaned[:1200]}"

    def append_after_approval(self, project: str, category: str, content: str) -> dict[str, Any]:
        cleaned = sanitize_content(content, self.settings)
        path = self._path(project, category, create_dir=True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = f"\n---\n\n_Entry: {now}_\n\n{cleaned}\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return {
            "project": project,
            "category": category,
            "document": path.name,
            "path": str(path),
            "createdAt": now,
            "size": path.stat().st_size,
            "appendedBytes": len(entry.encode("utf-8")),
        }

    def history(self, project: str, limit: int = 100) -> list[dict[str, Any]]:
        validate_project_name(project)
        directory = self.root / project
        if not directory.exists():
            return []
        records: list[dict[str, Any]] = []
        for category, filename in self.DOCUMENTS.items():
            path = directory / filename
            if path.is_file():
                records.append({
                    "project": project,
                    "category": category,
                    "document": filename,
                    "path": str(path.relative_to(self.root)),
                    "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
                    "size": path.stat().st_size,
                })
        return sorted(records, key=lambda item: item["updatedAt"], reverse=True)[:limit]
