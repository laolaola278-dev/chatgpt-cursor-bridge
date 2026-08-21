"""Organization Strategy Manager (Phase 24).

Facade that wires the impact analyzer, risk engine, strategy generator and
evaluator, decision manager, simulation adapter, recommendation engine and
organization memory together. Write entry points are only invoked from the
approved execution path (_execute_action); read-only analysis never modifies
graph, projects or memory. Approved writes also sync strategy metadata into
the Phase 23 organization graph as non-hierarchical nodes/edges.
"""

from __future__ import annotations

from typing import Any

from app.audit.logger import AuditLogger
from app.config import Settings
from app.governance.storage import GovernanceStorage
from app.organization.storage import OrganizationStorage
from app.organization_graph.models import EdgeType, GraphNode, OrgEdge
from app.organization_graph.storage import OrganizationGraphStorage
from app.security.validator import ResourceNotFound, ValidationFailed

from .analyzer import OrganizationImpactAnalyzer
from .decision import OrganizationDecisionManager
from .memory import OrganizationMemory
from .models import (
    EngineeringStrategy,
    OrganizationStrategySimulation,
    StrategicRecommendation,
    StrategyStatus,
    StrategyType,
)
from .recommendation import OrganizationRecommendationEngine
from .risk import OrganizationRiskEngine
from .simulation import OrganizationSimulationAdapter
from .storage import OrganizationStrategyStorage
from .strategy import OrganizationStrategyEvaluator, OrganizationStrategyGenerator

_STRATEGY_NODE_TYPE = "ORGANIZATION_STRATEGY"
_DECISION_NODE_TYPE = "ORGANIZATION_DECISION"
_SIMULATION_NODE_TYPE = "STRATEGY_SIMULATION"
_RISK_NODE_TYPE = "ORGANIZATION_RISK"


class OrganizationStrategyManager:
    def __init__(self, settings: Settings, audit: AuditLogger | None = None) -> None:
        self.settings = settings
        self.audit = audit
        self.storage = OrganizationStrategyStorage(settings.organization_strategy_db_path)
        self.graph = OrganizationGraphStorage(settings.organization_graph_db_path)
        self.org = OrganizationStorage(settings.organization_db_path)
        self.governance = GovernanceStorage(settings.governance_db_path)
        self.memory = OrganizationMemory(settings)
        self.impact_analyzer = OrganizationImpactAnalyzer(self.graph)
        self.risk_engine = OrganizationRiskEngine(self.graph)
        self.generator = OrganizationStrategyGenerator()
        self.evaluator = OrganizationStrategyEvaluator()
        self.decision_manager = OrganizationDecisionManager(self.storage)
        self.simulator = OrganizationSimulationAdapter()
        self.recommendations_engine = OrganizationRecommendationEngine()

    # ------------------------------------------------------------------ #
    # Read-only analysis
    # ------------------------------------------------------------------ #

    def impact(self, node_id: str) -> dict[str, Any]:
        report = self.impact_analyzer.analyze(node_id)
        self.storage.save_impact(report)
        return report.as_dict()

    def risk(self, node_id: str, *, severity: str = "medium", likelihood: str = "medium") -> dict[str, Any]:
        report = self.risk_engine.propagate(node_id, severity=severity, likelihood=likelihood)
        self.storage.save_risk(report)
        self._sync_graph_node(_RISK_NODE_TYPE, report.id, f"risk:{node_id}", {})
        return report.as_dict()

    def strategies(self, project: str | None = None) -> list[dict[str, Any]]:
        return [strategy.as_dict() for strategy in self.storage.list_strategies(project)]

    def strategy(self, strategy_id: str) -> dict[str, Any]:
        strategy = self.storage.get_strategy(strategy_id)
        if strategy is None:
            raise ResourceNotFound(f"Strategy '{strategy_id}' was not found")
        return strategy.as_dict()

    def evaluations(self, strategy_id: str | None = None) -> list[dict[str, Any]]:
        return [evaluation.as_dict() for evaluation in self.storage.list_evaluations(strategy_id)]

    def decision(self, decision_id: str) -> dict[str, Any]:
        return self.decision_manager.get(decision_id).as_dict()

    def decisions(self, status: str | None = None) -> list[dict[str, Any]]:
        return [decision.as_dict() for decision in self.storage.list_decisions(status)]

    def simulation(self, simulation_id: str) -> dict[str, Any]:
        simulation = self.storage.get_simulation(simulation_id)
        if simulation is None:
            raise ResourceNotFound(f"Strategy simulation '{simulation_id}' was not found")
        return simulation.as_dict()

    def recommendations(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.storage.list_recommendations()]

    def generate_candidates(self) -> list[EngineeringStrategy]:
        """Deterministic candidate generation from real persisted signals."""
        projects = self._project_names()
        healths = [self._latest_health(project) for project in projects]
        healths = [health for health in healths if health is not None]
        debts = {project: [item.as_dict() for item in self.governance.list_debt(project)] for project in projects}
        drifts = {project: self.governance.list_drift(project) for project in projects}
        failure_patterns = [pattern.as_dict() for pattern in self.org.list_failure_patterns()]
        incidents = [incident.as_dict() for incident in self.org.list_incidents()]
        teams_by_project = self._teams_by_project()
        return self.generator.generate(
            healths=healths, debts=debts, drifts=drifts,
            failure_patterns=failure_patterns, incidents=incidents,
            teams_by_project=teams_by_project,
        )

    def build_recommendations(self) -> list[StrategicRecommendation]:
        risks = [risk.as_dict() for risk in self.storage.list_risks()]
        impacts = [impact.as_dict() for impact in self.storage.list_impacts()]
        simulations = [simulation.as_dict() for simulation in self.storage.list_simulations()]
        projects = self._project_names()
        debts = {project: [item.as_dict() for item in self.governance.list_debt(project)] for project in projects}
        drifts = {project: self.governance.list_drift(project) for project in projects}
        healths = [health for project in projects if (health := self._latest_health(project)) is not None]
        return self.recommendations_engine.build(
            healths=healths, risks=risks, impacts=impacts, debts=debts,
            drifts=drifts, simulations=simulations,
            teams_by_project=self._teams_by_project(),
        )

    def org_context(self) -> dict[str, Any]:
        nodes = [node.as_dict() for node in self.graph.list_nodes()]
        edges = [edge.as_dict() for edge in self.graph.list_edges()]
        projects = self._project_names()
        debt = {
            project: [item.as_dict() for item in self.governance.list_debt(project) if item.status.value == "OPEN"]
            for project in projects
        }
        drift = {project: self.governance.list_drift(project) for project in projects}
        return {
            "organization": "organization",
            "graph": {"nodes": nodes, "edges": edges, "readOnly": True},
            "organization_health": [health for project in projects if (health := self._latest_health(project)) is not None],
            "active_risks": [risk.as_dict() for risk in self.storage.list_risks()],
            "cross_project_impacts": [impact.as_dict() for impact in self.storage.list_impacts()],
            "active_strategies": [strategy.as_dict() for strategy in self.storage.list_strategies() if strategy.status.value != "SELECTED"],
            "pending_decisions": [decision.as_dict() for decision in self.storage.list_decisions() if decision.status.value in ("PROPOSED", "ANALYZING", "REVIEW_REQUIRED", "APPROVAL_REQUIRED")],
            "technical_debt": debt,
            "architecture_drift": drift,
            "recommendations": [item.as_dict() for item in self.storage.list_recommendations()],
            "readOnly": True,
        }

    # ------------------------------------------------------------------ #
    # Approved writes (only called from _execute_action after approval)
    # ------------------------------------------------------------------ #

    def create_strategy(self, payload: dict[str, Any]) -> dict[str, Any]:
        strategy_type = (payload.get("strategy_type") or "").strip().upper()
        try:
            strategy_type = StrategyType(strategy_type)
        except ValueError as exc:
            raise ValidationFailed(f"Unknown strategy type '{payload.get('strategy_type')}'") from exc
        title = (payload.get("title") or "").strip()
        problem = (payload.get("problem") or "").strip()
        if not title or not problem:
            raise ValidationFailed("Strategy title and problem are required")
        strategy = EngineeringStrategy(
            strategy_type=strategy_type,
            title=title,
            problem=problem,
            affected_projects=list(payload.get("affected_projects", [])),
            affected_teams=list(payload.get("affected_teams", [])),
            benefits=list(payload.get("benefits", [])),
            risks=list(payload.get("risks", [])),
            estimated_effort=str(payload.get("estimated_effort", "")),
            confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.5)))),
            priority=str(payload.get("priority", "medium")),
            alternatives=list(payload.get("alternatives", [])),
            evidence=list(payload.get("evidence", [])),
        )
        self.storage.save_strategy(strategy)
        self._sync_strategy_graph(strategy)
        return strategy.as_dict()

    def evaluate_strategies(self, strategy_ids: list[str]) -> dict[str, Any]:
        if not strategy_ids:
            raise ValidationFailed("At least one strategy id is required")
        strategies: list[EngineeringStrategy] = []
        for strategy_id in strategy_ids:
            strategy = self.storage.get_strategy(strategy_id)
            if strategy is None:
                raise ResourceNotFound(f"Strategy '{strategy_id}' was not found")
            strategies.append(strategy)
        evaluations = self.evaluator.evaluate(strategies)
        for evaluation in evaluations:
            self.storage.save_evaluation(evaluation)
        simulations: list[OrganizationStrategySimulation] = []
        for strategy in strategies:
            strategy.transition("EVALUATED")
            self.storage.save_strategy(strategy)
            simulation = self.simulator.simulate(strategy)
            self.storage.save_simulation(simulation)
            simulations.append(simulation)
            self._sync_simulation_graph(strategy, simulation)
        return {
            "evaluations": [evaluation.as_dict() for evaluation in evaluations],
            "simulations": [simulation.as_dict() for simulation in simulations],
            "strategies": [strategy.as_dict() for strategy in strategies],
            "readOnly": True,
        }

    def create_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        strategy_id = payload.get("strategy_id") or payload.get("selected_strategy") or ""
        strategy = self.storage.get_strategy(strategy_id) if strategy_id else None
        if strategy is None:
            raise ResourceNotFound(f"Strategy '{strategy_id}' was not found")
        decision = self.decision_manager.create(
            organization_id=payload.get("organization_id", "organization"),
            title=payload.get("title") or f"Adopt {strategy.title}",
            source_graph_nodes=list(payload.get("source_graph_nodes", [])),
            selected_strategy=strategy_id,
            alternatives=list(payload.get("alternatives", [])) or strategy.alternatives,
            confidence=float(payload.get("confidence", strategy.confidence)),
            impact_report=payload.get("impact_report", {}),
            risk_report=payload.get("risk_report", {}),
        )
        # A decision selects the strategy: walk the strict state machine
        # (PROPOSED -> EVALUATED -> SELECTED); already-evaluated strategies
        # only need the final step.
        if strategy.status is StrategyStatus.PROPOSED:
            strategy.transition("EVALUATED")
            self.storage.save_strategy(strategy)
        if strategy.status is not StrategyStatus.SELECTED:
            strategy.transition("SELECTED")
            self.storage.save_strategy(strategy)
        self._sync_decision_graph(decision, strategy)
        return decision.as_dict()

    def transition_decision(self, decision_id: str, status: str) -> dict[str, Any]:
        decision = self.decision_manager.transition(decision_id, status)
        if decision.status.value == "SUPERSEDED" and decision.selected_strategy:
            strategy = self.storage.get_strategy(decision.selected_strategy)
            if strategy is not None:
                self._sync_edge(decision.id, strategy.id, EdgeType.SUPERSEDES)
        return decision.as_dict()

    def append_memory(self, org: str, category: str, content: str) -> dict[str, Any]:
        return self.memory.append_after_approval(org, category, content)

    # ------------------------------------------------------------------ #
    # Graph integration helpers
    # ------------------------------------------------------------------ #

    def _sync_strategy_graph(self, strategy: EngineeringStrategy) -> None:
        self._sync_graph_node(_STRATEGY_NODE_TYPE, strategy.id, strategy.title, {
            "strategyType": strategy.strategy_type.value, "priority": strategy.priority,
        })
        for project in strategy.affected_projects:
            for node_id in self._node_ids_by_name("PROJECT", project):
                self._sync_edge(strategy.id, node_id, EdgeType.AFFECTS)

    def _sync_simulation_graph(self, strategy: EngineeringStrategy, simulation: OrganizationStrategySimulation) -> None:
        self._sync_graph_node(_SIMULATION_NODE_TYPE, simulation.id, f"simulation:{strategy.id}", simulation.predictions)
        self._sync_edge(strategy.id, simulation.id, EdgeType.EVALUATED_BY)

    def _sync_decision_graph(self, decision, strategy: EngineeringStrategy) -> None:
        self._sync_graph_node(_DECISION_NODE_TYPE, decision.id, decision.title, {
            "status": decision.status.value, "selectedStrategy": strategy.id,
        })
        if strategy.id:
            self._sync_edge(decision.id, strategy.id, EdgeType.IMPLEMENTED_BY)
        for node_id in decision.source_graph_nodes:
            self._sync_edge(decision.id, node_id, EdgeType.INFLUENCES)

    def _sync_graph_node(self, node_type: str, node_id: str, label: str, metadata: dict[str, Any]) -> None:
        self.graph.save_node(GraphNode(id=node_id, type=node_type, name=label, metadata=metadata))

    def _sync_edge(self, source: str, target: str, relation: EdgeType) -> None:
        if source and target and source != target:
            self.graph.save_edge(OrgEdge(source=source, target=target, relation=relation))

    def _node_ids_by_name(self, node_type: str, name: str) -> list[str]:
        return [
            node.id for node in self.graph.list_nodes()
            if node.type == node_type and node.name == name
        ]

    # ------------------------------------------------------------------ #
    # Signal helpers (real persisted data)
    # ------------------------------------------------------------------ #

    def _project_names(self) -> list[str]:
        return [entity.name for entity in self.org.list_entities("PROJECT")]

    def _teams_by_project(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for project in self.org.list_entities("PROJECT"):
            if project.parent_id:
                team = self.org.get_entity(project.parent_id)
                if team is not None:
                    mapping[project.name] = team.name
        return mapping

    def _latest_health(self, project: str) -> dict[str, Any] | None:
        snapshots = self.governance.list_health(project, limit=1)
        if snapshots:
            return snapshots[0]
        snapshots = self.org.list_health(project, limit=1)
        return snapshots[0] if snapshots else None
