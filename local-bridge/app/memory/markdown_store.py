"""Human-readable markdown storage for project memory.

Every memory document is plain markdown so it stays reviewable and
version-controllable. Writes are append-only: existing content is never
overwritten or truncated.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings
from app.memory.models import (
    DOCUMENT_INTROS,
    DOCUMENT_TITLES,
    DecisionInput,
    MemoryDocument,
    utc_now,
)
from app.security.sandbox import validate_memory_path
from app.security.validator import PayloadTooLarge, ResourceNotFound, ValidationFailed

ADR_HEADING = re.compile(r"^##\s+ADR-(\d{3,})\b", re.MULTILINE)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def document_header(document: MemoryDocument) -> str:
    title = DOCUMENT_TITLES[document]
    intro = DOCUMENT_INTROS[document]
    return f"# {title}\n\n_{intro}_\n\n_Created: {utc_now()}_\n"


def sanitize_content(content: str, settings: Settings) -> str:
    """Reject control characters and oversized payloads."""
    if content is None:
        raise ValidationFailed("Field 'content' must not be empty")
    cleaned = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        raise ValidationFailed("Field 'content' must not be empty")
    if CONTROL_CHARS.search(cleaned):
        raise ValidationFailed("Content contains control characters")

    encoded = cleaned.encode("utf-8")
    if len(encoded) > settings.max_memory_append_bytes:
        limit_kb = settings.max_memory_append_bytes // 1024
        raise PayloadTooLarge(f"Memory append exceeds the {limit_kb}KB limit")
    return cleaned


class MarkdownStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def path_for(self, project: str, document: MemoryDocument, *, create_dir: bool = False) -> Path:
        return validate_memory_path(
            project, document.value, self._settings, create_dir=create_dir
        )

    def initialise(self, project: str) -> list[str]:
        """Create any missing memory documents. Existing files are untouched."""
        created: list[str] = []
        for document in MemoryDocument:
            target = self.path_for(project, document, create_dir=True)
            if target.exists():
                continue
            target.write_text(document_header(document), encoding="utf-8")
            created.append(document.value)
        return created

    def exists(self, project: str, document: MemoryDocument) -> bool:
        try:
            return self.path_for(project, document).exists()
        except ResourceNotFound:
            return False

    def read(self, project: str, document: MemoryDocument) -> tuple[str, int]:
        target = self.path_for(project, document)
        if not target.exists():
            raise ResourceNotFound(
                f"Memory document '{document.value}' does not exist for project '{project}'"
            )
        content = target.read_text(encoding="utf-8")
        return content, target.stat().st_size

    def append(self, project: str, document: MemoryDocument, content: str) -> dict[str, object]:
        """Append a timestamped section. Never overwrites existing content."""
        cleaned = sanitize_content(content, self._settings)
        target = self.path_for(project, document, create_dir=True)

        if not target.exists():
            target.write_text(document_header(document), encoding="utf-8")

        before = target.read_text(encoding="utf-8")
        timestamp = utc_now()
        entry = f"\n---\n\n_Entry: {timestamp}_\n\n{cleaned}\n"

        with target.open("a", encoding="utf-8") as handle:
            handle.write(entry)

        after_size = target.stat().st_size
        return {
            "document": document.value,
            "appendedBytes": len(entry.encode("utf-8")),
            "size": after_size,
            "timestamp": timestamp,
            "preview": entry.strip()[:600],
            "previousSize": len(before.encode("utf-8")),
        }

    def next_adr_id(self, project: str) -> str:
        """Compute the next ADR identifier from decisions.md."""
        target = self.path_for(project, MemoryDocument.DECISIONS, create_dir=True)
        if not target.exists():
            return "ADR-001"
        existing = ADR_HEADING.findall(target.read_text(encoding="utf-8"))
        highest = max((int(item) for item in existing), default=0)
        return f"ADR-{highest + 1:03d}"

    def render_decision(self, adr_id: str, payload: DecisionInput, created: str) -> str:
        return (
            f"\n## {adr_id}\n\n"
            f"Title: {payload.title}\n\n"
            f"Context: {payload.context}\n\n"
            f"Decision: {payload.decision}\n\n"
            f"Consequence: {payload.consequence}\n\n"
            f"Created: {created}\n"
        )

    def append_decision(self, project: str, payload: DecisionInput) -> dict[str, object]:
        """Append an ADR block to decisions.md."""
        for field_name, value in (
            ("title", payload.title),
            ("context", payload.context),
            ("decision", payload.decision),
            ("consequence", payload.consequence),
        ):
            if CONTROL_CHARS.search(value):
                raise ValidationFailed(f"ADR field '{field_name}' contains control characters")

        adr_id = self.next_adr_id(project)
        created = utc_now()
        block = self.render_decision(adr_id, payload, created)

        if len(block.encode("utf-8")) > self._settings.max_memory_append_bytes:
            limit_kb = self._settings.max_memory_append_bytes // 1024
            raise PayloadTooLarge(f"ADR exceeds the {limit_kb}KB limit")

        target = self.path_for(project, MemoryDocument.DECISIONS, create_dir=True)
        if not target.exists():
            target.write_text(document_header(MemoryDocument.DECISIONS), encoding="utf-8")

        with target.open("a", encoding="utf-8") as handle:
            handle.write(block)

        return {
            "id": adr_id,
            "title": payload.title,
            "document": MemoryDocument.DECISIONS.value,
            "createdAt": created,
            "size": target.stat().st_size,
            "preview": block.strip()[:600],
        }
