"""SQLite storage for Phase 27 validation records.

Every record is project-scoped; queries always filter by project so records
from one project can never leak into another. The store is append-mostly:
evaluations, effectiveness, decision outcomes, and benchmark runs are
insert-or-replace by their generated id only.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from app.intelligence.common import ensure_project

from .models import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkRun,
    DecisionOutcome,
    EvaluationRecord,
    KnowledgeImprovement,
    RecommendationEffectiveness,
)


class ValidationStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS intelligence_evaluations (
                evaluation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                prediction_id TEXT NOT NULL, evaluation_kind TEXT NOT NULL,
                input_context TEXT NOT NULL, prediction_result TEXT NOT NULL,
                expected_outcome TEXT NOT NULL, actual_outcome TEXT NOT NULL,
                evaluation_result TEXT NOT NULL, confidence REAL NOT NULL,
                evaluated_at TEXT NOT NULL, agent_id TEXT NOT NULL,
                model_id TEXT NOT NULL, decision_id TEXT, recommendation_id TEXT,
                evidence_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intelligence_recommendation_effectiveness (
                effectiveness_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                recommendation_id TEXT NOT NULL, content TEXT NOT NULL,
                confidence REAL NOT NULL, user_decision TEXT NOT NULL,
                actual_result TEXT NOT NULL, effectiveness_score REAL NOT NULL,
                classification TEXT NOT NULL, failure_reason TEXT NOT NULL,
                decision_id TEXT, evaluated_at TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intelligence_decision_outcomes (
                outcome_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                decision_id TEXT NOT NULL, decision_type TEXT NOT NULL,
                title TEXT NOT NULL, expected_outcome TEXT NOT NULL,
                actual_outcome TEXT NOT NULL, status TEXT NOT NULL,
                evaluated_at TEXT NOT NULL, agent_id TEXT NOT NULL,
                model_id TEXT NOT NULL, evidence_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intelligence_benchmarks (
                benchmark_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
                dataset_name TEXT NOT NULL, project_id TEXT NOT NULL,
                category TEXT NOT NULL, model_id TEXT NOT NULL,
                score REAL NOT NULL, accuracy REAL NOT NULL,
                determinism_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                cases_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intelligence_knowledge_improvements (
                improvement_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                evaluation_id TEXT NOT NULL, prediction_id TEXT NOT NULL,
                category TEXT NOT NULL, content TEXT NOT NULL,
                source TEXT NOT NULL, evidence_json TEXT NOT NULL,
                confidence REAL NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, validated_at TEXT NOT NULL,
                approval_request_id TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS intelligence_evaluations_project
              ON intelligence_evaluations(project_id, evaluated_at DESC);
            CREATE INDEX IF NOT EXISTS intelligence_effectiveness_project
              ON intelligence_recommendation_effectiveness(project_id, evaluated_at DESC);
            CREATE INDEX IF NOT EXISTS intelligence_decision_outcomes_project
              ON intelligence_decision_outcomes(project_id, evaluated_at DESC);
            CREATE INDEX IF NOT EXISTS intelligence_benchmarks_project
              ON intelligence_benchmarks(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS intelligence_improvements_project
              ON intelligence_knowledge_improvements(project_id, created_at DESC);
            """
        )
        self.connection.commit()

    # ------------------------------------------------------------------ evaluations

    def save_evaluation(self, record: EvaluationRecord) -> EvaluationRecord:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_evaluations
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.evaluation_id, record.project_id, record.prediction_id,
                    record.evaluation_kind, record.input_context, record.prediction_result,
                    record.expected_outcome, record.actual_outcome, record.evaluation_result,
                    record.confidence, record.evaluated_at, record.agent_id, record.model_id,
                    record.decision_id, record.recommendation_id, json.dumps(record.evidence),
                ),
            )
            self.connection.commit()
        return record

    def get_evaluation(self, evaluation_id: str, project_id: str | None = None) -> EvaluationRecord | None:
        query = "SELECT * FROM intelligence_evaluations WHERE evaluation_id=?"
        values: list[Any] = [evaluation_id]
        if project_id is not None:
            query += " AND project_id=?"
            values.append(ensure_project(project_id))
        row = self.connection.execute(query, values).fetchone()
        return self._evaluation_from_row(row) if row else None

    def evaluations(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        agent_id: str | None = None,
        model_id: str | None = None,
        limit: int = 2000,
    ) -> list[EvaluationRecord]:
        project = ensure_project(project_id)
        query = "SELECT * FROM intelligence_evaluations WHERE project_id=?"
        values: list[Any] = [project]
        if kind:
            query += " AND evaluation_kind=?"
            values.append(str(kind).lower().strip())
        if agent_id:
            query += " AND agent_id=?"
            values.append(str(agent_id).strip())
        if model_id:
            query += " AND model_id=?"
            values.append(str(model_id).strip())
        query += " ORDER BY evaluated_at DESC, evaluation_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 5000)))
        return [self._evaluation_from_row(row) for row in self.connection.execute(query, values).fetchall()]

    @staticmethod
    def _evaluation_from_row(row: sqlite3.Row) -> EvaluationRecord:
        return EvaluationRecord(
            row["evaluation_id"], row["project_id"], row["prediction_id"], row["evaluation_kind"],
            row["input_context"], row["prediction_result"], row["expected_outcome"],
            row["actual_outcome"], row["evaluation_result"], float(row["confidence"]),
            row["evaluated_at"], row["agent_id"], row["model_id"], row["decision_id"],
            row["recommendation_id"], json.loads(row["evidence_json"] or "[]"),
        )

    # ------------------------------------------------------- recommendation effectiveness

    def save_effectiveness(self, record: RecommendationEffectiveness) -> RecommendationEffectiveness:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_recommendation_effectiveness
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.effectiveness_id, record.project_id, record.recommendation_id,
                    record.content, record.confidence, record.user_decision,
                    record.actual_result, record.effectiveness_score, record.classification,
                    record.failure_reason, record.decision_id, record.evaluated_at,
                    json.dumps(record.evidence),
                ),
            )
            self.connection.commit()
        return record

    def effectiveness(self, project_id: str, limit: int = 2000) -> list[RecommendationEffectiveness]:
        project = ensure_project(project_id)
        rows = self.connection.execute(
            "SELECT * FROM intelligence_recommendation_effectiveness WHERE project_id=? ORDER BY evaluated_at DESC, effectiveness_id DESC LIMIT ?",
            (project, max(1, min(int(limit), 5000))),
        ).fetchall()
        return [
            RecommendationEffectiveness(
                row["effectiveness_id"], row["project_id"], row["recommendation_id"],
                row["content"], float(row["confidence"]), row["user_decision"],
                row["actual_result"], float(row["effectiveness_score"]), row["classification"],
                row["failure_reason"], row["decision_id"], row["evaluated_at"],
                json.loads(row["evidence_json"] or "[]"),
            )
            for row in rows
        ]

    # ------------------------------------------------------------ decision outcomes

    def save_decision_outcome(self, record: DecisionOutcome) -> DecisionOutcome:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_decision_outcomes
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.outcome_id, record.project_id, record.decision_id,
                    record.decision_type, record.title, record.expected_outcome,
                    record.actual_outcome, record.status, record.evaluated_at,
                    record.agent_id, record.model_id, json.dumps(record.evidence),
                ),
            )
            self.connection.commit()
        return record

    def decision_outcomes(
        self, project_id: str, *, decision_type: str | None = None, limit: int = 2000
    ) -> list[DecisionOutcome]:
        project = ensure_project(project_id)
        query = "SELECT * FROM intelligence_decision_outcomes WHERE project_id=?"
        values: list[Any] = [project]
        if decision_type:
            query += " AND decision_type=?"
            values.append(str(decision_type).lower().strip())
        query += " ORDER BY evaluated_at DESC, outcome_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 5000)))
        return [
            DecisionOutcome(
                row["outcome_id"], row["project_id"], row["decision_id"], row["decision_type"],
                row["title"], row["expected_outcome"], row["actual_outcome"], row["status"],
                row["evaluated_at"], row["agent_id"], row["model_id"],
                json.loads(row["evidence_json"] or "[]"),
            )
            for row in self.connection.execute(query, values).fetchall()
        ]

    # ------------------------------------------------------------------ benchmarks

    def save_benchmark(self, run: BenchmarkRun) -> BenchmarkRun:
        cases = [
            {
                "case": result.case.as_dict(),
                "predicted": result.predicted,
                "correct": result.correct,
                "score": result.score,
            }
            for result in run.cases
        ]
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_benchmarks
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run.benchmark_id, run.dataset_id, run.dataset_name, run.project_id,
                    run.category, run.model_id, run.score, run.accuracy,
                    run.determinism_hash, run.created_at, json.dumps(cases),
                ),
            )
            self.connection.commit()
        return run

    def get_benchmark(self, benchmark_id: str, project_id: str | None = None) -> BenchmarkRun | None:
        query = "SELECT * FROM intelligence_benchmarks WHERE benchmark_id=?"
        values: list[Any] = [benchmark_id]
        if project_id is not None:
            query += " AND project_id=?"
            values.append(ensure_project(project_id))
        row = self.connection.execute(query, values).fetchone()
        return self._benchmark_from_row(row) if row else None

    def benchmarks(self, project_id: str, limit: int = 200, *, model_id: str | None = None) -> list[BenchmarkRun]:
        project = ensure_project(project_id)
        query = "SELECT * FROM intelligence_benchmarks WHERE project_id=?"
        values: list[Any] = [project]
        if model_id:
            query += " AND model_id=?"
            values.append(str(model_id).strip())
        query += " ORDER BY created_at DESC, benchmark_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 1000)))
        rows = self.connection.execute(query, values).fetchall()
        return [self._benchmark_from_row(row) for row in rows]

    @staticmethod
    def _benchmark_from_row(row: sqlite3.Row) -> BenchmarkRun:
        cases = json.loads(row["cases_json"] or "[]")
        results = [
            BenchmarkCaseResult(
                BenchmarkCase(case["case"]["case_id"], case["case"]["category"], case["case"]["input"], case["case"]["expected"]),
                case["predicted"], bool(case["correct"]), float(case["score"]),
            )
            for case in cases
        ]
        return BenchmarkRun(
            row["benchmark_id"], row["dataset_id"], row["dataset_name"], row["project_id"],
            row["category"], row["model_id"], float(row["score"]), float(row["accuracy"]),
            row["determinism_hash"], row["created_at"], results,
        )

    # ------------------------------------------------------ knowledge improvements

    def save_improvement(self, record: KnowledgeImprovement) -> KnowledgeImprovement:
        with self._lock:
            self.connection.execute(
                """INSERT OR REPLACE INTO intelligence_knowledge_improvements
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.improvement_id, record.project_id, record.evaluation_id,
                    record.prediction_id, record.category, record.content, record.source,
                    json.dumps(record.evidence), record.confidence, record.status,
                    record.created_at, record.validated_at, record.approval_request_id,
                ),
            )
            self.connection.commit()
        return record

    def improvements(
        self, project_id: str, *, status: str | None = None, limit: int = 1000
    ) -> list[KnowledgeImprovement]:
        project = ensure_project(project_id)
        query = "SELECT * FROM intelligence_knowledge_improvements WHERE project_id=?"
        values: list[Any] = [project]
        if status:
            query += " AND status=?"
            values.append(str(status).lower().strip())
        query += " ORDER BY created_at DESC, improvement_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 3000)))
        return [
            KnowledgeImprovement(
                row["improvement_id"], row["project_id"], row["evaluation_id"],
                row["prediction_id"], row["category"], row["content"], row["source"],
                json.loads(row["evidence_json"] or "[]"), float(row["confidence"]),
                row["status"], row["created_at"], row["validated_at"], row["approval_request_id"],
            )
            for row in self.connection.execute(query, values).fetchall()
        ]

    def save_many(self, records: Iterable[Any]) -> list[Any]:
        result: list[Any] = []
        for record in records:
            if isinstance(record, EvaluationRecord):
                result.append(self.save_evaluation(record))
            elif isinstance(record, RecommendationEffectiveness):
                result.append(self.save_effectiveness(record))
            elif isinstance(record, DecisionOutcome):
                result.append(self.save_decision_outcome(record))
            elif isinstance(record, BenchmarkRun):
                result.append(self.save_benchmark(record))
            elif isinstance(record, KnowledgeImprovement):
                result.append(self.save_improvement(record))
        return result
