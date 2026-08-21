from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from secrets import token_hex
from threading import Lock
from typing import Any, Iterable

from app.audit.logger import AuditLogger
from app.intelligence.common import ensure_project, sanitize_metadata, sanitize_text, utc_now
from app.security.validator import ResourceNotFound, ValidationFailed

from .models import Observation, ObservationType


class ObservationStore:
    """Append-friendly observation store; it never reads or writes project source."""

    def __init__(self, db_path: str | Path, audit: AuditLogger | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = audit
        self._lock = Lock()
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS observations_project_time
              ON observations(project_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS observations_project_type
              ON observations(project_id, type, timestamp DESC);
            CREATE TABLE IF NOT EXISTS observation_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def _audit(self, observation: Observation, action: str = "observation_record") -> None:
        self.connection.execute(
            "INSERT INTO observation_audit(observation_id, project_id, action, timestamp) VALUES(?,?,?,?)",
            (observation.id, observation.project_id, action, utc_now()),
        )
        if self.audit is not None:
            self.audit.record(
                action=action,
                path=f"{observation.project_id}:observation/{observation.id}",
                permission="LEVEL_0",
                approved=True,
                result="success",
                detail=f"{observation.type.value}: {sanitize_text(observation.summary, limit=240)}",
            )

    def save(self, observation: Observation, *, audit: bool = True) -> Observation:
        # Reconstructing here ensures callers cannot bypass the model's scrubber
        # by passing a mutable metadata dictionary after validation.
        clean = Observation(
            id=observation.id,
            project_id=observation.project_id,
            timestamp=observation.timestamp,
            type=observation.type,
            source=observation.source,
            summary=observation.summary,
            metadata=sanitize_metadata(observation.metadata),
            risk_level=observation.risk_level,
        )
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO observations
                (id, project_id, timestamp, type, source, summary, metadata_json, risk_level, created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    clean.id,
                    clean.project_id,
                    clean.timestamp,
                    clean.type.value,
                    clean.source,
                    clean.summary,
                    json.dumps(clean.metadata, ensure_ascii=False, sort_keys=True),
                    clean.risk_level,
                    utc_now(),
                ),
            )
            if audit:
                self._audit(clean)
            self.connection.commit()
        return clean

    def add(self, observation: Observation) -> Observation:
        return self.save(observation)

    def record(
        self,
        *,
        project_id: str,
        type: ObservationType | str,
        source: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
        risk_level: str = "low",
        observation_id: str | None = None,
        timestamp: str | None = None,
    ) -> Observation:
        return self.save(
            Observation.build(
                project_id=project_id,
                type=type,
                source=source,
                summary=summary,
                metadata=metadata,
                risk_level=risk_level,
                observation_id=observation_id or f"obs_{token_hex(8)}",
                timestamp=timestamp,
            )
        )

    def get(self, observation_id: str, project_id: str | None = None) -> Observation:
        query = "SELECT * FROM observations WHERE id=?"
        values: list[Any] = [observation_id]
        if project_id is not None:
            query += " AND project_id=?"
            values.append(ensure_project(project_id))
        row = self.connection.execute(query, values).fetchone()
        if row is None:
            raise ResourceNotFound(f"Observation '{observation_id}' was not found")
        return Observation.from_row(row)

    def list(
        self,
        project_id: str,
        *,
        type: ObservationType | str | None = None,
        limit: int = 100,
    ) -> list[Observation]:
        project = ensure_project(project_id)
        limit = max(1, min(int(limit), 1000))
        query = "SELECT * FROM observations WHERE project_id=?"
        values: list[Any] = [project]
        if type is not None:
            kind = type.value if isinstance(type, ObservationType) else str(type).lower()
            try:
                ObservationType(kind)
            except ValueError as exc:
                raise ValidationFailed(f"Unsupported observation type: {type}") from exc
            query += " AND type=?"
            values.append(kind)
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        values.append(limit)
        rows = self.connection.execute(query, values).fetchall()
        return [Observation.from_row(row) for row in rows]

    def list_all(self, project_id: str, limit: int = 100) -> list[Observation]:
        return self.list(project_id, limit=limit)

    def count(self, project_id: str, type: ObservationType | str | None = None) -> int:
        project = ensure_project(project_id)
        query = "SELECT COUNT(*) FROM observations WHERE project_id=?"
        values: list[Any] = [project]
        if type is not None:
            values.append(type.value if isinstance(type, ObservationType) else str(type).lower())
            query += " AND type=?"
        return int(self.connection.execute(query, values).fetchone()[0])

    def audit_entries(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        project = ensure_project(project_id)
        rows = self.connection.execute(
            "SELECT observation_id, project_id, action, timestamp FROM observation_audit WHERE project_id=? ORDER BY audit_id DESC LIMIT ?",
            (project, max(1, min(int(limit), 1000))),
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_for_tests_only(self, project_id: str) -> None:
        """Explicit maintenance helper; production API does not expose it."""
        project = ensure_project(project_id)
        with self._lock:
            self.connection.execute("DELETE FROM observations WHERE project_id=?", (project,))
            self.connection.execute("DELETE FROM observation_audit WHERE project_id=?", (project,))
            self.connection.commit()
