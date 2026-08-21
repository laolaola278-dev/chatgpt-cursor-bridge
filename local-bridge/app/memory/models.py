"""Memory domain models and document registry.

Memory stores *project facts*, not chat transcripts. The document set is a
fixed, human-readable whitelist so arbitrary files can never be created inside
the memory sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.security.validator import ValidationFailed


class MemoryDocument(str, Enum):
    PROJECT = "project.md"
    ARCHITECTURE = "architecture.md"
    DECISIONS = "decisions.md"
    TASKS = "tasks.md"
    CHANGELOG = "changelog.md"


#: Order matters: this is the creation order used when initialising memory.
MEMORY_DOCUMENTS: tuple[MemoryDocument, ...] = (
    MemoryDocument.PROJECT,
    MemoryDocument.ARCHITECTURE,
    MemoryDocument.DECISIONS,
    MemoryDocument.TASKS,
    MemoryDocument.CHANGELOG,
)

DOCUMENT_TITLES: dict[MemoryDocument, str] = {
    MemoryDocument.PROJECT: "Project",
    MemoryDocument.ARCHITECTURE: "Architecture",
    MemoryDocument.DECISIONS: "Decisions (ADR)",
    MemoryDocument.TASKS: "Tasks",
    MemoryDocument.CHANGELOG: "Changelog",
}

DOCUMENT_INTROS: dict[MemoryDocument, str] = {
    MemoryDocument.PROJECT: "Project goal, tech stack and constraints.",
    MemoryDocument.ARCHITECTURE: "Architecture design, modules and their relationships.",
    MemoryDocument.DECISIONS: "Architecture Decision Records. Append-only.",
    MemoryDocument.TASKS: "Current and planned tasks.",
    MemoryDocument.CHANGELOG: "History of applied changes.",
}

#: The database file lives next to the markdown documents.
MEMORY_DB_FILENAME = "memory.db"


def parse_document(value: str) -> MemoryDocument:
    """Resolve a document name against the whitelist."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        raise ValidationFailed("Field 'document' must not be empty")
    if not cleaned.endswith(".md"):
        cleaned = f"{cleaned}.md"
    try:
        return MemoryDocument(cleaned)
    except ValueError as exc:
        allowed = ", ".join(doc.value for doc in MEMORY_DOCUMENTS)
        raise ValidationFailed(
            f"Unknown memory document '{value}'. Allowed documents: {allowed}"
        ) from exc


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class DocumentRecord:
    """Index row describing one markdown memory document."""

    id: str
    project: str
    type: str
    path: str
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "type": self.type,
            "path": self.path,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class DecisionRecord:
    """Index row describing one ADR entry."""

    id: str
    title: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "createdAt": self.created_at}


@dataclass(frozen=True)
class DecisionInput:
    """Validated ADR payload."""

    title: str
    context: str
    decision: str
    consequence: str

    @staticmethod
    def build(
        *, title: str, context: str, decision: str, consequence: str
    ) -> "DecisionInput":
        fields = {
            "title": title,
            "context": context,
            "decision": decision,
            "consequence": consequence,
        }
        cleaned: dict[str, str] = {}
        for name, raw in fields.items():
            value = (raw or "").strip()
            if not value:
                raise ValidationFailed(f"ADR field '{name}' is required")
            cleaned[name] = value
        return DecisionInput(**cleaned)
