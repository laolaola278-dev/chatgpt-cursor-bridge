from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from secrets import token_hex
from threading import Lock
from typing import Any, Iterable

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now
from app.security.validator import ValidationFailed


class OutcomeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class StrategyOutcome:
    outcome_id: str
    project_id: str
    strategy_id: str
    decision_id: str | None
    status: OutcomeStatus
    expected_outcome: str
    actual_outcome: str
    difference: str
    evidence: list[str] = field(default_factory=list)
    source: str = "user_decision"
    confidence: float = 0.5
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        for name in ("strategy_id", "expected_outcome", "actual_outcome", "difference", "source"):
            object.__setattr__(self, name, sanitize_text(getattr(self, name), limit=4000).strip())
        if not self.strategy_id:
            raise ValidationFailed("Strategy id is required for an outcome")
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id, "outcomeId": self.outcome_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "strategy_id": self.strategy_id, "strategyId": self.strategy_id,
            "decision_id": self.decision_id, "decisionId": self.decision_id,
            "status": self.status.value,
            "expected_outcome": self.expected_outcome, "expectedOutcome": self.expected_outcome,
            "actual_outcome": self.actual_outcome, "actualOutcome": self.actual_outcome,
            "difference": self.difference, "evidence": list(self.evidence),
            "source": self.source, "confidence": self.confidence,
            "created_at": self.created_at, "createdAt": self.created_at,
            "readOnly": True,
        }


class OutcomeStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path); self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock(); self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False); self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS intelligence_outcomes (
                outcome_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, strategy_id TEXT NOT NULL,
                decision_id TEXT, status TEXT NOT NULL, expected_outcome TEXT NOT NULL,
                actual_outcome TEXT NOT NULL, difference TEXT NOT NULL, evidence_json TEXT NOT NULL,
                source TEXT NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_outcomes_project ON intelligence_outcomes(project_id, created_at DESC);
        """); self.connection.commit()

    def save(self, outcome: StrategyOutcome) -> StrategyOutcome:
        with self._lock:
            self.connection.execute("""INSERT OR REPLACE INTO intelligence_outcomes
              (outcome_id, project_id, strategy_id, decision_id, status, expected_outcome, actual_outcome, difference, evidence_json, source, confidence, created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (outcome.outcome_id, outcome.project_id, outcome.strategy_id, outcome.decision_id, outcome.status.value, outcome.expected_outcome, outcome.actual_outcome, outcome.difference, json.dumps(outcome.evidence), outcome.source, outcome.confidence, outcome.created_at)); self.connection.commit()
        return outcome

    def record(self, *, project_id: str, strategy_id: str, status: OutcomeStatus | str, expected_outcome: str, actual_outcome: str, difference: str = "", evidence: list[str] | None = None, decision_id: str | None = None, source: str = "user_decision", confidence: float = 0.5) -> StrategyOutcome:
        try: parsed = status if isinstance(status, OutcomeStatus) else OutcomeStatus(str(status).upper())
        except ValueError as exc: raise ValidationFailed("Unknown strategy outcome status") from exc
        return self.save(StrategyOutcome(f"out_{token_hex(8)}", project_id, strategy_id, decision_id, parsed, expected_outcome, actual_outcome, difference, evidence or [], source, confidence))

    def get(self, outcome_id: str, project_id: str | None = None) -> StrategyOutcome | None:
        query = "SELECT * FROM intelligence_outcomes WHERE outcome_id=?"; values: list[Any] = [outcome_id]
        if project_id is not None: query += " AND project_id=?"; values.append(ensure_project(project_id))
        row = self.connection.execute(query, values).fetchone(); return self._from_row(row) if row else None

    def list(self, project_id: str, status: str | None = None, limit: int = 100) -> list[StrategyOutcome]:
        project = ensure_project(project_id); query = "SELECT * FROM intelligence_outcomes WHERE project_id=?"; values: list[Any] = [project]
        if status: query += " AND status=?"; values.append(str(status).upper())
        query += " ORDER BY created_at DESC, outcome_id DESC LIMIT ?"; values.append(max(1, min(int(limit), 1000)))
        return [self._from_row(row) for row in self.connection.execute(query, values).fetchall()]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StrategyOutcome:
        return StrategyOutcome(row["outcome_id"], row["project_id"], row["strategy_id"], row["decision_id"], OutcomeStatus(row["status"]), row["expected_outcome"], row["actual_outcome"], row["difference"], json.loads(row["evidence_json"] or "[]"), row["source"], float(row["confidence"]), row["created_at"])


class StrategyOutcomeTracker:
    def __init__(self, store: OutcomeStore) -> None: self.store = store
    def record(self, **kwargs: Any) -> StrategyOutcome: return self.store.record(**kwargs)
    def list(self, project_id: str, **kwargs: Any) -> list[StrategyOutcome]: return self.store.list(project_id, **kwargs)
