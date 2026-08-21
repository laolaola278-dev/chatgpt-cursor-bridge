"""Memory manager: coordinates markdown storage and the SQLite index.

All public methods go through the sandbox (`validate_memory_path`) and are
per-project isolated. Nothing here writes without an explicit caller decision;
approval gating lives in the API layer.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.memory.markdown_store import MarkdownStore, sanitize_content
from app.memory.models import (
    MEMORY_DOCUMENTS,
    DecisionInput,
    MemoryDocument,
    parse_document,
)
from app.memory.sqlite_index import MemoryIndex
from app.security.sandbox import get_memory_dir, memory_root, validate_project_name


class MemoryManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._store = MarkdownStore(settings)

    # -- helpers ---------------------------------------------------------

    def _index(self, project: str, *, create: bool = False) -> MemoryIndex:
        memory_dir = get_memory_dir(project, self._settings, create=create)
        return MemoryIndex(memory_dir)

    def resolve_document(self, document: str) -> MemoryDocument:
        return parse_document(document)

    def preview_append(self, project: str, document: str, content: str) -> str:
        """Validate an append request and return a preview (no write)."""
        validate_project_name(project)
        doc = self.resolve_document(document)
        cleaned = sanitize_content(content, self._settings)
        return f"[append -> {doc.value}]\n\n{cleaned[:600]}"

    def preview_decision(self, project: str, payload: DecisionInput) -> str:
        validate_project_name(project)
        get_memory_dir(project, self._settings, create=True)
        adr_id = self._store.next_adr_id(project)
        return (
            f"[append -> {MemoryDocument.DECISIONS.value}]\n\n"
            f"## {adr_id}\n\nTitle: {payload.title}\n\n"
            f"Context: {payload.context[:200]}\n\n"
            f"Decision: {payload.decision[:200]}\n\n"
            f"Consequence: {payload.consequence[:200]}"
        )

    # -- read side (LEVEL_0) --------------------------------------------

    def list_projects(self) -> list[dict[str, Any]]:
        root = memory_root(self._settings)
        projects: list[dict[str, Any]] = []
        for entry in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            documents = sorted(
                doc.value for doc in MEMORY_DOCUMENTS if (entry / doc.value).exists()
            )
            projects.append({"project": entry.name, "documents": documents})
        return projects

    def status(self, project: str) -> dict[str, Any]:
        memory_dir = get_memory_dir(project, self._settings)
        index = MemoryIndex(memory_dir)
        return {
            "project": project,
            "memoryDir": str(memory_dir),
            "documents": [record.as_dict() for record in index.list_documents(project)],
            "decisions": [record.as_dict() for record in index.list_decisions()],
        }

    def read(self, project: str, document: str) -> dict[str, Any]:
        doc = self.resolve_document(document)
        content, size = self._store.read(project, doc)
        return {
            "project": project,
            "document": doc.value,
            "size": size,
            "content": content,
        }

    # -- write side (LEVEL_1, called only after approval) ----------------

    def initialise(self, project: str) -> dict[str, Any]:
        validate_project_name(project)
        created = self._store.initialise(project)
        index = self._index(project, create=True)

        for document in MEMORY_DOCUMENTS:
            path = self._store.path_for(project, document, create_dir=True)
            if path.exists():
                index.upsert_document(project=project, document=document, path=str(path))

        return {
            "project": project,
            "created": created,
            "documents": [record.as_dict() for record in index.list_documents(project)],
            "indexPath": str(index.db_path),
        }

    def append(self, project: str, document: str, content: str) -> dict[str, Any]:
        doc = self.resolve_document(document)
        # Ensure the document set and index exist before appending.
        self.initialise(project)

        result = self._store.append(project, doc, content)
        path = self._store.path_for(project, doc)
        index = self._index(project, create=True)
        record = index.upsert_document(
            project=project,
            document=doc,
            path=str(path),
            timestamp=str(result["timestamp"]),
        )
        return {**result, "project": project, "index": record.as_dict()}

    def append_decision(self, project: str, payload: DecisionInput) -> dict[str, Any]:
        self.initialise(project)

        result = self._store.append_decision(project, payload)
        path = self._store.path_for(project, MemoryDocument.DECISIONS)
        index = self._index(project, create=True)

        index.upsert_document(
            project=project,
            document=MemoryDocument.DECISIONS,
            path=str(path),
            timestamp=str(result["createdAt"]),
        )
        record = index.insert_decision(
            adr_id=str(result["id"]),
            title=str(result["title"]),
            created_at=str(result["createdAt"]),
        )
        return {**result, "project": project, "index": record.as_dict()}
