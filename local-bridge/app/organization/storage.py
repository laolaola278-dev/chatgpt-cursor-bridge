"""SQLite persistence for organization intelligence.

Stores the org entity graph, org architecture decisions, incidents, the
engineering pattern library and derived organization health snapshots. All
records are metadata/derived analysis; nothing here can modify project
source code or memory.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import IncidentStatus, OrgDecision, OrgEntity, OrgFailurePattern, OrgIncident, OrgPattern, PatternCategory


class OrganizationStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS org_entities (
                id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
                parent_id TEXT, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_decisions (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, title TEXT NOT NULL,
                context TEXT NOT NULL, decision TEXT NOT NULL, consequence TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_incidents (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, service TEXT NOT NULL,
                title TEXT NOT NULL, summary TEXT NOT NULL, severity TEXT NOT NULL,
                signature TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_patterns (
                id TEXT PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL,
                summary TEXT NOT NULL, project TEXT NOT NULL, tags_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_health_snapshots (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, health_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_failure_patterns (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, category TEXT NOT NULL,
                signature TEXT NOT NULL, occurrences INTEGER NOT NULL, severity TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS org_entities_type ON org_entities(type);
            CREATE INDEX IF NOT EXISTS org_entities_parent ON org_entities(parent_id);
            CREATE INDEX IF NOT EXISTS org_incidents_project ON org_incidents(project);
            CREATE INDEX IF NOT EXISTS org_patterns_category ON org_patterns(category);
            CREATE INDEX IF NOT EXISTS org_health_project ON org_health_snapshots(project);
            CREATE INDEX IF NOT EXISTS org_failure_project ON org_failure_patterns(project);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    # -- org graph ---------------------------------------------------------

    def save_entity(self, entity: OrgEntity) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_entities(id,type,name,parent_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
            (entity.id, entity.entity_type.value, entity.name, entity.parent_id,
             json.dumps(entity.metadata, ensure_ascii=False), entity.created_at),
        )
        self.connection.commit()

    def get_entity(self, entity_id: str) -> OrgEntity | None:
        row = self.connection.execute("SELECT * FROM org_entities WHERE id=?", (entity_id,)).fetchone()
        return self._entity(row) if row else None

    def list_entities(self, entity_type: str | None = None) -> list[OrgEntity]:
        if entity_type:
            rows = self.connection.execute("SELECT * FROM org_entities WHERE type=? ORDER BY created_at", (entity_type,)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM org_entities ORDER BY created_at").fetchall()
        return [self._entity(row) for row in rows]

    def children(self, parent_id: str) -> list[OrgEntity]:
        rows = self.connection.execute("SELECT * FROM org_entities WHERE parent_id=? ORDER BY created_at", (parent_id,)).fetchall()
        return [self._entity(row) for row in rows]

    @staticmethod
    def _entity(row: sqlite3.Row) -> OrgEntity:
        from .models import OrgEntityType

        return OrgEntity(
            entity_type=OrgEntityType(row["type"]),
            name=row["name"],
            parent_id=row["parent_id"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            id=row["id"],
            created_at=row["created_at"],
        )

    # -- org decisions ------------------------------------------------------

    def save_decision(self, decision: OrgDecision) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_decisions(id,project,title,context,decision,consequence,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (decision.id, decision.project, decision.title, decision.context,
             decision.decision, decision.consequence, decision.status, decision.created_at),
        )
        self.connection.commit()

    def list_decisions(self, project: str | None = None, limit: int = 200) -> list[OrgDecision]:
        if project:
            rows = self.connection.execute("SELECT * FROM org_decisions WHERE project=? ORDER BY created_at DESC LIMIT ?", (project, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM org_decisions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            OrgDecision(r["project"], r["title"], r["context"], r["decision"], r["consequence"],
                        r["status"], r["id"], r["created_at"])
            for r in rows
        ]

    # -- incidents ----------------------------------------------------------

    def save_incident(self, incident: OrgIncident) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_incidents(id,project,service,title,summary,severity,signature,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (incident.id, incident.project, incident.service, incident.title, incident.summary,
             incident.severity, incident.signature, incident.status.value, incident.created_at),
        )
        self.connection.commit()

    def list_incidents(self, project: str | None = None, limit: int = 200) -> list[OrgIncident]:
        if project:
            rows = self.connection.execute("SELECT * FROM org_incidents WHERE project=? ORDER BY created_at DESC LIMIT ?", (project, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM org_incidents ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            OrgIncident(r["project"], r["title"], r["summary"], r["severity"], r["service"],
                        r["signature"], IncidentStatus(r["status"]), r["id"], r["created_at"])
            for r in rows
        ]

    # -- pattern library ----------------------------------------------------

    def save_pattern(self, pattern: OrgPattern) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_patterns(id,category,name,summary,project,tags_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (pattern.id, pattern.category.value, pattern.name, pattern.summary,
             pattern.project, json.dumps(pattern.tags, ensure_ascii=False), pattern.created_at),
        )
        self.connection.commit()

    def list_patterns(self, category: str | None = None, limit: int = 200) -> list[OrgPattern]:
        if category:
            rows = self.connection.execute("SELECT * FROM org_patterns WHERE category=? ORDER BY created_at DESC LIMIT ?", (category, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM org_patterns ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            OrgPattern(PatternCategory(r["category"]), r["name"], r["summary"], r["project"],
                       json.loads(r["tags_json"] or "[]"), r["id"], r["created_at"])
            for r in rows
        ]

    # -- failure pattern library (cross-project learning) ----------------------

    def save_failure_pattern(self, pattern: OrgFailurePattern) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_failure_patterns(id,project,category,signature,occurrences,severity,created_at) VALUES(?,?,?,?,?,?,?)",
            (pattern.id, pattern.project, pattern.category, pattern.signature,
             pattern.occurrences, pattern.severity, pattern.created_at),
        )
        self.connection.commit()

    def replace_failure_patterns(self, project: str, patterns: list[OrgFailurePattern]) -> None:
        self.connection.execute("DELETE FROM org_failure_patterns WHERE project=?", (project,))
        for pattern in patterns:
            self.save_failure_pattern(pattern)

    def list_failure_patterns(self, project: str | None = None, limit: int = 500) -> list[OrgFailurePattern]:
        if project:
            rows = self.connection.execute("SELECT * FROM org_failure_patterns WHERE project=? ORDER BY occurrences DESC LIMIT ?", (project, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM org_failure_patterns ORDER BY occurrences DESC LIMIT ?", (limit,)).fetchall()
        return [
            OrgFailurePattern(r["project"], r["category"], r["signature"], int(r["occurrences"]), r["severity"], r["id"], r["created_at"])
            for r in rows
        ]

    # -- org health snapshots ------------------------------------------------

    def record_health(self, project: str, report: dict[str, Any]) -> str:
        snapshot_id = f"orghealth_{project}_{report.get('createdAt', '')[:19].replace(':', '')}"
        self.connection.execute(
            "INSERT OR REPLACE INTO org_health_snapshots(id,project,health_json,created_at) VALUES(?,?,?,?)",
            (snapshot_id, project, json.dumps(report, ensure_ascii=False), report.get("createdAt", "")),
        )
        self.connection.commit()
        return snapshot_id

    def list_health(self, project: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT health_json FROM org_health_snapshots WHERE project=? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [json.loads(row["health_json"]) for row in rows]
