from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_metadata, sanitize_text, utc_now
from app.security.sandbox import validate_project_name
from app.security.validator import ValidationFailed


# Phase 25 categories remain compatible; Phase 26 adds evidence-backed trend,
# correlation, recommendation, and evaluation knowledge. Every append still
# occurs only through the approval-bound action in app.main.
KNOWLEDGE_TYPES = (
    "patterns",
    "predictions",
    "strategies",
    "outcomes",
    "trends",
    "correlations",
    "recommendations",
    "evaluations",
)


@dataclass(frozen=True)
class KnowledgeRecord:
    id: str
    project_id: str
    category: str
    content: str
    source: str
    evidence: list[str]
    confidence: float
    created_at: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "project_id": self.project_id, "projectId": self.project_id, "category": self.category, "content": self.content, "source": self.source, "evidence": self.evidence, "confidence": self.confidence, "created_at": self.created_at, "createdAt": self.created_at, "metadata": self.metadata, "readOnly": True}


class IntelligenceMemory:
    """Append-only JSONL memory. There is intentionally no automatic writer."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.memory_root / "intelligence"

    def _path(self, project: str, category: str, create_dir: bool = False) -> Path:
        project = ensure_project(project)
        category = str(category).lower().strip()
        if category not in KNOWLEDGE_TYPES:
            raise ValidationFailed(f"Unknown intelligence knowledge category: {category}")
        directory = self.root / project
        if create_dir: directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{category}.jsonl"

    def preview(self, project: str, category: str, content: str, *, source: str = "", evidence: list[str] | None = None, confidence: float = 0.0) -> str:
        path = self._path(project, category)
        return f"[knowledge proposal/{category}] {path.name}\n\nsource={sanitize_text(source, limit=200)} confidence={bounded_confidence(confidence)}\nevidence={', '.join(ids(evidence))}\n\n{sanitize_text(content, limit=1200)}"

    def append_after_approval(self, project: str, category: str, content: str, *, source: str = "", evidence: list[str] | None = None, confidence: float = 0.0, metadata: dict[str, Any] | None = None, record_id: str | None = None) -> dict[str, Any]:
        path = self._path(project, category, True)
        record = KnowledgeRecord(record_id or f"knowledge_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}", ensure_project(project), category, sanitize_text(content, limit=12000), sanitize_text(source, limit=500), ids(evidence), bounded_confidence(confidence), utc_now(), sanitize_metadata(metadata or {}))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.as_dict(), ensure_ascii=False) + "\n")
        return {**record.as_dict(), "document": path.name, "path": str(path.relative_to(self.root)), "size": path.stat().st_size}

    append_knowledge_after_approval = append_after_approval

    def list(self, project: str, category: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        project = ensure_project(project)
        categories = [category] if category else list(KNOWLEDGE_TYPES)
        rows: list[dict[str, Any]] = []
        for current in categories:
            path = self._path(project, current)
            if not path.is_file(): continue
            for raw in path.read_text(encoding="utf-8").splitlines()[-max(1, min(int(limit), 1000)):]:
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                item.pop("path", None)
                rows.append(item)
        rows.sort(key=lambda item: str(item.get("created_at", item.get("createdAt", ""))), reverse=True)
        return rows[:max(1, min(int(limit), 1000))]

    def history(self, project: str, limit: int = 100) -> list[dict[str, Any]]:
        return self.list(project, limit=limit)
