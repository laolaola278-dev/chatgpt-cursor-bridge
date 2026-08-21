"""SQLite storage for the Engineering Intelligence Governance Layer.

Every table is project-scoped; reads always filter by project so one project
can never observe another project's governance records.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from app.intelligence.governance.models import (
    GovernanceMemoryRecord,
    GovernanceRecord,
    PolicyViolation,
    ReviewProposal,
    RiskFinding,
)
from app.intelligence.common import ensure_project


def _conn(db_path: str | Path) -> sqlite3.Connection:
    path = str(db_path)
    if path != ":memory:":
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def _json(value: Any) -> str:
    return json.dumps(list(value or []), ensure_ascii=False)


class GovernanceStore:
    def __init__(self, db_path: str | Path) -> None:
        self._lock = Lock()
        self._connection = _conn(db_path)
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS governance_records (
                governance_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT '',
                model_id TEXT NOT NULL DEFAULT '',
                policy_ids_json TEXT NOT NULL DEFAULT '[]',
                risk_level TEXT NOT NULL,
                risk_score REAL NOT NULL,
                confidence REAL NOT NULL,
                evaluation_result TEXT NOT NULL DEFAULT '',
                governance_result TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                evidence_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                audit_request_id TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS risk_findings (
                risk_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT '',
                model_id TEXT NOT NULL DEFAULT '',
                risk_level TEXT NOT NULL,
                risk_score REAL NOT NULL,
                confidence REAL NOT NULL,
                risk_factors_json TEXT NOT NULL DEFAULT '[]',
                reason TEXT NOT NULL DEFAULT '',
                similar_cases_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policy_violations (
                violation_id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                severity TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_proposals (
                proposal_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                recommended_action TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT NOT NULL DEFAULT '',
                audit_request_id TEXT NOT NULL DEFAULT '',
                reviewer_note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS governance_memory (
                memory_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                approval_request_id TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_gov_records_project ON governance_records(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_gov_risks_project ON risk_findings(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_gov_violations_project ON policy_violations(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_gov_reviews_project ON review_proposals(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_gov_memory_project ON governance_memory(project_id, created_at);
            """
        )
        self._connection.commit()

    # -- governance records -------------------------------------------------

    def save_record(self, record: GovernanceRecord) -> GovernanceRecord:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO governance_records (
                    governance_id, project_id, source_kind, source_id, agent_id,
                    model_id, policy_ids_json, risk_level, risk_score, confidence,
                    evaluation_result, governance_result, reason, evidence_json,
                    created_at, audit_request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.governance_id, record.project_id, record.source_kind,
                    record.source_id, record.agent_id, record.model_id,
                    _json(record.policy_ids), record.risk_level, record.risk_score,
                    record.confidence, record.evaluation_result,
                    record.governance_result, record.reason, _json(record.evidence),
                    record.created_at, record.audit_request_id,
                ),
            )
            self._connection.commit()
        return record

    def get_record(self, governance_id: str, project: str) -> GovernanceRecord | None:
        project = ensure_project(project)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM governance_records WHERE governance_id=? AND project_id=?",
                (governance_id, project),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def records(
        self,
        project: str,
        *,
        source_kind: str | None = None,
        risk_level: str | None = None,
        governance_result: str | None = None,
        agent_id: str | None = None,
        model_id: str | None = None,
        limit: int = 500,
    ) -> list[GovernanceRecord]:
        project = ensure_project(project)
        where = ["project_id=?"]
        params: list[Any] = [project]
        for column, value in (
            ("source_kind", source_kind),
            ("risk_level", risk_level),
            ("governance_result", governance_result),
            ("agent_id", agent_id),
            ("model_id", model_id),
        ):
            if value:
                where.append(f"{column}=?")
                params.append(value)
        params.append(max(1, min(int(limit), 5000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM governance_records WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> GovernanceRecord:
        return GovernanceRecord(
            governance_id=row["governance_id"],
            project_id=row["project_id"],
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            agent_id=row["agent_id"],
            model_id=row["model_id"],
            policy_ids=json.loads(row["policy_ids_json"]),
            risk_level=row["risk_level"],
            risk_score=row["risk_score"],
            confidence=row["confidence"],
            evaluation_result=row["evaluation_result"],
            governance_result=row["governance_result"],
            reason=row["reason"],
            evidence=json.loads(row["evidence_json"]),
            created_at=row["created_at"],
            audit_request_id=row["audit_request_id"],
        )

    # -- risk findings ------------------------------------------------------

    def save_risk(self, finding: RiskFinding) -> RiskFinding:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO risk_findings (
                    risk_id, project_id, source_kind, source_id, agent_id, model_id,
                    risk_level, risk_score, confidence, risk_factors_json, reason,
                    similar_cases_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.risk_id, finding.project_id, finding.source_kind,
                    finding.source_id, finding.agent_id, finding.model_id,
                    finding.risk_level, finding.risk_score, finding.confidence,
                    _json(finding.risk_factors), finding.reason,
                    _json(finding.similar_cases), finding.created_at,
                ),
            )
            self._connection.commit()
        return finding

    def risks(
        self,
        project: str,
        *,
        risk_level: str | None = None,
        source_kind: str | None = None,
        agent_id: str | None = None,
        limit: int = 500,
    ) -> list[RiskFinding]:
        project = ensure_project(project)
        where = ["project_id=?"]
        params: list[Any] = [project]
        for column, value in (("risk_level", risk_level), ("source_kind", source_kind), ("agent_id", agent_id)):
            if value:
                where.append(f"{column}=?")
                params.append(value)
        params.append(max(1, min(int(limit), 5000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM risk_findings WHERE {' AND '.join(where)} ORDER BY risk_score DESC, created_at DESC LIMIT ?", params
            ).fetchall()
        return [self._risk_from_row(row) for row in rows]

    @staticmethod
    def _risk_from_row(row: sqlite3.Row) -> RiskFinding:
        return RiskFinding(
            risk_id=row["risk_id"],
            project_id=row["project_id"],
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            agent_id=row["agent_id"],
            model_id=row["model_id"],
            risk_level=row["risk_level"],
            risk_score=row["risk_score"],
            confidence=row["confidence"],
            risk_factors=json.loads(row["risk_factors_json"]),
            reason=row["reason"],
            similar_cases=json.loads(row["similar_cases_json"]),
            created_at=row["created_at"],
        )

    # -- policy violations --------------------------------------------------

    def save_violations(self, violations: list[PolicyViolation]) -> list[PolicyViolation]:
        if not violations:
            return violations
        with self._lock:
            for violation in violations:
                self._connection.execute(
                    """
                    INSERT OR REPLACE INTO policy_violations (
                        violation_id, policy_id, project_id, source_id, source_kind,
                        severity, reason, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        violation.violation_id, violation.policy_id, violation.project_id,
                        violation.source_id, violation.source_kind, violation.severity,
                        violation.reason, violation.confidence, violation.created_at,
                    ),
                )
            self._connection.commit()
        return violations

    def violations(
        self,
        project: str,
        *,
        severity: str | None = None,
        policy_id: str | None = None,
        limit: int = 500,
    ) -> list[PolicyViolation]:
        project = ensure_project(project)
        where = ["project_id=?"]
        params: list[Any] = [project]
        for column, value in (("severity", severity), ("policy_id", policy_id)):
            if value:
                where.append(f"{column}=?")
                params.append(value)
        params.append(max(1, min(int(limit), 5000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM policy_violations WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        result: list[PolicyViolation] = []
        for row in rows:
            result.append(
                PolicyViolation(
                    violation_id=row["violation_id"],
                    policy_id=row["policy_id"],
                    project_id=row["project_id"],
                    source_id=row["source_id"],
                    source_kind=row["source_kind"],
                    severity=row["severity"],
                    reason=row["reason"],
                    confidence=row["confidence"],
                    created_at=row["created_at"],
                )
            )
        return result

    # -- review proposals ---------------------------------------------------

    def save_proposal(self, proposal: ReviewProposal) -> ReviewProposal:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO review_proposals (
                    proposal_id, project_id, source_id, source_kind, risk_level,
                    reason, recommended_action, confidence, evidence_json, status,
                    created_at, resolved_at, audit_request_id, reviewer_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.proposal_id, proposal.project_id, proposal.source_id,
                    proposal.source_kind, proposal.risk_level, proposal.reason,
                    proposal.recommended_action, proposal.confidence,
                    _json(proposal.evidence), proposal.status, proposal.created_at,
                    proposal.resolved_at, proposal.audit_request_id,
                    proposal.reviewer_note,
                ),
            )
            self._connection.commit()
        return proposal

    def get_proposal(self, proposal_id: str, project: str) -> ReviewProposal | None:
        project = ensure_project(project)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM review_proposals WHERE proposal_id=? AND project_id=?",
                (proposal_id, project),
            ).fetchone()
        return self._proposal_from_row(row) if row else None

    def proposals(
        self,
        project: str,
        *,
        status: str | None = None,
        risk_level: str | None = None,
        limit: int = 500,
    ) -> list[ReviewProposal]:
        project = ensure_project(project)
        where = ["project_id=?"]
        params: list[Any] = [project]
        for column, value in (("status", status), ("risk_level", risk_level)):
            if value:
                where.append(f"{column}=?")
                params.append(value)
        params.append(max(1, min(int(limit), 5000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM review_proposals WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        return [self._proposal_from_row(row) for row in rows]

    @staticmethod
    def _proposal_from_row(row: sqlite3.Row) -> ReviewProposal:
        return ReviewProposal(
            proposal_id=row["proposal_id"],
            project_id=row["project_id"],
            source_id=row["source_id"],
            source_kind=row["source_kind"],
            risk_level=row["risk_level"],
            reason=row["reason"],
            recommended_action=row["recommended_action"],
            confidence=row["confidence"],
            evidence=json.loads(row["evidence_json"]),
            status=row["status"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            audit_request_id=row["audit_request_id"],
            reviewer_note=row["reviewer_note"],
        )

    # -- governance memory --------------------------------------------------

    def save_memory(self, record: GovernanceMemoryRecord) -> GovernanceMemoryRecord:
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO governance_memory (
                    memory_id, project_id, category, content, source, confidence,
                    evidence_json, created_at, approval_request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.memory_id, record.project_id, record.category,
                    record.content, record.source, record.confidence,
                    _json(record.evidence), record.created_at,
                    record.approval_request_id,
                ),
            )
            self._connection.commit()
        return record

    def memory(
        self,
        project: str,
        *,
        category: str | None = None,
        limit: int = 500,
    ) -> list[GovernanceMemoryRecord]:
        project = ensure_project(project)
        where = ["project_id=?"]
        params: list[Any] = [project]
        if category:
            where.append("category=?")
            params.append(category)
        params.append(max(1, min(int(limit), 5000)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM governance_memory WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?", params
            ).fetchall()
        result: list[GovernanceMemoryRecord] = []
        for row in rows:
            result.append(
                GovernanceMemoryRecord(
                    memory_id=row["memory_id"],
                    project_id=row["project_id"],
                    category=row["category"],
                    content=row["content"],
                    source=row["source"],
                    confidence=row["confidence"],
                    evidence=json.loads(row["evidence_json"]),
                    created_at=row["created_at"],
                    approval_request_id=row["approval_request_id"],
                )
            )
        return result

    def clear(self) -> None:
        with self._lock:
            for table in (
                "governance_records",
                "risk_findings",
                "policy_violations",
                "review_proposals",
                "governance_memory",
            ):
                self._connection.execute(f"DELETE FROM {table}")
            self._connection.commit()
