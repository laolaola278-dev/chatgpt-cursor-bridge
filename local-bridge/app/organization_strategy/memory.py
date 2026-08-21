"""Organization Memory (Phase 24).

Append-only markdown memory under memory/organization/. Writing is strictly
approval-gated: append_after_approval() is only ever called from the approved
execution path (after a human approves an organization_memory_append request
through the ApprovalStore). Nothing here can write directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.memory.markdown_store import sanitize_content
from app.security.validator import ValidationFailed


class OrganizationMemory:
    DOCUMENTS = {
        "strategies": "organization-strategies.md",
        "decisions": "organization-decisions.md",
        "lessons": "cross-project-lessons.md",
        "risk_history": "organization-risk-history.md",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.memory_root / "organization"

    def preview(self, org: str, category: str, content: str) -> str:
        cleaned = sanitize_content(content, self.settings)
        return f"[organization memory proposal/{category}] {self._path(org, category).name}\n\n{cleaned[:1200]}"

    def _path(self, org: str, category: str, create_dir: bool = False) -> Path:
        org = (org or "").strip().replace("/", "_").replace("\\", "_")
        if not org:
            raise ValidationFailed("Organization name must not be empty")
        if category not in self.DOCUMENTS:
            raise ValidationFailed("Unknown organization memory category")
        directory = self.root / org
        if create_dir:
            directory.mkdir(parents=True, exist_ok=True)
        return directory / self.DOCUMENTS[category]

    def append_after_approval(self, org: str, category: str, content: str) -> dict[str, Any]:
        cleaned = sanitize_content(content, self.settings)
        path = self._path(org, category, True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = f"\n---\n\n_Entry: {now}_\n\n{cleaned}\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return {
            "organization": org,
            "category": category,
            "document": path.name,
            "path": str(path),
            "createdAt": now,
            "size": path.stat().st_size,
        }

    def history(self, org: str, limit: int = 100) -> list[dict[str, Any]]:
        org = (org or "").strip().replace("/", "_").replace("\\", "_")
        directory = self.root / org
        if not directory.exists():
            return []
        output: list[dict[str, Any]] = []
        for category, filename in self.DOCUMENTS.items():
            path = directory / filename
            if path.is_file():
                output.append(
                    {
                        "organization": org,
                        "category": category,
                        "document": filename,
                        "path": str(path.relative_to(self.root)),
                        "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(
                            timespec="seconds"
                        ),
                        "size": path.stat().st_size,
                    }
                )
        return sorted(output, key=lambda item: item["updatedAt"], reverse=True)[:limit]
