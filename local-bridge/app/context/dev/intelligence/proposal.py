"""Phase 30 · Patch Proposal Preparation.

The Intelligence layer can build a structured Patch Proposal (target file,
target symbol, proposed change, reason, expected impact, risk). Nothing here
writes source files. Proposals are persisted only after a human approves the
ApprovalStore request, and even then the record is metadata-only — applying
the patch remains the job of the existing controlled tool runtime.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from app.security.sandbox import validate_project_name

from .models import PatchProposal, stable_id

RISK_LEVELS = ("low", "medium", "high")


class PatchProposalGenerator:
    def build(
        self,
        *,
        project: str,
        target_file: str,
        target_symbol: str,
        proposed_change: str,
        reason: str,
        expected_impact: str,
        risk: str,
        agent: str = "ASSISTANT",
    ) -> PatchProposal:
        project = validate_project_name(project)
        risk = str(risk).lower().strip()
        if risk not in RISK_LEVELS:
            risk = "medium"
        proposal_id = stable_id(project, target_file, target_symbol, proposed_change, reason, expected_impact)
        return PatchProposal(
            id=proposal_id,
            project=project,
            agent=agent[:64],
            target_file=target_file[:500],
            target_symbol=target_symbol[:200],
            proposed_change=proposed_change[:4000],
            reason=reason[:2000],
            expected_impact=expected_impact[:2000],
            risk=risk,
            status="proposed",
            applied=False,
        )


class PatchProposalStore:
    """Project-isolated SQLite store for approved proposal records."""

    def __init__(self, db_path: str | Path) -> None:
        self._lock = Lock()
        self._db_path = str(db_path)
        Path(self._db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS patch_proposals (
                id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                agent TEXT NOT NULL,
                target_file TEXT NOT NULL,
                target_symbol TEXT NOT NULL,
                proposed_change TEXT NOT NULL,
                reason TEXT NOT NULL,
                expected_impact TEXT NOT NULL,
                risk TEXT NOT NULL,
                status TEXT NOT NULL,
                applied INTEGER NOT NULL,
                approval_request_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def save(self, proposal: PatchProposal, *, approval_request_id: str = "") -> PatchProposal:
        from datetime import datetime, timezone

        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO patch_proposals (
                    id, project, agent, target_file, target_symbol, proposed_change,
                    reason, expected_impact, risk, status, applied, approval_request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id, proposal.project, proposal.agent, proposal.target_file,
                    proposal.target_symbol, proposal.proposed_change, proposal.reason,
                    proposal.expected_impact, proposal.risk, proposal.status,
                    1 if proposal.applied else 0, approval_request_id,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            self._connection.commit()
        return proposal

    def list(self, project: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM patch_proposals WHERE project=? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, proposal_id: str, project: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM patch_proposals WHERE id=? AND project=?", (proposal_id, project)
        ).fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project": row["project"],
            "agent": row["agent"],
            "targetFile": row["target_file"],
            "targetSymbol": row["target_symbol"],
            "proposedChange": row["proposed_change"],
            "reason": row["reason"],
            "expectedImpact": row["expected_impact"],
            "risk": row["risk"],
            "status": row["status"],
            "applied": bool(row["applied"]),
            "approvalRequestId": row["approval_request_id"],
            "createdAt": row["created_at"],
        }
