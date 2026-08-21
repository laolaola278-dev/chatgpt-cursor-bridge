"""SQLite persistence for the organization engineering strategy layer.

Stores impact reports, risk reports, candidate strategies, evaluations,
organization decisions, strategy simulations and strategic recommendations.
All tables use CREATE TABLE IF NOT EXISTS so pre-existing databases keep
working; nothing here can modify project source code or memory.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import (
    DecisionStatus,
    EngineeringStrategy,
    OrganizationDecision,
    OrganizationImpactReport,
    OrganizationRiskReport,
    OrganizationStrategySimulation,
    StrategicRecommendation,
    StrategyEvaluation,
    StrategyStatus,
    StrategyType,
)


class OrganizationStrategyStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS org_strategies (
                id TEXT PRIMARY KEY, strategy_type TEXT NOT NULL, title TEXT NOT NULL,
                problem TEXT NOT NULL, status TEXT NOT NULL, data_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_strategy_evaluations (
                id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, data_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_strategy_decisions (
                id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, title TEXT NOT NULL,
                status TEXT NOT NULL, data_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_strategy_simulations (
                id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, data_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_recommendations (
                id TEXT PRIMARY KEY, data_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_impact_reports (
                id TEXT PRIMARY KEY, source_node TEXT NOT NULL, data_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS org_risk_reports (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, data_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS org_strategies_type ON org_strategies(strategy_type);
            CREATE INDEX IF NOT EXISTS org_strategies_status ON org_strategies(status);
            CREATE INDEX IF NOT EXISTS org_strategy_decisions_status ON org_strategy_decisions(status);
            CREATE INDEX IF NOT EXISTS org_impact_source ON org_impact_reports(source_node);
            CREATE INDEX IF NOT EXISTS org_risk_source ON org_risk_reports(source);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    # -- strategies ---------------------------------------------------------

    def save_strategy(self, strategy: EngineeringStrategy) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_strategies(id,strategy_type,title,problem,status,data_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (strategy.id, strategy.strategy_type.value, strategy.title, strategy.problem,
             strategy.status.value, json.dumps(strategy.as_dict(), ensure_ascii=False), strategy.created_at),
        )
        self.connection.commit()

    def get_strategy(self, strategy_id: str) -> EngineeringStrategy | None:
        row = self.connection.execute("SELECT * FROM org_strategies WHERE id=?", (strategy_id,)).fetchone()
        return self._strategy(row) if row else None

    def list_strategies(self, project: str | None = None, limit: int = 200) -> list[EngineeringStrategy]:
        if project:
            rows = self.connection.execute(
                "SELECT * FROM org_strategies ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            output = [self._strategy(row) for row in rows if row is not None]
            return [strategy for strategy in output if project in strategy.affected_projects]
        rows = self.connection.execute(
            "SELECT * FROM org_strategies ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._strategy(row) for row in rows if row is not None]

    @staticmethod
    def _strategy(row: sqlite3.Row) -> EngineeringStrategy:
        value = json.loads(row["data_json"])
        return EngineeringStrategy(
            strategy_type=StrategyType(value["strategy_type"]),
            title=value["title"],
            problem=value["problem"],
            affected_projects=value.get("affected_projects", []),
            affected_teams=value.get("affected_teams", []),
            benefits=value.get("benefits", []),
            risks=value.get("risks", []),
            estimated_effort=value.get("estimated_effort", ""),
            confidence=float(value.get("confidence", 0)),
            priority=value.get("priority", "medium"),
            alternatives=value.get("alternatives", []),
            evidence=value.get("evidence", []),
            status=StrategyStatus(value.get("status", "PROPOSED")),
            id=value["strategy_id"],
            created_at=value.get("createdAt", ""),
        )

    # -- evaluations --------------------------------------------------------

    def save_evaluation(self, evaluation: StrategyEvaluation) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_strategy_evaluations(id,strategy_id,data_json,created_at) VALUES(?,?,?,?)",
            (evaluation.id, evaluation.strategy_id,
             json.dumps(evaluation.as_dict(), ensure_ascii=False), evaluation.created_at),
        )
        self.connection.commit()

    def list_evaluations(self, strategy_id: str | None = None, limit: int = 100) -> list[StrategyEvaluation]:
        if strategy_id:
            rows = self.connection.execute(
                "SELECT * FROM org_strategy_evaluations WHERE strategy_id=? ORDER BY created_at DESC LIMIT ?",
                (strategy_id, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM org_strategy_evaluations ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._evaluation(row) for row in rows if row is not None]

    @staticmethod
    def _evaluation(row: sqlite3.Row) -> StrategyEvaluation:
        value = json.loads(row["data_json"])
        return StrategyEvaluation(
            strategy_id=value["strategy_id"],
            criteria={key: float(item) for key, item in value.get("criteria", {}).items()},
            composite_score=float(value.get("composite_score", 0)),
            recommended=bool(value.get("recommended", False)),
            id=value["evaluation_id"],
            created_at=value.get("createdAt", ""),
        )

    # -- decisions ----------------------------------------------------------

    def save_decision(self, decision: OrganizationDecision) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_strategy_decisions(id,organization_id,title,status,data_json,created_at) VALUES(?,?,?,?,?,?)",
            (decision.id, decision.organization_id, decision.title, decision.status.value,
             json.dumps(decision.as_dict(), ensure_ascii=False), decision.created_at),
        )
        self.connection.commit()

    def get_decision(self, decision_id: str) -> OrganizationDecision | None:
        row = self.connection.execute("SELECT * FROM org_strategy_decisions WHERE id=?", (decision_id,)).fetchone()
        return self._decision(row) if row else None

    def list_decisions(self, status: str | None = None, limit: int = 200) -> list[OrganizationDecision]:
        if status:
            rows = self.connection.execute(
                "SELECT * FROM org_strategy_decisions WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status.upper(), limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM org_strategy_decisions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decision(row) for row in rows if row is not None]

    @staticmethod
    def _decision(row: sqlite3.Row) -> OrganizationDecision:
        value = json.loads(row["data_json"])
        return OrganizationDecision(
            organization_id=value["organization_id"],
            title=value["title"],
            source_graph_nodes=value.get("source_graph_nodes", []),
            selected_strategy=value.get("selected_strategy", ""),
            alternatives=value.get("alternatives", []),
            confidence=float(value.get("confidence", 0)),
            impact_report=value.get("impact_report", {}),
            risk_report=value.get("risk_report", {}),
            status=DecisionStatus(value.get("status", "PROPOSED")),
            history=[{"from": str(item.get("from", "")), "to": str(item.get("to", "")), "at": str(item.get("at", ""))} for item in value.get("history", [])],
            id=value["decision_id"],
            created_at=value.get("createdAt", ""),
        )

    # -- simulations --------------------------------------------------------

    def save_simulation(self, simulation: OrganizationStrategySimulation) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_strategy_simulations(id,strategy_id,data_json,created_at) VALUES(?,?,?,?)",
            (simulation.id, simulation.strategy_id,
             json.dumps(simulation.as_dict(), ensure_ascii=False), simulation.created_at),
        )
        self.connection.commit()

    def get_simulation(self, simulation_id: str) -> OrganizationStrategySimulation | None:
        row = self.connection.execute("SELECT * FROM org_strategy_simulations WHERE id=?", (simulation_id,)).fetchone()
        if row is None:
            return None
        value = json.loads(row["data_json"])
        return OrganizationStrategySimulation(
            strategy_id=value["strategy_id"], strategy_type=value["strategy_type"],
            predictions=value.get("predictions", {}), id=value["simulation_id"],
            created_at=value.get("createdAt", ""),
        )

    def list_simulations(self, strategy_id: str | None = None, limit: int = 100) -> list[OrganizationStrategySimulation]:
        if strategy_id:
            rows = self.connection.execute(
                "SELECT * FROM org_strategy_simulations WHERE strategy_id=? ORDER BY created_at DESC LIMIT ?",
                (strategy_id, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM org_strategy_simulations ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        output: list[OrganizationStrategySimulation] = []
        for row in rows:
            value = json.loads(row["data_json"])
            output.append(OrganizationStrategySimulation(
                strategy_id=value["strategy_id"], strategy_type=value["strategy_type"],
                predictions=value.get("predictions", {}), id=value["simulation_id"],
                created_at=value.get("createdAt", ""),
            ))
        return output

    # -- recommendations ----------------------------------------------------

    def save_recommendation(self, recommendation: StrategicRecommendation) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_recommendations(id,data_json,created_at) VALUES(?,?,?)",
            (recommendation.id, json.dumps(recommendation.as_dict(), ensure_ascii=False), recommendation.created_at),
        )
        self.connection.commit()

    def list_recommendations(self, limit: int = 100) -> list[StrategicRecommendation]:
        rows = self.connection.execute(
            "SELECT * FROM org_recommendations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        output: list[StrategicRecommendation] = []
        for row in rows:
            value = json.loads(row["data_json"])
            output.append(StrategicRecommendation(
                problem=value["problem"],
                evidence=value.get("evidence", []),
                recommendation=value.get("recommendation", ""),
                expected_benefit=value.get("expected_benefit", ""),
                risk=value.get("risk", "low"),
                confidence=float(value.get("confidence", 0)),
                affected_projects=value.get("affected_projects", []),
                affected_teams=value.get("affected_teams", []),
                alternatives=value.get("alternatives", []),
                id=value["recommendation_id"],
                created_at=value.get("createdAt", ""),
            ))
        return output

    # -- impact / risk reports ----------------------------------------------

    def save_impact(self, report: OrganizationImpactReport) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_impact_reports(id,source_node,data_json,created_at) VALUES(?,?,?,?)",
            (report.id, report.source_node, json.dumps(report.as_dict(), ensure_ascii=False), report.created_at),
        )
        self.connection.commit()

    def list_impacts(self, limit: int = 50) -> list[OrganizationImpactReport]:
        rows = self.connection.execute(
            "SELECT * FROM org_impact_reports ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._impact(row) for row in rows if row is not None]

    @staticmethod
    def _impact(row: sqlite3.Row) -> OrganizationImpactReport:
        value = json.loads(row["data_json"])
        return OrganizationImpactReport(
            source_node=value["source_node"],
            affected_projects=value.get("affected_projects", []),
            affected_teams=value.get("affected_teams", []),
            affected_services=value.get("affected_services", []),
            dependency_paths=value.get("dependency_paths", []),
            risk_level=value.get("risk_level", "low"),
            impact_score=int(value.get("impact_score", 0)),
            confidence=float(value.get("confidence", 0)),
            blocking_issues=value.get("blocking_issues", []),
            id=value["id"],
            created_at=value.get("createdAt", ""),
        )

    def save_risk(self, report: OrganizationRiskReport) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO org_risk_reports(id,source,data_json,created_at) VALUES(?,?,?,?)",
            (report.id, report.source, json.dumps(report.as_dict(), ensure_ascii=False), report.created_at),
        )
        self.connection.commit()

    def list_risks(self, limit: int = 50) -> list[OrganizationRiskReport]:
        rows = self.connection.execute(
            "SELECT * FROM org_risk_reports ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        output: list[OrganizationRiskReport] = []
        for row in rows:
            value = json.loads(row["data_json"])
            output.append(OrganizationRiskReport(
                source=value["source"],
                severity=value.get("severity", "low"),
                likelihood=value.get("likelihood", "low"),
                propagation_path=value.get("propagation_path", []),
                affected_nodes=value.get("affected_nodes", []),
                affected_projects=value.get("affected_projects", []),
                affected_teams=value.get("affected_teams", []),
                affected_services=value.get("affected_services", []),
                impact=value.get("impact", "low"),
                confidence=float(value.get("confidence", 0)),
                recommendations=value.get("recommendations", []),
                id=value["risk_id"],
                created_at=value.get("createdAt", ""),
            ))
        return output
