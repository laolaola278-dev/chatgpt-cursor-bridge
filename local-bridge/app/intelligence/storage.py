from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import Decision, DecisionStatus, Insight, InsightType, Proposal, ProposalStatus, Severity


class IntelligenceStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS insights (id TEXT PRIMARY KEY, project TEXT NOT NULL, type TEXT NOT NULL, severity TEXT NOT NULL, title TEXT NOT NULL, location TEXT NOT NULL, evidence_json TEXT NOT NULL, suggestion TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, project TEXT NOT NULL, insight_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE, type TEXT NOT NULL, target_json TEXT NOT NULL, reasons_json TEXT NOT NULL, expected_gain_json TEXT NOT NULL, risk TEXT NOT NULL, risk_score INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, project TEXT NOT NULL, proposal_id TEXT NOT NULL REFERENCES proposals(id), title TEXT NOT NULL, context TEXT NOT NULL, options_json TEXT NOT NULL, recommendation TEXT NOT NULL, simulation_id TEXT, selected_scenario TEXT, confidence REAL, alternatives_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, history_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS intelligence_insight_project ON insights(project, created_at);
            CREATE INDEX IF NOT EXISTS intelligence_proposal_project ON proposals(project, created_at);
            CREATE INDEX IF NOT EXISTS intelligence_decision_project ON decisions(project, updated_at);
        """)
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(decisions)").fetchall()}
        for name, definition in (("simulation_id", "TEXT"), ("selected_scenario", "TEXT"), ("confidence", "REAL"), ("alternatives_json", "TEXT NOT NULL DEFAULT '[]'"), ("implementation_plan_id", "TEXT"), ("execution_status", "TEXT")):
            if name not in columns:
                self.connection.execute(f"ALTER TABLE decisions ADD COLUMN {name} {definition}")
        self.connection.commit()

    def save_insights(self, insights: Iterable[Insight]) -> None:
        self.connection.executemany("INSERT OR REPLACE INTO insights VALUES(?,?,?,?,?,?,?,?,?)", [(x.id, x.project, x.insight_type.value, x.severity.value, x.title, x.location, json.dumps(x.evidence, ensure_ascii=False), x.suggestion, x.created_at) for x in insights])
        self.connection.commit()

    def get_insight(self, insight_id: str) -> Insight | None:
        row = self.connection.execute("SELECT * FROM insights WHERE id=?", (insight_id,)).fetchone()
        return self._insight(row) if row else None

    def save_proposals(self, proposals: Iterable[Proposal]) -> None:
        self.connection.executemany("INSERT OR REPLACE INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?,?)", [(x.id, x.project, x.insight_id, x.proposal_type, json.dumps(x.target, ensure_ascii=False), json.dumps(x.reasons, ensure_ascii=False), json.dumps(x.expected_gain, ensure_ascii=False), x.risk, x.risk_score, x.status.value, x.created_at) for x in proposals])
        self.connection.commit()

    @staticmethod
    def _insight(row: sqlite3.Row) -> Insight:
        return Insight(row["id"], row["project"], InsightType(row["type"]), Severity(row["severity"]), row["title"], row["location"], json.loads(row["evidence_json"]), row["suggestion"], row["created_at"])

    @staticmethod
    def _proposal(row: sqlite3.Row) -> Proposal:
        return Proposal(row["id"], row["project"], row["insight_id"], row["type"], json.loads(row["target_json"]), json.loads(row["reasons_json"]), json.loads(row["expected_gain_json"]), row["risk"], int(row["risk_score"]), ProposalStatus(row["status"]), row["created_at"])

    @staticmethod
    def _decision(row: sqlite3.Row) -> Decision:
        return Decision(id=row["id"], project=row["project"], proposal_id=row["proposal_id"], title=row["title"], context=row["context"], options=json.loads(row["options_json"]), recommendation=row["recommendation"], simulation_id=row["simulation_id"], selected_scenario=row["selected_scenario"], confidence=row["confidence"], alternatives=json.loads(row["alternatives_json"] or "[]"), implementation_plan_id=row["implementation_plan_id"], execution_status=row["execution_status"], status=DecisionStatus(row["status"]), created_at=row["created_at"], updated_at=row["updated_at"], history=json.loads(row["history_json"]))

    def list_insights(self, project: str | None = None, insight_type: str | None = None, limit: int = 100) -> list[Insight]:
        clauses, values = [], []
        if project: clauses += ["project=?"]; values += [project]
        if insight_type: clauses += ["type=?"]; values += [insight_type]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return [self._insight(row) for row in self.connection.execute(f"SELECT * FROM insights {where} ORDER BY created_at DESC LIMIT ?", (*values, limit)).fetchall()]

    def list_proposals(self, project: str | None = None, status: str | None = None, limit: int = 100) -> list[Proposal]:
        clauses, values = [], []
        if project: clauses += ["project=?"]; values += [project]
        if status: clauses += ["status=?"]; values += [status]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return [self._proposal(row) for row in self.connection.execute(f"SELECT * FROM proposals {where} ORDER BY created_at DESC LIMIT ?", (*values, limit)).fetchall()]

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        row = self.connection.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return self._proposal(row) if row else None

    def save_decision(self, decision: Decision) -> None:
        self.connection.execute("INSERT OR REPLACE INTO decisions (id,project,proposal_id,title,context,options_json,recommendation,simulation_id,selected_scenario,confidence,alternatives_json,implementation_plan_id,execution_status,status,created_at,updated_at,history_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (decision.id, decision.project, decision.proposal_id, decision.title, decision.context, json.dumps(decision.options, ensure_ascii=False), decision.recommendation, decision.simulation_id, decision.selected_scenario, decision.confidence, json.dumps(decision.alternatives, ensure_ascii=False), decision.implementation_plan_id, decision.execution_status, decision.status.value, decision.created_at, decision.updated_at, json.dumps(decision.history, ensure_ascii=False)))
        self.connection.commit()

    def get_decision(self, decision_id: str) -> Decision | None:
        row = self.connection.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
        return self._decision(row) if row else None

    def list_decisions(self, project: str | None = None, status: str | None = None, limit: int = 100) -> list[Decision]:
        clauses, values = [], []
        if project: clauses += ["project=?"]; values += [project]
        if status: clauses += ["status=?"]; values += [status]
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return [self._decision(row) for row in self.connection.execute(f"SELECT * FROM decisions {where} ORDER BY updated_at DESC LIMIT ?", (*values, limit)).fetchall()]
