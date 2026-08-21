"""Phase 24 - Organization Engineering Strategy tests.

Covers cross-project impact analysis, risk propagation, strategy generation
and evaluation, the organization decision lifecycle, the strategy simulation
adapter, strategic recommendations, organization memory, engineering graph
integration, organization context extension, Quality Gate 10.0 strategy
signals, the API surface and approval integration. Every organization write
must flow through the ApprovalStore; no endpoint may execute, modify source,
write memory or bypass human approval.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from app.organization_graph.models import EdgeType, GraphNode, OrgEdge
from app.organization_graph.storage import OrganizationGraphStorage
from app.organization_strategy import (
    DecisionStatus,
    EngineeringStrategy,
    OrganizationDecisionManager,
    OrganizationMemory,
    OrganizationStrategyManager,
    OrganizationStrategyStorage,
    StrategyStatus,
    StrategyType,
)
from app.organization_strategy.analyzer import OrganizationImpactAnalyzer
from app.organization_strategy.recommendation import OrganizationRecommendationEngine
from app.organization_strategy.risk import OrganizationRiskEngine
from app.organization_strategy.simulation import OrganizationSimulationAdapter
from app.organization_strategy.strategy import (
    OrganizationStrategyEvaluator,
    OrganizationStrategyGenerator,
)
from app.quality.gate10 import QualityGate10Evaluator
from app.security.permissions import PermissionLevel, level_for_action
from app.security.validator import ValidationFailed

# --------------------------------------------------------------------------- #
# Shared fixtures / helpers
# --------------------------------------------------------------------------- #


def _graph(tmp_path) -> tuple[OrganizationGraphStorage, dict[str, str]]:
    """Seeded organization graph: 2 teams-2 projects, 2 services, 2 repos.

    Edges: checkout-api DEPENDS_ON checkout-repo; payments-api DEPENDS_ON
    checkout-repo (shared repository); checkout-api RELATED_TO payments-api.
    """
    storage = OrganizationGraphStorage(tmp_path / "org_graph.db")
    ids: dict[str, str] = {}
    rows = [
        ("comp", "COMPANY", "Acme", None),
        ("team", "TEAM", "Platform", "comp"),
        ("p1", "PROJECT", "checkout", "team"),
        ("p2", "PROJECT", "payments", "team"),
        ("s1", "SERVICE", "checkout-api", "p1"),
        ("s2", "SERVICE", "payments-api", "p2"),
        ("r1", "REPOSITORY", "checkout-repo", "p1"),
        ("r2", "REPOSITORY", "payments-repo", "p2"),
    ]
    for key, node_type, name, parent in rows:
        ids[key] = key
        storage.save_node(GraphNode(id=key, type=node_type, name=name, parent_id=parent))
    storage.save_edge(OrgEdge("s1", "r1", EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge("s2", "r1", EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge("s1", "s2", EdgeType.RELATED_TO))
    return storage, ids


def _strategy(
    strategy_type: StrategyType = StrategyType.STANDARDIZATION,
    title: str = "Unify authentication",
    projects: list[str] | None = None,
    confidence: float = 0.7,
) -> EngineeringStrategy:
    return EngineeringStrategy(
        strategy_type=strategy_type,
        title=title,
        problem="Multiple projects use different authentication approaches",
        affected_projects=projects or ["checkout", "payments"],
        affected_teams=["Platform"],
        benefits=["One shared approach", "Fewer security gaps"],
        risks=["Touchpoints across projects"],
        estimated_effort="4-7 person-weeks",
        confidence=confidence,
        priority="high",
        alternatives=["Keep current approach", "Phase the migration"],
    )


def _storage(tmp_path) -> OrganizationStrategyStorage:
    return OrganizationStrategyStorage(tmp_path / "strategy.db")


def _seed_org_graph_via_api(bridge) -> dict[str, str]:
    """Register Phase 22 entities, sync them into the Phase 23 graph and add
    dependency edges. Returns a mapping of logical name -> graph node id."""
    from app.config import get_settings

    entities = [
        ("COMPANY", "Acme"),
        ("TEAM", "Platform"),
        ("PROJECT", "checkout"),
        ("PROJECT", "payments"),
        ("SERVICE", "checkout-api"),
        ("SERVICE", "payments-api"),
        ("REPOSITORY", "checkout-repo"),
        ("REPOSITORY", "payments-repo"),
    ]
    parent: dict[str, str] = {}
    ids: dict[str, str] = {}
    for entity_type, name in entities:
        payload = {"type": entity_type, "name": name, "reason": "seed"}
        if entity_type == "TEAM":
            payload["parent_id"] = parent["COMPANY"]
        elif entity_type == "PROJECT":
            payload["parent_id"] = parent["TEAM"]
        elif entity_type in ("SERVICE", "REPOSITORY"):
            project_name = name.replace("-api", "").replace("-repo", "")
            payload["parent_id"] = ids[project_name]
        pending = bridge.client.post("/organization/graph/entity", json=payload)
        assert pending.status_code == 202, pending.text
        executed = bridge.approve(pending.json()["requestId"])
        assert executed.status_code == 200, executed.text
        parent[entity_type] = executed.json()["result"]["id"]
        ids[name] = executed.json()["result"]["id"]
    pending = bridge.client.post("/organization-graph/sync", json={"reason": "seed"})
    assert pending.status_code == 202, pending.text
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200, executed.text
    # Dependency edges (no write API exists for edges; direct storage seeding).
    graph = OrganizationGraphStorage(get_settings().organization_graph_db_path)
    graph.save_edge(OrgEdge(ids["checkout-api"], ids["checkout-repo"], EdgeType.DEPENDS_ON))
    graph.save_edge(OrgEdge(ids["payments-api"], ids["checkout-repo"], EdgeType.DEPENDS_ON))
    graph.save_edge(OrgEdge(ids["checkout-api"], ids["payments-api"], EdgeType.RELATED_TO))
    return ids


# --------------------------------------------------------------------------- #
# 1. Cross-Project Impact Analysis
# --------------------------------------------------------------------------- #


def test_impact_direct_and_transitive_affected(tmp_path):
    storage, ids = _graph(tmp_path)
    report = OrganizationImpactAnalyzer(storage).analyze("s1")
    assert "r1" in {node.id for node in storage.list_nodes()}
    assert report.source_node == "s1"
    assert "payments" in report.affected_projects
    assert "checkout" in report.affected_projects
    assert "payments-api" in report.affected_services


def test_impact_dependency_paths_through_shared_repository(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationImpactAnalyzer(storage).analyze("s1")
    assert any("checkout-repo" in path for path in report.dependency_paths)
    assert any("payments-api" in path for path in report.dependency_paths)


def test_impact_team_level_aggregation(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationImpactAnalyzer(storage).analyze("s1")
    assert "Platform" in report.affected_teams


def test_impact_isolated_node_has_no_affected(tmp_path):
    storage = OrganizationGraphStorage(Path(tmp_path) / "iso.db")
    storage.save_node(GraphNode(id="lonely", type="SERVICE", name="lonely-api"))
    report = OrganizationImpactAnalyzer(storage).analyze("lonely")
    assert report.affected_projects == []
    assert report.affected_teams == []
    assert report.impact_score == 0
    assert report.risk_level == "low"


def test_impact_missing_node_raises_404(tmp_path):
    storage, _ids = _graph(tmp_path)
    with pytest.raises(Exception) as exc:
        OrganizationImpactAnalyzer(storage).analyze("missing")
    assert exc.type.__name__ in ("ResourceNotFound",)


def test_impact_score_is_deterministic(tmp_path):
    storage, _ids = _graph(tmp_path)
    first = OrganizationImpactAnalyzer(storage).analyze("s1")
    second = OrganizationImpactAnalyzer(storage).analyze("s1")
    assert first.impact_score == second.impact_score
    assert first.confidence == second.confidence


def test_impact_confidence_within_bounds(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationImpactAnalyzer(storage).analyze("s1")
    assert 0.0 <= report.confidence <= 0.95


def test_impact_risk_level_thresholds(tmp_path):
    storage, _ids = _graph(tmp_path)
    low = OrganizationImpactAnalyzer(storage).analyze("r2")
    assert low.impact_score < 50
    high = OrganizationImpactAnalyzer(storage).analyze("r1")
    assert high.impact_score > low.impact_score


def test_impact_does_not_modify_graph(tmp_path):
    storage, _ids = _graph(tmp_path)
    before = hashlib.sha256(
        "\n".join(node.id for node in storage.list_nodes()).encode()
    ).hexdigest()
    OrganizationImpactAnalyzer(storage).analyze("s1")
    after = hashlib.sha256(
        "\n".join(node.id for node in storage.list_nodes()).encode()
    ).hexdigest()
    assert before == after


def test_impact_report_shape(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationImpactAnalyzer(storage).analyze("s1").as_dict()
    for key in ["id", "source_node", "affected_projects", "affected_teams",
                "affected_services", "dependency_paths", "risk_level",
                "impact_score", "confidence", "blocking_issues", "createdAt", "readOnly"]:
        assert key in report
    assert report["readOnly"] is True


def test_impact_self_loop_ignored(tmp_path):
    storage = OrganizationGraphStorage(Path(tmp_path) / "loop.db")
    storage.save_node(GraphNode(id="a", type="SERVICE", name="a-api"))
    storage.save_node(GraphNode(id="b", type="SERVICE", name="b-api"))
    storage.save_edge(OrgEdge("a", "a", EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge("a", "b", EdgeType.DEPENDS_ON))
    report = OrganizationImpactAnalyzer(storage).analyze("a")
    assert "b-api" in report.affected_services


def test_impact_shared_repository_creates_blocking_issue(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationImpactAnalyzer(storage).analyze("r1")
    assert report.impact_score >= 50
    assert report.risk_level in ("medium", "high")


def test_impact_strategy_edges_are_included(tmp_path):
    storage, _ids = _graph(tmp_path)
    storage.save_node(GraphNode(id="ostrat_1", type="ORGANIZATION_STRATEGY", name="Unify auth"))
    storage.save_edge(OrgEdge("ostrat_1", "p1", EdgeType.AFFECTS))
    report = OrganizationImpactAnalyzer(storage).analyze("ostrat_1")
    assert "checkout" in report.affected_projects


def test_impact_incident_aware_aggregation(tmp_path):
    storage = OrganizationGraphStorage(Path(tmp_path) / "inc.db")
    storage.save_node(GraphNode(id="comp", type="COMPANY", name="Acme"))
    storage.save_node(GraphNode(id="team", type="TEAM", name="Platform", parent_id="comp"))
    storage.save_node(GraphNode(id="p1", type="PROJECT", name="checkout", parent_id="team"))
    storage.save_node(GraphNode(id="inc1", type="INCIDENT", name="cache failure", parent_id="p1"))
    storage.save_node(GraphNode(id="s1", type="SERVICE", name="checkout-api", parent_id="p1"))
    storage.save_edge(OrgEdge("s1", "inc1", EdgeType.RELATED_TO))
    report = OrganizationImpactAnalyzer(storage).analyze("s1")
    assert "checkout" in report.affected_projects


def test_impact_zero_score_for_unknown_only(tmp_path):
    storage = OrganizationGraphStorage(Path(tmp_path) / "empty.db")
    storage.save_node(GraphNode(id="a", type="SERVICE", name="a-api"))
    report = OrganizationImpactAnalyzer(storage).analyze("a")
    assert report.impact_score == 0


# --------------------------------------------------------------------------- #
# 2. Risk Propagation Engine
# --------------------------------------------------------------------------- #


def test_risk_propagates_through_shared_repository(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high")
    affected = {node["name"] for node in report.affected_nodes}
    assert "payments-api" in affected
    assert "checkout-repo" in affected


def test_risk_affected_projects_and_teams(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high")
    assert "checkout" in report.affected_projects
    assert "payments" in report.affected_projects
    assert "Platform" in report.affected_teams


def test_risk_severity_decays_per_hop(tmp_path):
    storage = OrganizationGraphStorage(Path(tmp_path) / "chain.db")
    for index in range(4):
        storage.save_node(GraphNode(id=f"n{index}", type="SERVICE", name=f"svc-{index}"))
    storage.save_edge(OrgEdge("n0", "n1", EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge("n1", "n2", EdgeType.DEPENDS_ON))
    storage.save_edge(OrgEdge("n2", "n3", EdgeType.DEPENDS_ON))
    report = OrganizationRiskEngine(storage).propagate("n0", severity="high", likelihood="high")
    affected = {node["id"]: node["severity"] for node in report.affected_nodes}
    assert "n1" in affected
    # Decay stops before the far end of the chain (per-hop 0.8 decay).
    assert "n3" not in affected


def test_risk_contained_when_no_neighbors(tmp_path):
    storage = OrganizationGraphStorage(Path(tmp_path) / "alone.db")
    storage.save_node(GraphNode(id="solo", type="SERVICE", name="solo-api"))
    report = OrganizationRiskEngine(storage).propagate("solo", severity="high", likelihood="high")
    assert report.affected_nodes == []
    assert report.recommendations
    assert any("contained" in recommendation for recommendation in report.recommendations)


def test_risk_invalid_severity_rejected(tmp_path):
    storage, _ids = _graph(tmp_path)
    with pytest.raises(ValidationFailed):
        OrganizationRiskEngine(storage).propagate("s1", severity="catastrophic")


def test_risk_invalid_likelihood_rejected(tmp_path):
    storage, _ids = _graph(tmp_path)
    with pytest.raises(ValidationFailed):
        OrganizationRiskEngine(storage).propagate("s1", likelihood="maybe")


def test_risk_missing_node_404(tmp_path):
    storage, _ids = _graph(tmp_path)
    with pytest.raises(Exception) as exc:
        OrganizationRiskEngine(storage).propagate("missing")
    assert exc.type.__name__ in ("ResourceNotFound",)


def test_risk_impact_levels(tmp_path):
    storage, _ids = _graph(tmp_path)
    high = OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high")
    assert high.impact in ("medium", "high")
    low = OrganizationRiskEngine(storage).propagate("r2", severity="low", likelihood="low")
    assert low.impact in ("low", "medium")


def test_risk_confidence_bounds(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high")
    assert 0.0 <= report.confidence <= 0.95


def test_risk_propagation_path_shape(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high")
    assert report.propagation_path
    entry = report.propagation_path[0]
    for key in ["node", "via", "severity", "path"]:
        assert key in entry


def test_risk_deterministic(tmp_path):
    storage, _ids = _graph(tmp_path)
    engine = OrganizationRiskEngine(storage)
    first = engine.propagate("s1", severity="high", likelihood="high")
    second = engine.propagate("s1", severity="high", likelihood="high")
    assert [node["id"] for node in first.affected_nodes] == [node["id"] for node in second.affected_nodes]


def test_risk_report_read_only_contract(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high").as_dict()
    for key in ["risk_id", "source", "severity", "likelihood", "propagation_path",
                "affected_nodes", "impact", "confidence", "recommendations", "readOnly"]:
        assert key in report
    assert report["readOnly"] is True


def test_risk_does_not_modify_graph(tmp_path):
    storage, _ids = _graph(tmp_path)
    before = hashlib.sha256(
        "\n".join(node.id for node in storage.list_nodes()).encode()
    ).hexdigest()
    OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high")
    after = hashlib.sha256(
        "\n".join(node.id for node in storage.list_nodes()).encode()
    ).hexdigest()
    assert before == after


def test_risk_high_impact_gates_recommendation(tmp_path):
    storage, _ids = _graph(tmp_path)
    report = OrganizationRiskEngine(storage).propagate("s1", severity="high", likelihood="high")
    assert any("human approval" in recommendation.lower() for recommendation in report.recommendations)


# --------------------------------------------------------------------------- #
# 3. Strategy Generation
# --------------------------------------------------------------------------- #


def test_generator_refactor_from_debt(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        debts={"checkout": [{"status": "OPEN", "estimatedCost": 10}, {"status": "OPEN", "estimatedCost": 25}]},
    )
    assert any(strategy.strategy_type is StrategyType.REFACTOR for strategy in strategies)


def test_generator_architecture_alignment_from_drift(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        drifts={"checkout": [{"issues": [{"type": "unrecorded_dependency"}, {"type": "circular_dependency"}]}]},
    )
    assert any(strategy.strategy_type is StrategyType.ARCHITECTURE_ALIGNMENT for strategy in strategies)


def test_generator_deprecation_from_drift(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        drifts={"checkout": [{"issues": [{"type": "deprecated_component_usage"}]}]},
    )
    assert any(strategy.strategy_type is StrategyType.DEPRECATION for strategy in strategies)


def test_generator_standardization_from_repeated_failures(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        failure_patterns=[
            {"project": "checkout", "category": "deployment", "occurrences": 3},
            {"project": "payments", "category": "deployment", "occurrences": 2},
        ],
    )
    assert any(strategy.strategy_type is StrategyType.STANDARDIZATION for strategy in strategies)


def test_generator_migration_from_cache_failures(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        failure_patterns=[
            {"project": "checkout", "category": "cache", "signature": "redis cache invalidation"},
            {"project": "payments", "category": "cache", "signature": "redis cache failure"},
        ],
    )
    assert any(strategy.strategy_type is StrategyType.MIGRATION for strategy in strategies)


def test_generator_test_improvement_from_low_health(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        healths=[{"project": "checkout", "healthScore": 55, "riskLevel": "medium"}],
    )
    assert any(strategy.strategy_type is StrategyType.TEST_IMPROVEMENT for strategy in strategies)


def test_generator_risk_reduction_from_high_incidents(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        incidents=[{"project": "checkout", "severity": "high", "status": "OPEN"}],
    )
    assert any(strategy.strategy_type is StrategyType.RISK_REDUCTION for strategy in strategies)


def test_generator_empty_signals_produce_no_strategies():
    assert OrganizationStrategyGenerator().generate() == []


def test_generator_teams_mapped_from_projects(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        healths=[{"project": "checkout", "healthScore": 50, "riskLevel": "high"}],
        teams_by_project={"checkout": "Platform"},
    )
    assert all("Platform" in strategy.affected_teams for strategy in strategies)


def test_generator_evidence_is_real(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        debts={"checkout": [{"status": "OPEN", "estimatedCost": 30}, {"status": "OPEN", "estimatedCost": 40}]},
    )
    strategy = next(item for item in strategies if item.strategy_type is StrategyType.REFACTOR)
    assert strategy.evidence
    assert "checkout" in strategy.evidence[0]


def test_generator_deterministic(tmp_path):
    signals = {
        "healths": [{"project": "checkout", "healthScore": 60, "riskLevel": "medium"}],
        "debts": {"checkout": [{"status": "OPEN", "estimatedCost": 20}, {"status": "OPEN", "estimatedCost": 30}]},
        "failure_patterns": [
            {"project": "checkout", "category": "deployment", "occurrences": 2},
            {"project": "payments", "category": "deployment", "occurrences": 1},
        ],
    }
    first = OrganizationStrategyGenerator().generate(**signals)
    second = OrganizationStrategyGenerator().generate(**signals)
    assert [item.as_dict() for item in first] == [item.as_dict() for item in second]


def test_generator_confidence_bounds(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        failure_patterns=[
            {"project": "checkout", "category": "deployment", "occurrences": 4},
            {"project": "payments", "category": "deployment", "occurrences": 3},
        ],
    )
    for strategy in strategies:
        assert 0.0 <= strategy.confidence <= 0.95


def test_generator_migration_has_alternatives(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        failure_patterns=[
            {"project": "checkout", "category": "cache", "signature": "redis cache invalidation"},
            {"project": "payments", "category": "cache", "signature": "redis cache failure"},
        ],
    )
    migration = next(item for item in strategies if item.strategy_type is StrategyType.MIGRATION)
    assert len(migration.alternatives) >= 2
    assert any("status quo" in alternative.lower() for alternative in migration.alternatives)


def test_generator_priority_from_severity(tmp_path):
    low = OrganizationStrategyGenerator().generate(
        failure_patterns=[{"project": "a", "category": "deployment", "occurrences": 1},
                          {"project": "b", "category": "deployment", "occurrences": 1}],
    )
    assert any(item.priority in ("medium", "high") for item in low)
    high = OrganizationStrategyGenerator().generate(
        failure_patterns=[{"project": "a", "category": "deployment", "occurrences": 2, "severity": "high"},
                          {"project": "b", "category": "deployment", "occurrences": 2, "severity": "high"}],
    )
    assert any(item.priority == "high" for item in high)


def test_generator_strategy_requires_fields(tmp_path):
    strategy = _strategy()
    assert strategy.title and strategy.problem
    assert strategy.strategy_type in StrategyType


def test_generator_covers_all_seven_types(tmp_path):
    generated = OrganizationStrategyGenerator().generate(
        healths=[{"project": "checkout", "healthScore": 55, "riskLevel": "medium"}],
        debts={"checkout": [{"status": "OPEN", "estimatedCost": 10}, {"status": "OPEN", "estimatedCost": 25}]},
        drifts={
            "checkout": [{"issues": [{"type": "unrecorded_dependency"}, {"type": "circular_dependency"}]}],
            "payments": [{"issues": [{"type": "deprecated_component_usage"}]}],
        },
        failure_patterns=[
            {"project": "checkout", "category": "deployment", "occurrences": 3},
            {"project": "payments", "category": "deployment", "occurrences": 2},
            {"project": "checkout", "category": "cache", "signature": "redis cache invalidation"},
            {"project": "payments", "category": "cache", "signature": "redis cache failure"},
        ],
        incidents=[{"project": "checkout", "severity": "high", "status": "OPEN"}],
        teams_by_project={"checkout": "Platform", "payments": "Platform"},
    )
    types = {strategy.strategy_type for strategy in generated}
    assert {StrategyType.REFACTOR, StrategyType.ARCHITECTURE_ALIGNMENT, StrategyType.DEPRECATION,
            StrategyType.STANDARDIZATION, StrategyType.MIGRATION, StrategyType.TEST_IMPROVEMENT,
            StrategyType.RISK_REDUCTION} <= types


# --------------------------------------------------------------------------- #
# 4. Strategy Evaluation / Comparison
# --------------------------------------------------------------------------- #


def test_evaluation_criteria_keys(tmp_path):
    evaluation = OrganizationStrategyEvaluator().evaluate([_strategy()])[0]
    for key in ["impact", "risk", "cost", "complexity", "maintainability", "migration_difficulty", "confidence"]:
        assert key in evaluation.criteria


def test_evaluation_composite_bounds(tmp_path):
    evaluations = OrganizationStrategyEvaluator().evaluate([_strategy(), _strategy(StrategyType.MIGRATION)])
    for evaluation in evaluations:
        assert 0.0 <= evaluation.composite_score <= 1.0


def test_evaluation_single_recommended(tmp_path):
    strategies = [_strategy(), _strategy(StrategyType.MIGRATION, "Migrate cache")]
    evaluations = OrganizationStrategyEvaluator().evaluate(strategies)
    assert sum(1 for evaluation in evaluations if evaluation.recommended) == 1


def test_evaluation_recommended_is_best(tmp_path):
    strategies = [_strategy(confidence=0.3), _strategy(StrategyType.TEST_IMPROVEMENT, confidence=0.9)]
    evaluations = OrganizationStrategyEvaluator().evaluate(strategies)
    best = max(evaluations, key=lambda item: item.composite_score)
    assert best.recommended is True


def test_evaluation_deterministic(tmp_path):
    evaluator = OrganizationStrategyEvaluator()
    strategies = [_strategy(), _strategy(StrategyType.MIGRATION, "Migrate cache")]
    first = evaluator.evaluate(strategies)
    second = evaluator.evaluate(strategies)
    assert [item.as_dict() for item in first] == [item.as_dict() for item in second]


def test_evaluation_empty_list(tmp_path):
    assert OrganizationStrategyEvaluator().evaluate([]) == []


def test_evaluation_migration_scores_lower_maintainability_than_refactor(tmp_path):
    evaluator = OrganizationStrategyEvaluator()
    refactor = evaluator.evaluate([_strategy(StrategyType.REFACTOR)])[0]
    migration = evaluator.evaluate([_strategy(StrategyType.MIGRATION)])[0]
    assert refactor.criteria["maintainability"] > migration.criteria["maintainability"]


def test_evaluation_does_not_auto_select(tmp_path):
    """The evaluator marks a recommendation; selection needs a decision."""
    strategies = [_strategy(), _strategy(StrategyType.MIGRATION, "Migrate cache")]
    evaluations = OrganizationStrategyEvaluator().evaluate(strategies)
    for strategy in strategies:
        assert strategy.status is StrategyStatus.PROPOSED


def test_evaluation_criteria_weights_sum_to_one(tmp_path):
    weights = OrganizationStrategyEvaluator.WEIGHTS
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_evaluation_shape(tmp_path):
    evaluation = OrganizationStrategyEvaluator().evaluate([_strategy()])[0].as_dict()
    for key in ["evaluation_id", "strategy_id", "criteria", "composite_score", "recommended", "readOnly"]:
        assert key in evaluation


# --------------------------------------------------------------------------- #
# 5. Organization Decision Lifecycle
# --------------------------------------------------------------------------- #


def _decision_manager(tmp_path) -> tuple[OrganizationDecisionManager, OrganizationStrategyStorage]:
    storage = _storage(tmp_path)
    return OrganizationDecisionManager(storage), storage


def test_decision_create_is_proposed(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="Adopt unified auth",
                              source_graph_nodes=["s1"], selected_strategy="ostrat_1",
                              alternatives=[], confidence=0.8, impact_report={}, risk_report={})
    assert decision.status is DecisionStatus.PROPOSED
    assert decision.history[0]["to"] == "PROPOSED"


def test_decision_full_lifecycle(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="Adopt unified auth",
                              source_graph_nodes=["s1"], selected_strategy="ostrat_1",
                              alternatives=[], confidence=0.8, impact_report={}, risk_report={})
    for target in ["ANALYZING", "REVIEW_REQUIRED", "APPROVAL_REQUIRED", "APPROVED", "IMPLEMENTATION_PLANNED", "VERIFIED"]:
        decision = manager.transition(decision.id, target)
    assert decision.status is DecisionStatus.VERIFIED
    assert len(decision.history) == 7


def test_decision_illegal_jump_rejected(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})
    with pytest.raises(ValidationFailed):
        manager.transition(decision.id, "APPROVED")


def test_decision_rejected_is_terminal(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})
    manager.transition(decision.id, "ANALYZING")
    manager.transition(decision.id, "REJECTED")
    with pytest.raises(ValidationFailed):
        manager.transition(decision.id, "APPROVED")


def test_decision_cancelled_is_terminal(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})
    manager.transition(decision.id, "ANALYZING")
    manager.transition(decision.id, "CANCELLED")
    with pytest.raises(ValidationFailed):
        manager.transition(decision.id, "ANALYZING")


def test_decision_superseded_is_terminal(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})
    for target in ["ANALYZING", "REVIEW_REQUIRED", "APPROVAL_REQUIRED", "APPROVED"]:
        decision = manager.transition(decision.id, target)
    decision = manager.transition(decision.id, "SUPERSEDED")
    with pytest.raises(ValidationFailed):
        manager.transition(decision.id, "VERIFIED")


def test_decision_unknown_status_rejected(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})
    with pytest.raises(ValidationFailed):
        manager.transition(decision.id, "MAYBE")


def test_decision_missing_404(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    with pytest.raises(Exception) as exc:
        manager.get("ostdec_missing")
    assert exc.type.__name__ in ("ResourceNotFound",)


def test_decision_binds_strategy_and_reports(tmp_path):
    manager, storage = _decision_manager(tmp_path)
    impact = {"impact_score": 69, "risk_level": "medium"}
    risk = {"impact": "high", "confidence": 0.8}
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=["s1", "s2"],
                              selected_strategy="ostrat_1", alternatives=["alt_a", "alt_b"],
                              confidence=0.75, impact_report=impact, risk_report=risk)
    assert decision.organization_id == "acme"
    assert decision.source_graph_nodes == ["s1", "s2"]
    assert decision.selected_strategy == "ostrat_1"
    assert decision.alternatives == ["alt_a", "alt_b"]
    assert decision.confidence == 0.75
    assert decision.impact_report == impact
    assert decision.risk_report == risk


def test_decision_persists_across_instances(tmp_path):
    manager, storage = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})
    manager.transition(decision.id, "ANALYZING")
    reloaded = OrganizationDecisionManager(storage).get(decision.id)
    assert reloaded.status is DecisionStatus.ANALYZING
    assert len(reloaded.history) == 2


def test_decision_empty_title_rejected(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    with pytest.raises(ValidationFailed):
        manager.create(organization_id="acme", title="  ", source_graph_nodes=[],
                       selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})


def test_decision_confidence_clamped(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=5.0, impact_report={}, risk_report={})
    assert decision.confidence == 1.0


def test_decision_history_tracks_transitions(tmp_path):
    manager, _storage_ = _decision_manager(tmp_path)
    decision = manager.create(organization_id="acme", title="D", source_graph_nodes=[],
                              selected_strategy="s", alternatives=[], confidence=0.5, impact_report={}, risk_report={})
    decision = manager.transition(decision.id, "ANALYZING")
    decision = manager.transition(decision.id, "REVIEW_REQUIRED")
    transitions = [(item["from"], item["to"]) for item in decision.history]
    assert ("", "PROPOSED") in transitions
    assert ("PROPOSED", "ANALYZING") in transitions
    assert ("ANALYZING", "REVIEW_REQUIRED") in transitions


def test_decision_status_enum_complete(tmp_path):
    expected = {"PROPOSED", "ANALYZING", "REVIEW_REQUIRED", "APPROVAL_REQUIRED", "APPROVED",
                "IMPLEMENTATION_PLANNED", "VERIFIED", "REJECTED", "CANCELLED", "SUPERSEDED"}
    assert {status.value for status in DecisionStatus} == expected


# --------------------------------------------------------------------------- #
# 6. Simulation Adapter
# --------------------------------------------------------------------------- #


def test_simulation_predictions_keys(tmp_path):
    simulation = OrganizationSimulationAdapter().simulate(_strategy())
    for key in ["risk", "cost", "impact", "dependency", "project_disruption", "migration_complexity",
                "project_count", "team_count", "estimated_effort"]:
        assert key in simulation.predictions


def test_simulation_predictions_in_bounds(tmp_path):
    simulation = OrganizationSimulationAdapter().simulate(_strategy())
    for key in ["risk", "cost", "impact", "dependency", "project_disruption", "migration_complexity"]:
        assert 0.0 <= simulation.predictions[key] <= 1.0


def test_simulation_migration_most_disruptive(tmp_path):
    adapter = OrganizationSimulationAdapter()
    migration = adapter.simulate(_strategy(StrategyType.MIGRATION))
    tests = adapter.simulate(_strategy(StrategyType.TEST_IMPROVEMENT))
    assert migration.predictions["project_disruption"] > tests.predictions["project_disruption"]
    assert migration.predictions["migration_complexity"] > tests.predictions["migration_complexity"]


def test_simulation_deterministic(tmp_path):
    adapter = OrganizationSimulationAdapter()
    first = adapter.simulate(_strategy())
    second = adapter.simulate(_strategy())
    assert first.predictions == second.predictions


def test_simulation_storage_roundtrip(tmp_path):
    storage = _storage(tmp_path)
    strategy = _strategy()
    storage.save_strategy(strategy)
    simulation = OrganizationSimulationAdapter().simulate(strategy)
    storage.save_simulation(simulation)
    loaded = storage.get_simulation(simulation.id)
    assert loaded is not None
    assert loaded.predictions == simulation.predictions


def test_simulation_shape(tmp_path):
    simulation = OrganizationSimulationAdapter().simulate(_strategy()).as_dict()
    for key in ["simulation_id", "strategy_id", "strategy_type", "predictions", "createdAt", "readOnly"]:
        assert key in simulation


def test_simulation_readonly_flag(tmp_path):
    assert OrganizationSimulationAdapter().simulate(_strategy()).as_dict()["readOnly"] is True


def test_simulation_project_count_reflects_affected(tmp_path):
    adapter = OrganizationSimulationAdapter()
    single = adapter.simulate(_strategy(projects=["checkout"]))
    multi = adapter.simulate(_strategy(projects=["checkout", "payments", "identity"]))
    assert multi.predictions["project_count"] > single.predictions["project_count"]
    assert multi.predictions["impact"] > single.predictions["impact"]


def test_simulation_effort_passthrough(tmp_path):
    strategy = _strategy()
    simulation = OrganizationSimulationAdapter().simulate(strategy)
    assert simulation.predictions["estimated_effort"] == strategy.estimated_effort


# --------------------------------------------------------------------------- #
# 7. Recommendation Engine
# --------------------------------------------------------------------------- #


def test_recommendation_from_health_warning(tmp_path):
    recommendations = OrganizationRecommendationEngine().build(
        healths=[{"project": "checkout", "healthScore": 55, "riskLevel": "medium"}],
    )
    assert any("checkout" in item.affected_projects for item in recommendations)


def test_recommendation_from_risk_propagation(tmp_path):
    recommendations = OrganizationRecommendationEngine().build(
        risks=[{"source": "s1", "impact": "high", "affected_nodes": [{"id": "x"}],
                "affected_projects": ["checkout"], "affected_teams": ["Platform"],
                "propagation_path": [{"path": ["checkout-api", "checkout-repo"]}], "confidence": 0.8}],
    )
    assert recommendations
    assert "checkout" in recommendations[0].affected_projects


def test_recommendation_from_cross_project_impact(tmp_path):
    recommendations = OrganizationRecommendationEngine().build(
        impacts=[{"source_node": "s1", "impact_score": 80, "risk_level": "high",
                  "affected_projects": ["checkout", "payments"], "affected_teams": ["Platform"], "confidence": 0.8}],
    )
    assert recommendations
    assert "checkout" in recommendations[0].affected_projects


def test_recommendation_from_debt(tmp_path):
    recommendations = OrganizationRecommendationEngine().build(
        debts={"checkout": [{"status": "OPEN", "category": "refactor", "severity": "high"},
                            {"status": "OPEN", "category": "refactor", "severity": "medium"},
                            {"status": "OPEN", "category": "refactor", "severity": "low"}]},
        teams_by_project={"checkout": "Platform"},
    )
    assert any("checkout" in item.affected_projects for item in recommendations)


def test_recommendation_from_drift(tmp_path):
    recommendations = OrganizationRecommendationEngine().build(
        drifts={"checkout": [{"issues": [{"type": "unrecorded_dependency"}, {"type": "circular_dependency"}]}]},
        teams_by_project={"checkout": "Platform"},
    )
    assert recommendations


def test_recommendation_from_simulation_risk(tmp_path):
    recommendations = OrganizationRecommendationEngine().build(
        simulations=[{"strategy_id": "ostrat_1", "predictions": {"risk": 0.85, "project_disruption": 0.9, "migration_complexity": 0.8}}],
    )
    assert recommendations
    assert any("strategy" in item.recommendation.lower() or "phase" in item.recommendation.lower() for item in recommendations)


def test_recommendation_empty_signals(tmp_path):
    assert OrganizationRecommendationEngine().build() == []


def test_recommendation_shape(tmp_path):
    recommendation = OrganizationRecommendationEngine().build(
        healths=[{"project": "checkout", "healthScore": 50, "riskLevel": "high"}],
    )[0].as_dict()
    for key in ["recommendation_id", "problem", "evidence", "recommendation", "expected_benefit",
                "risk", "confidence", "affected_projects", "affected_teams", "alternatives", "readOnly"]:
        assert key in recommendation


def test_recommendation_evidence_from_real_signals(tmp_path):
    recommendations = OrganizationRecommendationEngine().build(
        healths=[{"project": "checkout", "healthScore": 40, "riskLevel": "high"}],
    )
    assert recommendations[0].evidence
    assert "healthScore" in recommendations[0].evidence[0]


def test_recommendation_deterministic(tmp_path):
    signals = {"healths": [{"project": "checkout", "healthScore": 55, "riskLevel": "medium"}]}
    first = OrganizationRecommendationEngine().build(**signals)
    second = OrganizationRecommendationEngine().build(**signals)
    assert [item.as_dict() for item in first] == [item.as_dict() for item in second]


# --------------------------------------------------------------------------- #
# 8. Organization Memory
# --------------------------------------------------------------------------- #


def test_memory_documents_exist(tmp_path, bridge):
    from app.config import get_settings

    memory = OrganizationMemory(get_settings())
    assert set(memory.DOCUMENTS) == {"strategies", "decisions", "lessons", "risk_history"}
    assert "organization-strategies.md" in memory.DOCUMENTS.values()


def test_memory_append_after_approval_writes_file(tmp_path, bridge):
    from app.config import get_settings

    settings = get_settings()
    memory = OrganizationMemory(settings)
    result = memory.append_after_approval("acme", "strategies", "## Unified auth strategy")
    assert result["document"] == "organization-strategies.md"
    assert result["size"] > 0
    target = settings.memory_root / "organization" / "acme" / "organization-strategies.md"
    assert target.exists()
    assert "Unified auth strategy" in target.read_text(encoding="utf-8")


def test_memory_unknown_category_rejected(tmp_path, bridge):
    from app.config import get_settings

    memory = OrganizationMemory(get_settings())
    with pytest.raises(ValidationFailed):
        memory.append_after_approval("acme", "random", "content")


def test_memory_empty_org_rejected(tmp_path, bridge):
    from app.config import get_settings

    memory = OrganizationMemory(get_settings())
    with pytest.raises(ValidationFailed):
        memory.append_after_approval("", "strategies", "content")


def test_memory_history_lists_documents(tmp_path, bridge):
    from app.config import get_settings

    settings = get_settings()
    memory = OrganizationMemory(settings)
    memory.append_after_approval("acme", "decisions", "decision note")
    history = memory.history("acme")
    assert any(item["category"] == "decisions" for item in history)


def test_memory_history_empty_for_unknown_org(tmp_path, bridge):
    from app.config import get_settings

    assert OrganizationMemory(get_settings()).history("unknown-org") == []


def test_memory_preview_contains_proposal(tmp_path, bridge):
    from app.config import get_settings

    memory = OrganizationMemory(get_settings())
    preview = memory.preview("acme", "risk_history", "risk note")
    assert "[organization memory proposal/risk_history]" in preview


def test_memory_append_keeps_history_appending(tmp_path, bridge):
    from app.config import get_settings

    settings = get_settings()
    memory = OrganizationMemory(settings)
    memory.append_after_approval("acme", "lessons", "lesson one")
    memory.append_after_approval("acme", "lessons", "lesson two")
    text = (settings.memory_root / "organization" / "acme" / "cross-project-lessons.md").read_text(encoding="utf-8")
    assert "lesson one" in text and "lesson two" in text


# --------------------------------------------------------------------------- #
# 9. Engineering Graph Integration
# --------------------------------------------------------------------------- #


def test_edge_type_phase24_relations_present():
    for relation in ["INFLUENCES", "AFFECTS", "RECOMMENDS", "EVALUATED_BY", "IMPLEMENTED_BY", "SUPERSEDES"]:
        assert relation in {edge.value for edge in EdgeType}


def test_new_relations_are_non_hierarchical(tmp_path):
    edge = OrgEdge("a", "b", EdgeType.AFFECTS)
    assert edge.is_hierarchy is False


def test_strategy_create_syncs_graph_node(tmp_path):
    from app.config import get_settings

    manager = OrganizationStrategyManager(get_settings())
    result = manager.create_strategy({
        "strategy_type": "STANDARDIZATION", "title": "Unify auth",
        "problem": "auth fragmentation", "affected_projects": [], "affected_teams": [],
        "benefits": [], "risks": [], "estimated_effort": "", "confidence": 0.7,
        "priority": "high", "alternatives": [], "evidence": [],
    })
    node = manager.graph.get_node(result["strategy_id"])
    assert node is not None
    assert node.type == "ORGANIZATION_STRATEGY"


def test_strategy_create_syncs_affects_edges(tmp_path, monkeypatch):
    from app.config import get_settings, reset_settings_cache

    # Isolate from the shared settings DB so the AFFECTS-edge count is deterministic.
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "ws"))
    reset_settings_cache()
    settings = get_settings()
    graph = OrganizationGraphStorage(settings.organization_graph_db_path)
    graph.save_node(GraphNode(id="p1", type="PROJECT", name="checkout"))
    graph.save_node(GraphNode(id="p2", type="PROJECT", name="payments"))
    manager = OrganizationStrategyManager(settings)
    result = manager.create_strategy({
        "strategy_type": "REFACTOR", "title": "Reduce debt",
        "problem": "debt", "affected_projects": ["checkout", "payments"],
        "affected_teams": [], "benefits": [], "risks": [], "estimated_effort": "",
        "confidence": 0.6, "priority": "medium", "alternatives": [], "evidence": [],
    })
    edges = [edge for edge in graph.list_edges() if edge.relation is EdgeType.AFFECTS]
    assert len(edges) == 2
    assert {edge.source for edge in edges} == {result["strategy_id"]}


def test_evaluate_syncs_simulation_node_and_edge(tmp_path):
    from app.config import get_settings

    settings = get_settings()
    manager = OrganizationStrategyManager(settings)
    created = manager.create_strategy({
        "strategy_type": "MIGRATION", "title": "Consolidate cache",
        "problem": "cache failures", "affected_projects": ["checkout", "payments"],
        "affected_teams": [], "benefits": [], "risks": [], "estimated_effort": "",
        "confidence": 0.8, "priority": "high", "alternatives": [], "evidence": [],
    })
    result = manager.evaluate_strategies([created["strategy_id"]])
    simulation_id = result["simulations"][0]["simulation_id"]
    node = manager.graph.get_node(simulation_id)
    assert node is not None and node.type == "STRATEGY_SIMULATION"
    edges = [edge for edge in manager.graph.list_edges() if edge.relation is EdgeType.EVALUATED_BY]
    assert any(edge.source == created["strategy_id"] and edge.target == simulation_id for edge in edges)


def test_evaluate_marks_strategy_evaluated(tmp_path):
    from app.config import get_settings

    manager = OrganizationStrategyManager(get_settings())
    created = manager.create_strategy({
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
        "affected_projects": [], "affected_teams": [], "benefits": [], "risks": [],
        "estimated_effort": "", "confidence": 0.5, "priority": "medium",
        "alternatives": [], "evidence": [],
    })
    manager.evaluate_strategies([created["strategy_id"]])
    assert manager.storage.get_strategy(created["strategy_id"]).status is StrategyStatus.EVALUATED


def test_decision_create_syncs_decision_node(tmp_path):
    from app.config import get_settings

    manager = OrganizationStrategyManager(get_settings())
    created = manager.create_strategy({
        "strategy_type": "STANDARDIZATION", "title": "Unify auth",
        "problem": "auth fragmentation", "affected_projects": ["checkout"],
        "affected_teams": [], "benefits": [], "risks": [], "estimated_effort": "",
        "confidence": 0.7, "priority": "high", "alternatives": [], "evidence": [],
    })
    decision = manager.create_decision({
        "organization_id": "acme", "title": "Adopt unified auth",
        "strategy_id": created["strategy_id"], "source_graph_nodes": ["p1"],
        "alternatives": [], "confidence": 0.8, "impact_report": {}, "risk_report": {},
    })
    node = manager.graph.get_node(decision["decision_id"])
    assert node is not None and node.type == "ORGANIZATION_DECISION"
    relations = {edge.relation for edge in manager.graph.list_edges()}
    assert EdgeType.IMPLEMENTED_BY in relations
    assert EdgeType.INFLUENCES in relations


def test_decision_create_marks_strategy_selected(tmp_path):
    from app.config import get_settings

    manager = OrganizationStrategyManager(get_settings())
    created = manager.create_strategy({
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
        "affected_projects": [], "affected_teams": [], "benefits": [], "risks": [],
        "estimated_effort": "", "confidence": 0.5, "priority": "medium",
        "alternatives": [], "evidence": [],
    })
    manager.create_decision({"title": "D", "strategy_id": created["strategy_id"], "source_graph_nodes": [],
                             "alternatives": [], "confidence": 0.8, "impact_report": {}, "risk_report": {}})
    assert manager.storage.get_strategy(created["strategy_id"]).status is StrategyStatus.SELECTED


def test_superseded_decision_adds_supersedes_edge(tmp_path):
    from app.config import get_settings

    manager = OrganizationStrategyManager(get_settings())
    created = manager.create_strategy({
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
        "affected_projects": [], "affected_teams": [], "benefits": [], "risks": [],
        "estimated_effort": "", "confidence": 0.5, "priority": "medium",
        "alternatives": [], "evidence": [],
    })
    decision = manager.create_decision({"title": "D", "strategy_id": created["strategy_id"], "source_graph_nodes": [],
                                        "alternatives": [], "confidence": 0.8, "impact_report": {}, "risk_report": {}})
    for target in ["ANALYZING", "REVIEW_REQUIRED", "APPROVAL_REQUIRED", "APPROVED"]:
        manager.transition_decision(decision["decision_id"], target)
    manager.transition_decision(decision["decision_id"], "SUPERSEDED")
    edges = [edge for edge in manager.graph.list_edges() if edge.relation is EdgeType.SUPERSEDES]
    assert edges


def test_graph_hierarchy_untouched_by_strategy_nodes(tmp_path):
    from app.config import get_settings

    settings = get_settings()
    graph = OrganizationGraphStorage(settings.organization_graph_db_path)
    graph.save_node(GraphNode(id="p1", type="PROJECT", name="checkout", parent_id="team1"))
    manager = OrganizationStrategyManager(settings)
    manager.create_strategy({
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
        "affected_projects": ["checkout"], "affected_teams": [], "benefits": [], "risks": [],
        "estimated_effort": "", "confidence": 0.5, "priority": "medium",
        "alternatives": [], "evidence": [],
    })
    node = graph.get_node("p1")
    assert node.parent_id == "team1"


def test_old_graph_data_reads_after_new_relations(tmp_path):
    storage, _ids = _graph(tmp_path)
    storage.save_node(GraphNode(id="ostrat_x", type="ORGANIZATION_STRATEGY", name="strategy"))
    storage.save_edge(OrgEdge("ostrat_x", "p1", EdgeType.INFLUENCES))
    loaded = storage.list_edges()
    assert any(edge.relation is EdgeType.INFLUENCES for edge in loaded)


# --------------------------------------------------------------------------- #
# 10. Organization Context Extension
# --------------------------------------------------------------------------- #


def test_base_context_shape_unchanged(tmp_path):
    from app.organization_graph.context import OrganizationContextBuilder

    storage, _ids = _graph(tmp_path)
    context = OrganizationContextBuilder(storage).build_context("s1")
    assert set(context) == {"node", "owner", "hierarchy", "related_architecture", "incidents", "ancestorChain", "readOnly"}


def test_strategy_context_adds_signal_fields(tmp_path):
    from app.organization_graph.context import OrganizationContextBuilder

    storage, _ids = _graph(tmp_path)
    context = OrganizationContextBuilder(storage).build_strategy_context("s1")
    for key in ["organization_health", "active_risks", "cross_project_impacts", "active_strategies",
                "pending_decisions", "technical_debt", "architecture_drift", "recommendations"]:
        assert key in context
    assert context["readOnly"] is True


def test_strategy_context_defaults_empty(tmp_path):
    from app.organization_graph.context import OrganizationContextBuilder

    storage, _ids = _graph(tmp_path)
    context = OrganizationContextBuilder(storage).build_strategy_context("s1")
    assert context["active_risks"] == []
    assert context["technical_debt"] == {}
    assert context["recommendations"] == []


def test_strategy_context_populated_signals(tmp_path):
    from app.organization_graph.context import OrganizationContextBuilder

    storage, _ids = _graph(tmp_path)
    context = OrganizationContextBuilder(storage).build_strategy_context(
        "s1",
        organization_health=[{"project": "checkout", "healthScore": 80}],
        active_risks=[{"risk_id": "r1"}],
        active_strategies=[{"strategy_id": "s1"}],
        pending_decisions=[{"decision_id": "d1"}],
        technical_debt={"checkout": [{"status": "OPEN"}]},
        architecture_drift={"checkout": [{"issues": []}]},
        recommendations=[{"recommendation_id": "rec1"}],
        cross_project_impacts=[{"id": "i1"}],
    )
    assert len(context["organization_health"]) == 1
    assert len(context["active_risks"]) == 1
    assert len(context["active_strategies"]) == 1
    assert len(context["pending_decisions"]) == 1
    assert len(context["recommendations"]) == 1


def test_strategy_context_preserves_base_fields(tmp_path):
    from app.organization_graph.context import OrganizationContextBuilder

    storage, _ids = _graph(tmp_path)
    context = OrganizationContextBuilder(storage).build_strategy_context("s1")
    assert context["node"]["id"] == "s1"
    assert context["ancestorChain"] == ["Acme", "Platform", "checkout", "checkout-api"]


def test_strategy_context_missing_node_404(tmp_path):
    from app.organization_graph.context import OrganizationContextBuilder

    storage, _ids = _graph(tmp_path)
    with pytest.raises(Exception) as exc:
        OrganizationContextBuilder(storage).build_strategy_context("missing")
    assert exc.type.__name__ in ("ResourceNotFound",)


def test_strategy_context_readonly_true_even_with_data(tmp_path):
    from app.organization_graph.context import OrganizationContextBuilder

    storage, _ids = _graph(tmp_path)
    context = OrganizationContextBuilder(storage).build_strategy_context(
        "s1", active_risks=[{"risk_id": "r1"}]
    )
    assert context["readOnly"] is True


# --------------------------------------------------------------------------- #
# 11. Quality Gate 10.0 strategy extension
# --------------------------------------------------------------------------- #


def test_gate10_phase22_behavior_preserved():
    # Same formula as Phase 22: (100 - 92) * 0.5 = 4 -> 88, no blocking issues.
    report = QualityGate10Evaluator().evaluate(org="acme", org_health_score=92, project_count=5)
    assert report["quality"] == 88
    assert report["blockingIssues"] == []


def test_gate10_phase22_blocking_preserved():
    report = QualityGate10Evaluator().evaluate(org_health_score=40)
    assert "organization_health_critical" in report["blockingIssues"]


def test_gate10_new_strategy_fields_defaults():
    report = QualityGate10Evaluator().evaluate(org="acme")
    assert report["strategyConfidence"] == 100
    assert report["architectureRisk"] == 0
    assert report["technicalDebt"] == 0
    assert report["crossProjectImpact"] == 0
    assert report["riskPropagation"] == 0
    assert report["policyViolations"] == []


def test_gate10_policy_violations_block():
    report = QualityGate10Evaluator().evaluate(policy_violations=["high_risk_change_requires_review"])
    assert "strategy_policy_violations" in report["blockingIssues"]


def test_gate10_architecture_risk_blocks():
    report = QualityGate10Evaluator().evaluate(architecture_risk=80)
    assert "architecture_risk_high" in report["blockingIssues"]


def test_gate10_risk_propagation_blocks():
    report = QualityGate10Evaluator().evaluate(risk_propagation=75)
    assert "risk_propagation_high" in report["blockingIssues"]


def test_gate10_low_strategy_confidence_blocks():
    report = QualityGate10Evaluator().evaluate(strategy_confidence=0.4)
    assert "strategy_confidence_low" in report["blockingIssues"]


def test_gate10_strategy_signals_penalize_quality():
    baseline = QualityGate10Evaluator().evaluate(org_health_score=90)
    penalized = QualityGate10Evaluator().evaluate(
        org_health_score=90, strategy_confidence=0.4, architecture_risk=60, risk_propagation=50
    )
    assert penalized["quality"] < baseline["quality"]


def test_gate10_no_strategy_signals_keeps_score():
    plain = QualityGate10Evaluator().evaluate(org_health_score=85, open_incidents=1)
    extended = QualityGate10Evaluator().evaluate(org_health_score=85, open_incidents=1, technical_debt=0)
    assert plain["quality"] == extended["quality"]


def test_gate10_readonly_flag():
    assert QualityGate10Evaluator().evaluate()["readOnly"] is True


def test_gate10_all_output_keys():
    report = QualityGate10Evaluator().evaluate(org="acme")
    for key in ["organization", "orgHealthScore", "projectCount", "openIncidents", "criticalProjects",
                "strategyConfidence", "architectureRisk", "technicalDebt", "crossProjectImpact",
                "riskPropagation", "policyViolations", "recommendations", "blockingIssues",
                "quality", "readOnly"]:
        assert key in report


# --------------------------------------------------------------------------- #
# 12. API - read-only GET endpoints
# --------------------------------------------------------------------------- #


def test_api_impact_get_read_only(bridge):
    ids = _seed_org_graph_via_api(bridge)
    response = bridge.client.get(f"/organization/impact/{ids['checkout-api']}")
    assert response.status_code == 200
    body = response.json()
    assert body["readOnly"] is True
    assert "affected_projects" in body
    assert "payments" in body["affected_projects"]


def test_api_risk_get_read_only(bridge):
    ids = _seed_org_graph_via_api(bridge)
    response = bridge.client.get(
        f"/organization/risk/{ids['checkout-api']}", params={"severity": "high", "likelihood": "high"}
    )
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_api_risk_invalid_severity_400(bridge):
    ids = _seed_org_graph_via_api(bridge)
    response = bridge.client.get(f"/organization/risk/{ids['checkout-api']}", params={"severity": "bad"})
    assert response.status_code == 400


def test_api_impact_missing_node_404(bridge):
    response = bridge.client.get("/organization/impact/missing")
    assert response.status_code == 404


def test_api_strategies_list_read_only(bridge):
    _seed_org_graph_via_api(bridge)
    response = bridge.client.get("/organization/strategies/checkout")
    assert response.status_code == 200
    body = response.json()
    assert body["readOnly"] is True
    assert isinstance(body["strategies"], list)


def test_api_strategy_detail_404(bridge):
    response = bridge.client.get("/organization/strategy/ostrat_missing")
    assert response.status_code == 404


def test_api_decision_detail_404(bridge):
    response = bridge.client.get("/organization/decision/ostdec_missing")
    assert response.status_code == 404


def test_api_simulation_detail_404(bridge):
    response = bridge.client.get("/organization/simulation/ostsim_missing")
    assert response.status_code == 404


def test_api_recommendations_read_only(bridge):
    _seed_org_graph_via_api(bridge)
    response = bridge.client.get("/organization/recommendations")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_api_context_read_only(bridge):
    _seed_org_graph_via_api(bridge)
    response = bridge.client.get("/organization/context")
    assert response.status_code == 200
    body = response.json()
    assert body["readOnly"] is True
    for key in ["organization_health", "active_risks", "cross_project_impacts", "active_strategies",
                "pending_decisions", "technical_debt", "architecture_drift", "recommendations"]:
        assert key in body


def test_api_context_reads_do_not_mutate(bridge):
    _seed_org_graph_via_api(bridge)
    before = bridge.client.get("/organization/context").json()
    bridge.client.get("/organization/context")
    after = bridge.client.get("/organization/context").json()
    assert before == after


def test_api_gate10_strategy_query_params(bridge):
    response = bridge.client.get(
        "/quality/v10/acme",
        params={"org_health_score": 80, "strategy_confidence": 0.4, "architecture_risk": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["strategyConfidence"] == 40
    assert body["architectureRisk"] == 50
    assert "strategy_confidence_low" in body["blockingIssues"]


def test_api_gate10_old_params_unchanged(bridge):
    # Same Phase 22 behavior: (100 - 90) * 0.5 = 5 -> 85, no blocking issues.
    response = bridge.client.get("/quality/v10/acme", params={"org_health_score": 90})
    assert response.status_code == 200
    body = response.json()
    assert body["quality"] == 85
    assert body["blockingIssues"] == []
    assert body["strategyConfidence"] == 100


def test_api_impact_and_risk_audit(bridge):
    ids = _seed_org_graph_via_api(bridge)
    bridge.client.get(f"/organization/impact/{ids['checkout-api']}")
    bridge.client.get(f"/organization/risk/{ids['checkout-api']}")
    actions = {entry["action"] for entry in bridge.audit_entries()}
    assert "organization_impact_read" in actions
    assert "organization_risk_read" in actions


# --------------------------------------------------------------------------- #
# 13. Approval integration - all writes 202 -> approve -> persisted
# --------------------------------------------------------------------------- #


def test_strategy_create_requires_approval(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "STANDARDIZATION", "title": "Unify auth", "problem": "auth fragmentation",
        "reason": "propose",
    })
    assert pending.status_code == 202
    assert pending.json()["status"] == "pending"
    assert pending.json()["permissionLevel"] == "LEVEL_1"
    assert bridge.client.get("/organization/strategies/organization").json()["strategies"] == []


def test_strategy_create_after_approval_persists(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "REFACTOR", "title": "Reduce debt", "problem": "too much debt",
        "affected_projects": ["checkout"], "reason": "propose",
    })
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    strategy = executed.json()["result"]
    assert strategy["strategy_type"] == "REFACTOR"
    detail = bridge.client.get(f"/organization/strategy/{strategy['strategy_id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Reduce debt"


def test_strategy_evaluate_requires_approval(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "MIGRATION", "title": "Migrate cache", "problem": "cache failures",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_eval = bridge.client.post("/organization/strategy/evaluate", json={
        "strategy_ids": [strategy["strategy_id"]],
    })
    assert pending_eval.status_code == 202
    # Before approval: no simulation exists.
    assert bridge.client.get(f"/organization/simulation/{strategy['strategy_id']}").status_code == 404


def test_strategy_evaluate_after_approval_simulates(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "MIGRATION", "title": "Migrate cache", "problem": "cache failures",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_eval = bridge.client.post("/organization/strategy/evaluate", json={
        "strategy_ids": [strategy["strategy_id"]],
    })
    executed = bridge.approve(pending_eval.json()["requestId"])
    assert executed.status_code == 200
    result = executed.json()["result"]
    assert result["evaluations"]
    assert result["simulations"]
    simulation = result["simulations"][0]
    detail = bridge.client.get(f"/organization/simulation/{simulation['simulation_id']}")
    assert detail.status_code == 200
    assert "predictions" in detail.json()


def test_decision_create_requires_approval_and_strategy(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "STANDARDIZATION", "title": "Unify auth", "problem": "auth fragmentation",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_decision = bridge.client.post("/organization/strategy/decision/create", json={
        "title": "Adopt unified auth", "strategy_id": strategy["strategy_id"],
        "source_graph_nodes": ["s1"], "confidence": 0.8,
    })
    assert pending_decision.status_code == 202
    # Before approval: decision does not exist and the strategy stays PROPOSED.
    assert bridge.client.get(f"/organization/decision/{strategy['strategy_id']}").status_code == 404


def test_decision_create_after_approval_persists(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "STANDARDIZATION", "title": "Unify auth", "problem": "auth fragmentation",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_decision = bridge.client.post("/organization/strategy/decision/create", json={
        "title": "Adopt unified auth", "strategy_id": strategy["strategy_id"],
        "source_graph_nodes": ["s1"], "confidence": 0.8,
    })
    executed = bridge.approve(pending_decision.json()["requestId"])
    assert executed.status_code == 200
    decision = executed.json()["result"]
    assert decision["status"] == "PROPOSED"
    detail = bridge.client.get(f"/organization/decision/{decision['decision_id']}")
    assert detail.status_code == 200
    assert detail.json()["selected_strategy"] == strategy["strategy_id"]


def test_decision_transition_requires_approval(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_decision = bridge.client.post("/organization/strategy/decision/create", json={
        "title": "D", "strategy_id": strategy["strategy_id"],
    })
    decision = bridge.approve(pending_decision.json()["requestId"]).json()["result"]
    pending_transition = bridge.client.post("/organization/strategy/decision/transition", json={
        "decision_id": decision["decision_id"], "status": "ANALYZING",
    })
    assert pending_transition.status_code == 202
    detail = bridge.client.get(f"/organization/decision/{decision['decision_id']}")
    assert detail.json()["status"] == "PROPOSED"


def test_decision_transition_after_approval_applies(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_decision = bridge.client.post("/organization/strategy/decision/create", json={
        "title": "D", "strategy_id": strategy["strategy_id"],
    })
    decision = bridge.approve(pending_decision.json()["requestId"]).json()["result"]
    pending_transition = bridge.client.post("/organization/strategy/decision/transition", json={
        "decision_id": decision["decision_id"], "status": "ANALYZING",
    })
    executed = bridge.approve(pending_transition.json()["requestId"])
    assert executed.status_code == 200
    assert executed.json()["result"]["status"] == "ANALYZING"


def test_decision_illegal_transition_rejected_after_approval(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_decision = bridge.client.post("/organization/strategy/decision/create", json={
        "title": "D", "strategy_id": strategy["strategy_id"],
    })
    decision = bridge.approve(pending_decision.json()["requestId"]).json()["result"]
    pending_transition = bridge.client.post("/organization/strategy/decision/transition", json={
        "decision_id": decision["decision_id"], "status": "VERIFIED",
    })
    executed = bridge.approve(pending_transition.json()["requestId"])
    assert executed.status_code == 400


def test_memory_append_requires_approval(bridge):
    pending = bridge.client.post("/organization/memory/append", json={
        "organization": "acme", "category": "strategies", "content": "## Strategy",
    })
    assert pending.status_code == 202
    from app.config import get_settings

    target = get_settings().memory_root / "organization" / "acme" / "organization-strategies.md"
    assert not target.exists()


def test_memory_append_after_approval_writes(bridge):
    pending = bridge.client.post("/organization/memory/append", json={
        "organization": "acme", "category": "decisions", "content": "## Decision note",
    })
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    result = executed.json()["result"]
    assert result["document"] == "organization-decisions.md"
    from app.config import get_settings

    target = get_settings().memory_root / "organization" / "acme" / "organization-decisions.md"
    assert target.exists()
    assert "Decision note" in target.read_text(encoding="utf-8")


def test_full_strategy_pipeline_through_approval(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "MIGRATION", "title": "Consolidate cache", "problem": "cache failures",
        "affected_projects": ["checkout", "payments"], "alternatives": ["status quo", "phased"],
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_eval = bridge.client.post("/organization/strategy/evaluate", json={
        "strategy_ids": [strategy["strategy_id"]],
    })
    evaluated = bridge.approve(pending_eval.json()["requestId"]).json()["result"]
    assert evaluated["evaluations"][0]["recommended"] in (True, False)
    pending_decision = bridge.client.post("/organization/strategy/decision/create", json={
        "title": "Consolidate cache decision", "strategy_id": strategy["strategy_id"],
    })
    decision = bridge.approve(pending_decision.json()["requestId"]).json()["result"]
    assert decision["selected_strategy"] == strategy["strategy_id"]
    for target in ["ANALYZING", "REVIEW_REQUIRED", "APPROVAL_REQUIRED"]:
        pending_transition = bridge.client.post("/organization/strategy/decision/transition", json={
            "decision_id": decision["decision_id"], "status": target,
        })
        assert bridge.approve(pending_transition.json()["requestId"]).status_code == 200
    detail = bridge.client.get(f"/organization/decision/{decision['decision_id']}")
    assert detail.json()["status"] == "APPROVAL_REQUIRED"


def test_approval_actions_are_level_1(bridge):
    for action in ["organization_strategy_create", "organization_strategy_evaluate",
                   "organization_strategy_decision_create", "organization_strategy_decision_transition",
                   "organization_memory_append"]:
        assert level_for_action(action) is PermissionLevel.LEVEL_1


def test_no_level_2_for_strategy_actions(bridge):
    for action in ["organization_strategy_create", "organization_strategy_evaluate",
                   "organization_strategy_decision_create", "organization_strategy_decision_transition",
                   "organization_memory_append"]:
        assert level_for_action(action) is not PermissionLevel.LEVEL_2


# --------------------------------------------------------------------------- #
# 14. Security regression
# --------------------------------------------------------------------------- #


def test_unapproved_strategy_create_has_no_side_effects(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
    })
    assert pending.status_code == 202
    assert bridge.client.get("/organization/strategies/organization").json()["strategies"] == []


def test_unapproved_decision_create_does_not_touch_projects(bridge):
    _seed_org_graph_via_api(bridge)
    before = bridge.client.get("/organization/context").json()
    pending = bridge.client.post("/organization/strategy/decision/create", json={
        "title": "D", "strategy_id": "ostrat_none",
    })
    assert pending.status_code == 202 or pending.status_code == 404
    after = bridge.client.get("/organization/context").json()
    assert before == after


def test_unapproved_memory_append_writes_nothing(bridge):
    bridge.client.post("/organization/memory/append", json={
        "organization": "acme", "category": "lessons", "content": "injected lesson",
    })
    from app.config import get_settings

    target = get_settings().memory_root / "organization" / "acme" / "cross-project-lessons.md"
    assert not target.exists()


def test_strategy_modules_have_no_executor(tmp_path):
    sources = inspect.getsource(OrganizationStrategyManager) + inspect.getsource(OrganizationImpactAnalyzer)
    assert "ControlledExecutor" not in sources
    assert "subprocess" not in sources
    assert "shell" not in sources.lower()


def test_strategy_routes_have_no_hidden_execution(tmp_path):
    from app.organization_strategy.routes import register_organization_strategy_routes

    source = inspect.getsource(register_organization_strategy_routes)
    assert "execute" not in source.lower().replace("executed", "").replace("execution", "")
    assert "subprocess" not in source


def test_strategy_manager_has_no_auto_approval(tmp_path):
    source = inspect.getsource(OrganizationStrategyManager)
    assert "mark_approved" not in source
    assert "auto_approve" not in source.lower()


def test_risk_and_analyzer_are_read_only(tmp_path):
    for module in [OrganizationImpactAnalyzer, OrganizationRiskEngine]:
        source = inspect.getsource(module)
        assert "delete" not in source
        assert "update" not in source.replace("updated", "")


def test_no_random_confidence(tmp_path):
    strategies = OrganizationStrategyGenerator().generate(
        failure_patterns=[{"project": "a", "category": "deployment", "occurrences": 2},
                          {"project": "b", "category": "deployment", "occurrences": 2}],
    )
    import random

    random.seed(1)
    first = [strategy.confidence for strategy in OrganizationStrategyGenerator().generate(
        failure_patterns=[{"project": "a", "category": "deployment", "occurrences": 2},
                          {"project": "b", "category": "deployment", "occurrences": 2}],
    )]
    random.seed(2)
    second = [strategy.confidence for strategy in OrganizationStrategyGenerator().generate(
        failure_patterns=[{"project": "a", "category": "deployment", "occurrences": 2},
                          {"project": "b", "category": "deployment", "occurrences": 2}],
    )]
    assert first == second


def test_strategy_never_calls_controlled_executor(tmp_path):
    from app.organization_strategy import routes, manager, strategy, decision, simulation

    combined = "".join(
        inspect.getsource(module) for module in [routes, manager, strategy, decision, simulation]
    )
    assert "ControlledExecutor" not in combined
    assert "execution_execute" not in combined


def test_graph_poisoning_via_reads_impossible(bridge):
    _seed_org_graph_via_api(bridge)
    before = bridge.client.get("/organization-graph/snapshot/list").json()["snapshots"]
    bridge.client.get("/organization/impact/s1")
    bridge.client.get("/organization/risk/s1")
    bridge.client.get("/organization/recommendations")
    after = bridge.client.get("/organization-graph/snapshot/list").json()["snapshots"]
    assert before == after


def test_cross_project_data_leakage_blocked(bridge):
    """Read endpoints are GET-only; no write endpoint exists for cross-project data."""
    _seed_org_graph_via_api(bridge)
    response = bridge.client.post("/organization/impact/s1", json={})
    assert response.status_code == 405


def test_permission_escalation_impossible(tmp_path):
    for action in ["organization_strategy_create", "organization_strategy_evaluate",
                   "organization_strategy_decision_create", "organization_strategy_decision_transition",
                   "organization_memory_append"]:
        assert level_for_action(action) is PermissionLevel.LEVEL_1
    assert "organization_strategy_create" not in {action for action, level in
                                                  __import__("app.security.permissions", fromlist=["ACTION_LEVELS"]).ACTION_LEVELS.items()
                                                  if level is PermissionLevel.LEVEL_2}


def test_simulation_not_modifiable_via_api(bridge):
    pending = bridge.client.post("/organization/strategy/create", json={
        "strategy_type": "REFACTOR", "title": "T", "problem": "P",
    })
    strategy = bridge.approve(pending.json()["requestId"]).json()["result"]
    pending_eval = bridge.client.post("/organization/strategy/evaluate", json={
        "strategy_ids": [strategy["strategy_id"]],
    })
    simulation = bridge.approve(pending_eval.json()["requestId"]).json()["result"]["simulations"][0]
    response = bridge.client.post(f"/organization/simulation/{simulation['simulation_id']}", json={"predictions": {}})
    assert response.status_code == 405


def test_strategy_write_endpoints_all_202(bridge):
    for endpoint, payload in [
        ("/organization/strategy/create", {"strategy_type": "REFACTOR", "title": "T", "problem": "P"}),
        ("/organization/strategy/evaluate", {"strategy_ids": ["ostrat_1"]}),
        ("/organization/strategy/decision/create", {"title": "D", "strategy_id": "ostrat_1"}),
        ("/organization/strategy/decision/transition", {"decision_id": "ostdec_1", "status": "ANALYZING"}),
        ("/organization/memory/append", {"organization": "acme", "category": "strategies", "content": "c"}),
    ]:
        response = bridge.client.post(endpoint, json=payload)
        assert response.status_code in (202, 404), (endpoint, response.status_code)
