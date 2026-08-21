from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import Evaluation, Plan, PlanStatus, Scenario, ScenarioStatus, Simulation, SimulationStatus


class SimulationStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS simulations (id TEXT PRIMARY KEY, project TEXT NOT NULL, problem TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, history_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, simulation_id TEXT NOT NULL REFERENCES simulations(id) ON DELETE CASCADE, name TEXT NOT NULL, type TEXT NOT NULL, changes_json TEXT NOT NULL, affected_files_json TEXT NOT NULL, dependent_modules_json TEXT NOT NULL, affected_tests_json TEXT NOT NULL, workflow_stages_json TEXT NOT NULL, memory_impacts_json TEXT NOT NULL, risk_score INTEGER NOT NULL, impact_score INTEGER NOT NULL, risk TEXT NOT NULL, status TEXT NOT NULL, evaluation_json TEXT);
        CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, simulation_id TEXT NOT NULL REFERENCES simulations(id) ON DELETE CASCADE, scenario_id TEXT NOT NULL REFERENCES scenarios(id), content TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS simulation_project ON simulations(project, updated_at);
        CREATE INDEX IF NOT EXISTS scenario_simulation ON scenarios(simulation_id, risk_score);
        """)
        self.connection.commit()

    def save_simulation(self, simulation: Simulation) -> None:
        # Do not use INSERT OR REPLACE here: SQLite implements REPLACE as a
        # delete followed by an insert, which would cascade-delete scenarios
        # and plans when a simulation transitions to COMPLETED.
        self.connection.execute(
            """
            INSERT INTO simulations (id, project, problem, status, created_at, updated_at, history_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              project=excluded.project,
              problem=excluded.problem,
              status=excluded.status,
              created_at=excluded.created_at,
              updated_at=excluded.updated_at,
              history_json=excluded.history_json
            """,
            (
                simulation.id,
                simulation.project,
                simulation.problem,
                simulation.status.value,
                simulation.created_at,
                simulation.updated_at,
                json.dumps(simulation.history, ensure_ascii=False),
            ),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SimulationStorage":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _simulation(row: sqlite3.Row) -> Simulation:
        return Simulation(row["id"], row["project"], row["problem"], SimulationStatus(row["status"]), row["created_at"], row["updated_at"], json.loads(row["history_json"]))

    def get_simulation(self, simulation_id: str) -> Simulation | None:
        row = self.connection.execute("SELECT * FROM simulations WHERE id=?", (simulation_id,)).fetchone()
        return self._simulation(row) if row else None

    def list_simulations(self, project: str | None = None, limit: int = 100) -> list[Simulation]:
        if project:
            rows = self.connection.execute("SELECT * FROM simulations WHERE project=? ORDER BY updated_at DESC LIMIT ?", (project, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM simulations ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._simulation(row) for row in rows]

    def save_scenarios(self, scenarios: Iterable[Scenario]) -> None:
        self.connection.executemany("INSERT OR REPLACE INTO scenarios VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [(x.id, x.simulation_id, x.name, x.scenario_type, json.dumps(x.changes, ensure_ascii=False), json.dumps(x.affected_files, ensure_ascii=False), json.dumps(x.dependent_modules, ensure_ascii=False), json.dumps(x.affected_tests, ensure_ascii=False), json.dumps(x.workflow_stages, ensure_ascii=False), json.dumps(x.memory_impacts, ensure_ascii=False), x.risk_score, x.impact_score, x.risk, x.status.value, None) for x in scenarios])
        self.connection.commit()

    @staticmethod
    def _scenario(row: sqlite3.Row) -> Scenario:
        return Scenario(row["id"], row["simulation_id"], row["name"], row["type"], json.loads(row["changes_json"]), json.loads(row["affected_files_json"]), json.loads(row["dependent_modules_json"]), json.loads(row["affected_tests_json"]), json.loads(row["workflow_stages_json"]), json.loads(row["memory_impacts_json"]), int(row["risk_score"]), int(row["impact_score"]), row["risk"], ScenarioStatus(row["status"]))

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        row = self.connection.execute("SELECT * FROM scenarios WHERE id=?", (scenario_id,)).fetchone()
        return self._scenario(row) if row else None

    def list_scenarios(self, simulation_id: str) -> list[Scenario]:
        return [self._scenario(row) for row in self.connection.execute("SELECT * FROM scenarios WHERE simulation_id=? ORDER BY impact_score, risk_score", (simulation_id,)).fetchall()]

    def save_evaluation(self, evaluation: Evaluation) -> None:
        self.connection.execute("UPDATE scenarios SET evaluation_json=? WHERE id=?", (json.dumps(evaluation.as_dict(), ensure_ascii=False), evaluation.scenario_id))
        self.connection.commit()

    def get_evaluation(self, scenario_id: str) -> Evaluation | None:
        row = self.connection.execute("SELECT evaluation_json FROM scenarios WHERE id=?", (scenario_id,)).fetchone()
        if not row or not row["evaluation_json"]: return None
        data = json.loads(row["evaluation_json"])
        return Evaluation(data["scenario"], int(data["score"]), data["risk"], data["advantages"], data["disadvantages"], data["factors"])

    def save_plan(self, plan: Plan) -> None:
        self.connection.execute("INSERT OR REPLACE INTO plans VALUES(?,?,?,?,?,?)", (plan.id, plan.simulation_id, plan.scenario_id, plan.content, plan.status.value, plan.created_at))
        self.connection.commit()

    def get_plan(self, plan_id: str) -> Plan | None:
        row = self.connection.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        return self._plan(row) if row else None

    def list_plans(self, simulation_id: str) -> list[Plan]:
        return [self._plan(row) for row in self.connection.execute("SELECT * FROM plans WHERE simulation_id=? ORDER BY created_at DESC", (simulation_id,)).fetchall()]

    @staticmethod
    def _plan(row: sqlite3.Row) -> Plan:
        return Plan(row["id"], row["simulation_id"], row["scenario_id"], row["content"], PlanStatus(row["status"]), row["created_at"])
