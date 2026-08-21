from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import BenchmarkCase, BenchmarkProject, BenchmarkResult, BenchmarkRun, BenchmarkStatus


class BenchmarkStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path); self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False); self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS benchmarks (id TEXT PRIMARY KEY, project TEXT NOT NULL, repository TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS benchmark_cases (id TEXT PRIMARY KEY, benchmark_id TEXT NOT NULL, task_type TEXT NOT NULL, description TEXT NOT NULL, difficulty TEXT NOT NULL, expected_result TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS benchmark_runs (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, workflow_id TEXT, execution_loop_id TEXT, agent_ids_json TEXT NOT NULL, started_at TEXT, finished_at TEXT, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS benchmark_results (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, success INTEGER NOT NULL, quality_score REAL NOT NULL, rollback_triggered INTEGER NOT NULL, verification_json TEXT NOT NULL, human_rating REAL);
        CREATE INDEX IF NOT EXISTS benchmark_project_idx ON benchmarks(project);
        CREATE INDEX IF NOT EXISTS benchmark_case_idx ON benchmark_cases(benchmark_id);
        CREATE INDEX IF NOT EXISTS benchmark_result_run_idx ON benchmark_results(run_id);
        """); self.connection.commit()

    def save_project(self, project: BenchmarkProject) -> None:
        self.connection.execute("INSERT OR REPLACE INTO benchmarks VALUES (?,?,?,?,?)", (project.id, project.project, project.repository, project.created_at, project.status.value)); self.connection.commit()

    def save_cases(self, cases: list[BenchmarkCase]) -> None:
        self.connection.executemany("INSERT OR REPLACE INTO benchmark_cases VALUES (?,?,?,?,?,?)", [(c.id, c.benchmark_id, c.task_type, c.description, c.difficulty, c.expected_result) for c in cases]); self.connection.commit()

    def save_run(self, run: BenchmarkRun) -> None:
        self.connection.execute("INSERT OR REPLACE INTO benchmark_runs VALUES (?,?,?,?,?,?,?,?)", (run.id, run.case_id, run.workflow_id, run.execution_loop_id, json.dumps(run.agent_ids), run.started_at, run.finished_at, run.status)); self.connection.commit()

    def save_result(self, result: BenchmarkResult) -> None:
        self.connection.execute("INSERT OR REPLACE INTO benchmark_results VALUES (?,?,?,?,?,?,?)", (result.id, result.run_id, int(result.success), result.quality_score, int(result.rollback_triggered), json.dumps(result.verification_result), result.human_rating)); self.connection.commit()

    def get(self, benchmark_id: str) -> BenchmarkProject | None:
        row = self.connection.execute("SELECT * FROM benchmarks WHERE id=?", (benchmark_id,)).fetchone()
        return BenchmarkProject(row["id"], row["project"], row["repository"], row["created_at"], BenchmarkStatus(row["status"])) if row else None

    def list(self, project: str | None = None) -> list[BenchmarkProject]:
        rows = self.connection.execute("SELECT * FROM benchmarks WHERE project=? ORDER BY created_at DESC" if project else "SELECT * FROM benchmarks ORDER BY created_at DESC", (project,) if project else ()).fetchall()
        return [BenchmarkProject(row["id"], row["project"], row["repository"], row["created_at"], BenchmarkStatus(row["status"])) for row in rows]

    def cases(self, benchmark_id: str) -> list[BenchmarkCase]:
        return [BenchmarkCase(row["id"], row["benchmark_id"], row["task_type"], row["description"], row["difficulty"], row["expected_result"]) for row in self.connection.execute("SELECT * FROM benchmark_cases WHERE benchmark_id=? ORDER BY id", (benchmark_id,)).fetchall()]

    def results(self, benchmark_id: str) -> list[BenchmarkResult]:
        rows = self.connection.execute("SELECT r.* FROM benchmark_results r JOIN benchmark_runs run ON run.id=r.run_id JOIN benchmark_cases c ON c.id=run.case_id WHERE c.benchmark_id=? ORDER BY r.id", (benchmark_id,)).fetchall()
        return [BenchmarkResult(row["id"], row["run_id"], bool(row["success"]), float(row["quality_score"]), bool(row["rollback_triggered"]), json.loads(row["verification_json"]), row["human_rating"]) for row in rows]

    def update_status(self, benchmark_id: str, status: BenchmarkStatus) -> BenchmarkProject:
        project = self.get(benchmark_id)
        if project is None: raise KeyError(benchmark_id)
        project.status = status; self.save_project(project); return project
