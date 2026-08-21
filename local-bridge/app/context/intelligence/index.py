"""Durable, read-only searchable index for project context snapshots."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Iterable


@dataclass(frozen=True)
class ContextSearchResult:
    project: str
    kind: str
    identifier: str
    title: str
    content: str
    updated_at: str
    score: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "kind": self.kind,
            "id": self.identifier,
            "title": self.title,
            "content": self.content,
            "updatedAt": self.updated_at,
            "score": self.score,
        }


class ContextIndex:
    """SQLite index used only for context discovery, never for mutations."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS context_documents (
                    id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS context_documents_project_idx
                    ON context_documents(project);
                CREATE INDEX IF NOT EXISTS context_documents_updated_idx
                    ON context_documents(updated_at);
                """
            )
            self._connection.commit()

    def replace_project(self, project: str, records: Iterable[dict[str, Any]]) -> None:
        """Replace one project's derived records atomically."""
        rows = list(records)
        with self._lock:
            self._connection.execute("DELETE FROM context_documents WHERE project=?", (project,))
            self._connection.executemany(
                """
                INSERT INTO context_documents (id, project, kind, title, content, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(row["id"]),
                        project,
                        str(row["kind"]),
                        str(row.get("title", "")),
                        str(row.get("content", "")),
                        str(row.get("updatedAt", "")),
                    )
                    for row in rows
                ],
            )
            self._connection.commit()

    def index_context(self, project: str, context: dict[str, Any]) -> None:
        """Index decisions, tasks, workflow history and current documents."""
        updated = str(context.get("updatedAt") or context.get("snapshot", {}).get("updatedAt") or "")
        records: list[dict[str, Any]] = []
        workflow = context.get("currentWorkflow")
        if workflow:
            records.append({
                "id": f"workflow:{workflow.get('id')}",
                "kind": "workflow",
                "title": str(workflow.get("name", "Workflow")),
                "content": json.dumps(workflow, ensure_ascii=False),
                "updatedAt": str(workflow.get("updatedAt") or updated),
            })
            for stage in workflow.get("stages", []):
                records.append({
                    "id": f"stage:{stage.get('id')}",
                    "kind": "workflow_history",
                    "title": str(stage.get("reportTitle") or stage.get("stageType") or "Stage"),
                    "content": json.dumps(stage, ensure_ascii=False),
                    "updatedAt": str(stage.get("updatedAt") or updated),
                })
        for document in context.get("documents") or []:
            records.append({
                "id": f"document:{document.get('id', document.get('type', 'document'))}",
                "kind": "document",
                "title": str(document.get("type", "Document")),
                "content": json.dumps(document, ensure_ascii=False),
                "updatedAt": str(document.get("updatedAt") or updated),
            })
        for index, decision in enumerate(context.get("recentDecisions") or []):
            records.append({
                "id": f"decision:{decision.get('id', index)}",
                "kind": "decision",
                "title": str(decision.get("title", "Decision")),
                "content": json.dumps(decision, ensure_ascii=False),
                "updatedAt": str(decision.get("createdAt") or updated),
            })
        for index, task in enumerate(context.get("openTasks") or []):
            records.append({
                "id": f"task:{index}:{task}",
                "kind": "task",
                "title": str(task),
                "content": str(task),
                "updatedAt": updated,
            })
        for index, change in enumerate(context.get("recentChanges") or []):
            records.append({
                "id": f"change:{index}:{change.get('timestamp', '')}",
                "kind": "document",
                "title": str(change.get("action", "Change")),
                "content": json.dumps(change, ensure_ascii=False),
                "updatedAt": str(change.get("timestamp") or updated),
            })
        self.replace_project(project, records)

    def search(
        self,
        query: str = "",
        *,
        project: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
    ) -> list[ContextSearchResult]:
        """Search indexed context with parameterized filters only."""
        clauses: list[str] = []
        params: list[Any] = []
        terms = [term.strip().lower() for term in query.split() if term.strip()]
        if terms:
            for term in terms:
                clauses.append("lower(title || ' ' || content) LIKE ?")
                params.append(f"%{term}%")
        if project:
            clauses.append("project=?")
            params.append(project)
        if date_from:
            clauses.append("updated_at >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("updated_at <= ?")
            params.append(date_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT project, kind, id, title, content, updated_at "
            f"FROM context_documents {where} ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(max(1, min(limit, 200)))
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        return [
            ContextSearchResult(
                project=row["project"],
                kind=row["kind"],
                identifier=row["id"],
                title=row["title"],
                content=row["content"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
