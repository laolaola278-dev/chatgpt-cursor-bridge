from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ValidationProject, ValidationRun, ValidationScenario, ValidationScenarioType, ValidationStatus


class ValidationStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path); self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False); self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS validation_projects (id TEXT PRIMARY KEY, project TEXT NOT NULL, repository TEXT NOT NULL, language TEXT NOT NULL, framework TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS validation_scenarios (id TEXT PRIMARY KEY, validation_id TEXT NOT NULL, scenario_type TEXT NOT NULL, description TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS validation_runs (id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, workflow_id TEXT, execution_loop_id TEXT, agents_json TEXT NOT NULL, result TEXT NOT NULL, human_rating REAL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS validation_project_idx ON validation_projects(project);
        CREATE INDEX IF NOT EXISTS validation_scenario_idx ON validation_scenarios(validation_id);
        """); self.connection.commit()

    def save_project(self, project: ValidationProject) -> None:
        self.connection.execute("INSERT OR REPLACE INTO validation_projects VALUES (?,?,?,?,?,?,?)", (project.id, project.project, project.repository, project.language, project.framework, project.created_at, project.status.value)); self.connection.commit()

    def save_scenarios(self, scenarios: list[ValidationScenario]) -> None:
        self.connection.executemany("INSERT OR REPLACE INTO validation_scenarios VALUES (?,?,?,?)", [(item.id, item.validation_id, item.scenario_type.value, item.description) for item in scenarios]); self.connection.commit()

    def save_run(self, run: ValidationRun) -> None:
        self.connection.execute("INSERT OR REPLACE INTO validation_runs VALUES (?,?,?,?,?,?,?,?)", (run.id, run.scenario_id, run.workflow_id, run.execution_loop_id, json.dumps(run.agents), run.result, run.human_rating, run.created_at)); self.connection.commit()

    def get(self, validation_id: str) -> ValidationProject | None:
        row = self.connection.execute("SELECT * FROM validation_projects WHERE id=?", (validation_id,)).fetchone()
        return ValidationProject(row["id"], row["project"], row["repository"], row["language"], row["framework"], row["created_at"], ValidationStatus(row["status"])) if row else None

    def list(self, project: str | None = None) -> list[ValidationProject]:
        rows = self.connection.execute("SELECT * FROM validation_projects WHERE project=? ORDER BY created_at DESC" if project else "SELECT * FROM validation_projects ORDER BY created_at DESC", (project,) if project else ()).fetchall()
        return [ValidationProject(row["id"], row["project"], row["repository"], row["language"], row["framework"], row["created_at"], ValidationStatus(row["status"])) for row in rows]

    def scenarios(self, validation_id: str) -> list[ValidationScenario]:
        return [ValidationScenario(row["id"], row["validation_id"], ValidationScenarioType(row["scenario_type"]), row["description"]) for row in self.connection.execute("SELECT * FROM validation_scenarios WHERE validation_id=? ORDER BY id", (validation_id,)).fetchall()]

    def runs(self, scenario_id: str) -> list[ValidationRun]:
        return [ValidationRun(row["id"], row["scenario_id"], row["workflow_id"], row["execution_loop_id"], json.loads(row["agents_json"]), row["result"], row["human_rating"], row["created_at"]) for row in self.connection.execute("SELECT * FROM validation_runs WHERE scenario_id=? ORDER BY created_at DESC", (scenario_id,)).fetchall()]

    def update_status(self, validation_id: str, status: ValidationStatus) -> ValidationProject:
        project = self.get(validation_id)
        if project is None: raise KeyError(validation_id)
        project.status = status; self.save_project(project); return project
