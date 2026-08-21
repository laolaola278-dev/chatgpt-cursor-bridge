"""SQLite index for project memory.

The database stores *index metadata only*. Document bodies and ADR text stay in
the markdown files so memory remains human readable and reviewable.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.memory.models import (
    MEMORY_DB_FILENAME,
    DecisionRecord,
    DocumentRecord,
    MemoryDocument,
    utc_now,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    type        TEXT NOT NULL,
    path        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project);
"""

#: Columns that must never appear: full text is not stored in the index.
FORBIDDEN_COLUMNS = {"content", "body", "text", "full_text"}


class MemoryIndex:
    """Thin SQLite wrapper scoped to a single project's memory directory."""

    def __init__(self, memory_dir: Path) -> None:
        self._db_path = memory_dir / MEMORY_DB_FILENAME
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    @staticmethod
    def document_id(project: str, document: MemoryDocument) -> str:
        return f"{project}:{document.value}"

    def upsert_document(
        self,
        *,
        project: str,
        document: MemoryDocument,
        path: str,
        timestamp: str | None = None,
    ) -> DocumentRecord:
        now = timestamp or utc_now()
        doc_id = self.document_id(project, document)

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT INTO documents (id, project, type, path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    path = excluded.path,
                    updated_at = excluded.updated_at
                """,
                (doc_id, project, document.value, path, created_at, now),
            )

        return DocumentRecord(
            id=doc_id,
            project=project,
            type=document.value,
            path=path,
            created_at=created_at,
            updated_at=now,
        )

    def list_documents(self, project: str) -> list[DocumentRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM documents WHERE project = ? ORDER BY type", (project,)
            ).fetchall()
        return [
            DocumentRecord(
                id=row["id"],
                project=row["project"],
                type=row["type"],
                path=row["path"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def insert_decision(self, *, adr_id: str, title: str, created_at: str) -> DecisionRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO decisions (id, title, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET title = excluded.title
                """,
                (adr_id, title, created_at),
            )
        return DecisionRecord(id=adr_id, title=title, created_at=created_at)

    def list_decisions(self) -> list[DecisionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM decisions ORDER BY id"
            ).fetchall()
        return [
            DecisionRecord(id=row["id"], title=row["title"], created_at=row["created_at"])
            for row in rows
        ]

    def table_columns(self, table: str) -> list[str]:
        """Introspection helper used by tests to assert no full text is stored."""
        if table not in {"documents", "decisions"}:
            return []
        with self._connect() as connection:
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        return [row["name"] for row in rows]
