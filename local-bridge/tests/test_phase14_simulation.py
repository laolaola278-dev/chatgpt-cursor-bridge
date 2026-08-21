from __future__ import annotations

from pathlib import Path

import pytest

from app.code_intelligence import CodeIndex, CodeScanner
from app.config import get_settings
from app.intelligence.models import Insight, InsightType, Proposal, ProposalStatus, Severity
from app.intelligence.storage import IntelligenceStorage
from app.memory.planning import PlanningMemory
from app.quality.gate6 import QualityGate6Evaluator
from app.security.permissions import ApprovalStatus, ApprovalStore
from app.simulation import SimulationManager, SimulationStorage
from app.simulation.evaluator import ScenarioEvaluator
from app.simulation.models import PlanStatus, ScenarioStatus, SimulationStatus
from app.simulation.planner import ScenarioPlanner
from app.simulation.scenario import ImpactSimulator
from app.security.validator import ValidationFailed


def setup_sim(bridge):
    settings = get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    storage = SimulationStorage(settings.simulation_db_path)
    manager = SimulationManager(storage, CodeIndex(settings.code_index_db_path))
    return settings, index, storage, manager


def test_simulation_package_is_persistent(bridge):
    settings, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="high coupling user service")
    reopened = SimulationStorage(settings.simulation_db_path)
    assert reopened.get_simulation(simulation.id).problem == simulation.problem

@pytest.mark.parametrize("problem", ["high coupling", "low coverage", "slow build", "security boundary", "database migration", "large module", "unstable tests", "duplicate logic", "missing API contract", "legacy adapter"])
def test_simulation_create_normalizes_problem(bridge, problem):
    _, _, _, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem=f"  {problem}  ")
    assert simulation.status is SimulationStatus.DRAFT and simulation.problem == problem

@pytest.mark.parametrize("bad", ["", " ", "\n", "\t"])
def test_simulation_rejects_empty_problem(bridge, bad):
    _, _, _, manager = setup_sim(bridge)
    with pytest.raises(ValidationFailed): manager.create(project="demo", problem=bad)


def test_planner_generates_three_alternatives(bridge):
    _, index, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="UserService too complex")
    result = manager.analyze(simulation.id)
    assert len(result["scenarios"]) == 3
    assert {item["type"] for item in result["scenarios"]} == {"patch", "refactor", "rewrite"}
    assert storage.get_simulation(simulation.id).status is SimulationStatus.COMPLETED

@pytest.mark.parametrize("kind", ["patch", "refactor", "rewrite"])
def test_planner_scenario_types_are_safe(bridge, kind):
    _, index, _, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling")
    scenarios = ScenarioPlanner(index).plan(simulation_id=simulation.id, project="demo", problem=simulation.problem)
    assert any(item.scenario_type == kind and item.workflow_stages == ["IMPLEMENTATION", "TESTING", "REVIEW"] for item in scenarios)

@pytest.mark.parametrize("coverage", [None, 0, 20, 50, 80, 100])
def test_simulation_analysis_is_deterministic_and_read_only(bridge, coverage):
    settings, _, storage, manager = setup_sim(bridge)
    before = (bridge.demo / "src" / "main.py").read_bytes()
    simulation = manager.create(project="demo", problem="coupling")
    result = manager.analyze(simulation.id, test_coverage=coverage)
    assert result["readOnlyAnalysis"] is True and len(result["evaluations"]) == 3
    assert (bridge.demo / "src" / "main.py").read_bytes() == before
    assert PlanningMemory(settings).history("demo") == []

@pytest.mark.parametrize("scenario_index", [0, 1, 2])
def test_scenario_has_impact_prediction(bridge, scenario_index):
    _, _, _, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling")
    result = manager.analyze(simulation.id)
    scenario = result["scenarios"][scenario_index]
    assert 0 <= scenario["impactScore"] <= 100 and 0 <= scenario["riskScore"] <= 100
    assert scenario["affectedFiles"] and "IMPLEMENTATION" in scenario["workflowStages"]

@pytest.mark.parametrize("scenario_index", [0, 1, 2])
def test_scenario_evaluation_has_tradeoffs(bridge, scenario_index):
    _, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling")
    manager.analyze(simulation.id)
    scenario = storage.list_scenarios(simulation.id)[scenario_index]
    evaluation = storage.get_evaluation(scenario.id)
    assert evaluation is not None and 0 <= evaluation.score <= 100
    assert evaluation.advantages and evaluation.disadvantages

@pytest.mark.parametrize("scope", [0, 1, 2, 5, 10, 20, 50, 100])
def test_impact_simulator_bounds_scope(bridge, scope):
    _, index, _, _ = setup_sim(bridge)
    result = ImpactSimulator(index).simulate("scenario", "sim", "demo", name="Test", scenario_type="patch", changes=["change"], affected_files=["src/main.py"] * max(1, scope))
    assert 0 <= result.impact_score <= 100 and 0 <= result.risk_score <= 100

@pytest.mark.parametrize("kind", ["patch", "refactor", "rewrite", "migration"])
def test_impact_simulator_assigns_workflow_and_memory_impact(bridge, kind):
    _, index, _, _ = setup_sim(bridge)
    result = ImpactSimulator(index).simulate("scenario", "sim", "demo", name="Test", scenario_type=kind, changes=["change"], affected_files=["src/main.py"])
    assert result.workflow_stages == ["IMPLEMENTATION", "TESTING", "REVIEW"]
    if kind in {"refactor", "rewrite", "migration"}: assert "ADR required" in result.memory_impacts

@pytest.mark.parametrize("rollback", [False, True])
def test_evaluator_exposes_rollback_factor(bridge, rollback):
    _, index, _, _ = setup_sim(bridge)
    scenario = ImpactSimulator(index).simulate("scenario", "sim", "demo", name="Test", scenario_type="patch", changes=["change"], affected_files=["src/main.py"])
    evaluation = ScenarioEvaluator().evaluate(scenario, rollback_available=rollback)
    assert evaluation.factors["rollback"] == (10 if rollback else 0)

@pytest.mark.parametrize("coverage", [None, 0, 25, 50, 75, 100])
def test_evaluator_score_is_bounded(bridge, coverage):
    _, index, _, _ = setup_sim(bridge)
    scenario = ImpactSimulator(index).simulate("scenario", "sim", "demo", name="Test", scenario_type="refactor", changes=["change"], affected_files=["src/main.py"])
    evaluation = ScenarioEvaluator().evaluate(scenario, test_coverage=coverage)
    assert 0 <= evaluation.score <= 100 and evaluation.risk in {"low", "medium", "high"}

@pytest.mark.parametrize("scenario_status", list(ScenarioStatus))
def test_scenario_status_enum_is_stable(scenario_status):
    assert ScenarioStatus(scenario_status.value) is scenario_status

@pytest.mark.parametrize("plan_status", list(PlanStatus))
def test_plan_status_enum_is_stable(plan_status):
    assert PlanStatus(plan_status.value) is plan_status

@pytest.mark.parametrize("limit", [1, 2, 3, 5, 10])
def test_storage_lists_simulations_by_project(bridge, limit):
    _, _, storage, manager = setup_sim(bridge)
    for index in range(4): manager.create(project="demo" if index % 2 == 0 else "other", problem=f"problem {index}")
    assert len(storage.list_simulations("demo", limit=limit)) <= limit
    assert all(item.project == "demo" for item in storage.list_simulations("demo"))

@pytest.mark.parametrize("problem", ["a", "b", "c", "d", "e"])
def test_storage_simulation_history_contains_creation(bridge, problem):
    _, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem=problem)
    assert storage.get_simulation(simulation.id).history[0]["status"] == "DRAFT"


def test_plan_generation_has_required_sections(bridge):
    _, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling")
    manager.analyze(simulation.id)
    scenario = storage.list_scenarios(simulation.id)[0]
    plan = manager.plan(simulation.id, scenario.id)
    assert plan.status is PlanStatus.DRAFT
    for section in ["# Engineering Plan", "## Problem", "## Current State", "## Selected Scenario", "## Files", "## Implementation Steps", "## Testing Plan", "## Rollback Plan", "## Risks"]:
        assert section in plan.content

@pytest.mark.parametrize("index", [0, 1, 2])
def test_plan_can_be_reopened(bridge, index):
    settings, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling"); manager.analyze(simulation.id)
    scenario = storage.list_scenarios(simulation.id)[index]
    plan = manager.plan(simulation.id, scenario.id)
    assert SimulationStorage(settings.simulation_db_path).get_plan(plan.id).content == plan.content

@pytest.mark.parametrize("bad_id", ["missing", "scenario_x", "sim_other"])
def test_plan_rejects_unknown_or_cross_bound_scenario(bridge, bad_id):
    _, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling")
    with pytest.raises(ValidationFailed): manager.plan(simulation.id, bad_id)


def test_planning_memory_preview_does_not_write(bridge):
    settings, _, _, _ = setup_sim(bridge)
    memory = PlanningMemory(settings)
    assert "proposal" in memory.preview("demo", "plans", "# Engineering Plan")
    assert memory.history("demo") == []

@pytest.mark.parametrize("category,filename", [("plans", "engineering-plans.md"), ("architecture", "architecture-options.md"), ("tradeoffs", "tradeoff-history.md")])
def test_planning_memory_append_is_append_only(bridge, category, filename):
    settings, _, _, _ = setup_sim(bridge)
    memory = PlanningMemory(settings)
    result = memory.append_after_approval("demo", category, "approved content")
    assert result["document"] == filename
    assert filename in {item["document"] for item in memory.history("demo")}

@pytest.mark.parametrize("category", ["bad", "code", "memory", ""])
def test_planning_memory_rejects_unknown_category(bridge, category):
    settings, _, _, _ = setup_sim(bridge)
    with pytest.raises(ValidationFailed): PlanningMemory(settings).preview("demo", category, "no")

@pytest.mark.parametrize("confidence", [0, .1, .25, .5, .75, .84, 1])
def test_quality_gate6_confidence_is_bounded(confidence):
    report = QualityGate6Evaluator().evaluate(simulation_confidence=confidence, alternative_coverage=80, risk_prediction_accuracy=70, plan_completeness=90)
    assert report["simulationConfidence"] == confidence and 0 <= report["quality"] <= 100 and report["readOnly"] is True

@pytest.mark.parametrize("value", [0, 10, 25, 50, 75, 100])
def test_quality_gate6_metrics_are_visible(value):
    report = QualityGate6Evaluator().evaluate(alternative_coverage=value, risk_prediction_accuracy=value, plan_completeness=value)
    assert report["alternativeCoverage"] == value and report["riskPredictionAccuracy"] == value and report["planCompleteness"] == value


def test_quality_gate6_missing_information_is_preserved():
    report = QualityGate6Evaluator().evaluate(simulation_confidence=.84, missing_information=["database migration impact"])
    assert report["missingInformation"] == ["database migration impact"]


def test_simulation_create_api_requires_approval(bridge):
    pending = bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"})
    assert pending.status_code == 202
    simulation_id = pending.json()["requestId"]
    assert bridge.client.get("/simulation/" + simulation_id).status_code in {404, 422}
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    created = executed.json()["result"]
    assert created["status"] == "DRAFT"


def test_simulation_api_flow_is_approval_gated(bridge):
    created_pending = bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"})
    created = bridge.approve(created_pending.json()["requestId"]).json()["result"]
    analyzed_pending = bridge.client.post(f"/simulation/{created['id']}/analyze", json={"test_coverage": 30})
    assert analyzed_pending.status_code == 202
    assert bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"] == []
    analyzed = bridge.approve(analyzed_pending.json()["requestId"])
    assert analyzed.status_code == 200
    scenarios = bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"]
    assert len(scenarios) == 3


def test_simulation_plan_requires_second_memory_approval(bridge):
    created = bridge.approve(bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/simulation/{created['id']}/analyze", json={}).json()["requestId"])
    scenario = bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"][0]
    plan_pending = bridge.client.post(f"/simulation/{created['id']}/plan", json={"scenario_id": scenario["id"]})
    assert plan_pending.status_code == 202
    executed = bridge.approve(plan_pending.json()["requestId"])
    assert executed.status_code == 200
    result = executed.json()["result"]
    assert result["content"].startswith("# Engineering Plan")
    memory_id = result["memoryProposal"]["requestId"]
    assert bridge.client.get("/memory/planning/history", params={"project": "demo"}).json()["history"] == []
    assert bridge.approve(memory_id).status_code == 200
    assert bridge.client.get("/memory/planning/history", params={"project": "demo"}).json()["history"]

@pytest.mark.parametrize("endpoint", ["/simulation/missing/scenarios", "/simulation/missing/evaluation", "/simulation/missing"])
def test_simulation_read_unknown_is_rejected(bridge, endpoint):
    assert bridge.client.get(endpoint).status_code in {404, 422}

@pytest.mark.parametrize("endpoint", ["/simulation/create", "/simulation/missing/analyze", "/simulation/missing/plan"])
def test_simulation_writes_do_not_execute_without_valid_approval(bridge, endpoint):
    if endpoint.endswith("create"):
        response = bridge.client.post(endpoint, json={"project": "demo", "problem": "test"})
        assert response.status_code == 202
    else:
        response = bridge.client.post(endpoint, json={"scenario_id": "scenario_x"} if endpoint.endswith("plan") else {})
        assert response.status_code in {404, 422}


def test_simulation_recovery_never_auto_approves(tmp_path):
    store = ApprovalStore(tmp_path / "approval.db")
    request = store.create(action="simulation_create", project="demo", path="simulation", payload={"problem": "test"}, reason="test", preview="metadata")
    recovered = store.recover_pending()
    assert recovered[0].status is ApprovalStatus.RECOVERED
    with pytest.raises(Exception): store.mark_approved(request.request_id)
    store.reconfirm(request.request_id)
    assert store.mark_approved(request.request_id).status.value == "approved"


def test_simulation_does_not_call_subprocess(bridge, monkeypatch):
    _, _, _, manager = setup_sim(bridge)
    called = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: called.append(args))
    simulation = manager.create(project="demo", problem="test")
    manager.analyze(simulation.id)
    assert called == []


def test_quality_gate6_api_is_read_only(bridge):
    response = bridge.client.get("/quality/v6/wf_1", params={"simulation_confidence": .84, "alternative_coverage": 80, "missing_information": "database migration impact"})
    assert response.status_code == 200 and response.json()["readOnly"] is True

@pytest.mark.parametrize("field", ["quality", "simulationConfidence", "alternativeCoverage", "riskPredictionAccuracy", "planCompleteness", "missingInformation", "readOnly"])
def test_quality_gate6_api_contract(bridge, field):
    assert field in bridge.client.get("/quality/v6/wf_1").json()


def test_simulation_status_update_preserves_child_scenarios(bridge):
    _, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling")
    manager.analyze(simulation.id)
    assert len(storage.list_scenarios(simulation.id)) == 3
    assert storage.get_simulation(simulation.id).status is SimulationStatus.COMPLETED


def test_missing_simulation_resources_return_not_found(bridge):
    assert bridge.client.get("/simulation/missing").status_code == 404
    assert bridge.client.get("/simulation/missing/scenarios").status_code == 404
    assert bridge.client.get("/simulation/missing/evaluation").status_code == 404


def test_plan_approval_boundary_keeps_planning_memory_empty(bridge):
    settings, _, storage, manager = setup_sim(bridge)
    simulation = manager.create(project="demo", problem="coupling")
    manager.analyze(simulation.id)
    plan = manager.plan(simulation.id, storage.list_scenarios(simulation.id)[0].id)
    assert plan.content.startswith("# Engineering Plan")
    assert PlanningMemory(settings).history("demo") == []
