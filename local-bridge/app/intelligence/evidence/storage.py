from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from app.intelligence.common import ensure_project

from .models import EvidenceBundle


class EvidenceStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path); self.db_path.parent.mkdir(parents=True, exist_ok=True); self._lock = Lock()
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False); self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS intelligence_evidence_bundles (
                bundle_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, decision_id TEXT,
                observation_json TEXT NOT NULL, pattern_json TEXT NOT NULL, prediction_json TEXT NOT NULL,
                risk_json TEXT NOT NULL, strategy_json TEXT NOT NULL, recommendation_json TEXT NOT NULL,
                historical_json TEXT NOT NULL, provenance_json TEXT NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_evidence_project ON intelligence_evidence_bundles(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS intelligence_evidence_decision ON intelligence_evidence_bundles(project_id, decision_id);
        """); self.connection.commit()

    def save(self, bundle: EvidenceBundle) -> EvidenceBundle:
        with self._lock:
            self.connection.execute("""INSERT OR REPLACE INTO intelligence_evidence_bundles
              (bundle_id, project_id, decision_id, observation_json, pattern_json, prediction_json, risk_json, strategy_json, recommendation_json, historical_json, provenance_json, confidence, created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (bundle.bundle_id, bundle.project_id, bundle.decision_id, json.dumps(bundle.observation_ids), json.dumps(bundle.pattern_ids), json.dumps(bundle.prediction_ids), json.dumps(bundle.risk_ids), json.dumps(bundle.strategy_ids), json.dumps(bundle.recommendation_ids), json.dumps(bundle.historical_evidence), json.dumps(bundle.provenance), bundle.confidence, bundle.created_at)); self.connection.commit()
        return bundle

    def get(self, bundle_id: str, project_id: str | None = None) -> EvidenceBundle | None:
        query = "SELECT * FROM intelligence_evidence_bundles WHERE bundle_id=?"; values: list[Any] = [bundle_id]
        if project_id is not None: query += " AND project_id=?"; values.append(ensure_project(project_id))
        row = self.connection.execute(query, values).fetchone(); return self._from_row(row) if row else None

    def get_for_decision(self, decision_id: str, project_id: str) -> EvidenceBundle | None:
        row = self.connection.execute("SELECT * FROM intelligence_evidence_bundles WHERE decision_id=? AND project_id=? ORDER BY created_at DESC LIMIT 1", (decision_id, ensure_project(project_id))).fetchone()
        return self._from_row(row) if row else None

    def list(self, project_id: str, limit: int = 100) -> list[EvidenceBundle]:
        project = ensure_project(project_id)
        return [self._from_row(row) for row in self.connection.execute("SELECT * FROM intelligence_evidence_bundles WHERE project_id=? ORDER BY created_at DESC LIMIT ?", (project, max(1, min(int(limit), 1000)))).fetchall()]

    def link_decision(self, bundle_id: str, decision_id: str, project_id: str) -> EvidenceBundle:
        bundle = self.get(bundle_id, project_id)
        if bundle is None: raise ValueError(f"Evidence bundle '{bundle_id}' was not found for project")
        linked = EvidenceBundle(bundle.bundle_id, bundle.project_id, decision_id, bundle.observation_ids, bundle.pattern_ids, bundle.prediction_ids, bundle.risk_ids, bundle.strategy_ids, bundle.recommendation_ids, bundle.historical_evidence, bundle.provenance, bundle.confidence, bundle.created_at)
        return self.save(linked)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> EvidenceBundle:
        return EvidenceBundle(row["bundle_id"], row["project_id"], row["decision_id"], json.loads(row["observation_json"] or "[]"), json.loads(row["pattern_json"] or "[]"), json.loads(row["prediction_json"] or "[]"), json.loads(row["risk_json"] or "[]"), json.loads(row["strategy_json"] or "[]"), json.loads(row["recommendation_json"] or "[]"), json.loads(row["historical_json"] or "[]"), json.loads(row["provenance_json"] or "[]"), float(row["confidence"]), row["created_at"])
