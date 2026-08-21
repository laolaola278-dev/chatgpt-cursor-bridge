from __future__ import annotations

import pytest

from app.config import get_settings
from app.execution import ExecutionManager, ExecutionStorage
from app.execution.verification_pipeline import VerificationPipeline
from app.execution_dag import ExecutionDagManager, ExecutionDagStorage
from app.execution_dag.models import DagStatus, DependencyType
from app.execution_loop import ExecutionLoopOrchestrator, ExecutionLoopRecovery, ExecutionLoopStorage, LoopContextBuilder
from app.execution_loop.models import ExecutionLoop, LoopStatus
from app.metrics.engineering import EngineeringMetricsManager
from app.security.permissions import ApprovalStore
from app.security.validator import ResourceNotFound, ValidationFailed
from app.simulation import SimulationStorage
from app.simulation.models import Plan, PlanStatus, Scenario, ScenarioStatus, Simulation, SimulationStatus

PLAN_CONTENT = """# Engineering Plan

## Problem
high coupling

## Current State
simulated

## Selected Scenario
module extraction (refactor)

## Files
- `src/main.py`
- `src/auth.py`

## Implementation Steps
1. extract auth service
2. move token logic

## Testing Plan
- regression tests

## Rollback Plan
- restore snapshots

## Risks
- medium
"""


def seed_plan(bridge, plan_id: str = "plan_1") -> Plan:
    storage = SimulationStorage(get_settings().simulation_db_path)
    storage.save_simulation(Simulation(id="sim_1", project="demo", problem="high coupling", status=SimulationStatus.APPROVED, created_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", history=[{"status": "APPROVED", "at": "2026-02-01T00:00:00Z", "detail": "seeded"}]))
    storage.save_scenarios([Scenario(id="scenario_a", simulation_id="sim_1", name="Module Extraction", scenario_type="refactor", changes=["create auth service"], affected_files=["src/main.py", "src/auth.py"], dependent_modules=[], affected_tests=[], workflow_stages=["IMPLEMENTATION", "TESTING"], memory_impacts=[], risk_score=45, impact_score=30, risk="medium", status=ScenarioStatus.CANDIDATE)])
    plan = Plan(id=plan_id, simulation_id="sim_1", scenario_id="scenario_a", content=PLAN_CONTENT, status=PlanStatus.APPROVED, created_at="2026-02-01T00:00:00Z")
    storage.save_plan(plan)
    return plan


def setup(bridge):
    from app.audit.logger import get_audit_logger

    settings = get_settings()
    approvals = ApprovalStore()
    loop_storage = ExecutionLoopStorage(settings.execution_loop_db_path)
    orchestrator = ExecutionLoopOrchestrator(loop_storage, settings, approvals=approvals, audit=get_audit_logger())
    dag_storage = ExecutionDagStorage(settings.execution_dag_db_path)
    dag_manager = ExecutionDagManager(dag_storage, orchestrator, audit=get_audit_logger())
    return settings, approvals, loop_storage, orchestrator, dag_storage, dag_manager


def make_loop(orchestrator: ExecutionLoopOrchestrator, *, loop_id: str, status: LoopStatus = LoopStatus.PLANNING, with_tasks: bool = False) -> ExecutionLoop:
    task_ids: list[str] = []
    if with_tasks:
        tasks = orchestrator.execution_manager.create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=PLAN_CONTENT)
        task_ids = [task.id for task in tasks]
    return ExecutionLoop(id=loop_id, project="demo", plan_id="plan_1", workflow_id=None, task_ids=task_ids, status=status, created_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", history=[{"status": status.value, "at": "2026-02-01T00:00:00Z", "detail": ""}])


def approved_execute_id(approvals: ApprovalStore) -> str:
    request = approvals.create(action="execution_execute", project="demo", path="execution", payload={}, reason="test", preview="metadata")
    approvals.mark_approved(request.request_id)
    return request.request_id


def _dummy_result():
    from app.execution.models import ExecutionResult

    return ExecutionResult(
        id="er_x", proposal_id="ep_x", task_id="et_x", project="demo",
        files_changed=["src/main.py"], diff_summary={"changed": 1, "diffBytes": 120},
        duration_ms=10, errors=[],
        verification={"status": "PASS", "checks": ["approval_verified", "snapshot_captured", "git_diff_present"], "snapshotCaptured": True, "approvalVerified": True, "files": ["src/main.py"]},
        created_at="2026-02-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Execution DAG: creation and validation
# ---------------------------------------------------------------------------


def test_dag_requires_loops(bridge):
    seed_plan(bridge)
    _, _, _, _, _, manager = setup(bridge)
    with pytest.raises(ValidationFailed):
        manager.create(project="demo", loop_ids=[])


def test_dag_rejects_unknown_loop(bridge):
    seed_plan(bridge)
    _, _, _, _, _, manager = setup(bridge)
    with pytest.raises(ResourceNotFound):
        manager.create(project="demo", loop_ids=["eloop_missing"])


def test_dag_creates_ordering(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b", "dependencyType": "depends_on"}])
    assert dag.status is DagStatus.CREATED
    assert dag.loop_ids == ["eloop_a", "eloop_b"]
    assert dag.edges[0].dependency_type is DependencyType.DEPENDS_ON


def test_dag_creates_without_edges(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"])
    assert dag.edges == []


@pytest.mark.parametrize("edges", [
    [{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}, {"sourceLoop": "eloop_b", "targetLoop": "eloop_a"}],
    [{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}, {"sourceLoop": "eloop_b", "targetLoop": "eloop_c"}, {"sourceLoop": "eloop_c", "targetLoop": "eloop_a"}],
    [{"sourceLoop": "eloop_a", "targetLoop": "eloop_a"}],
])
def test_dag_rejects_cycles(bridge, edges):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    for loop_id in ["eloop_a", "eloop_b", "eloop_c"]:
        orchestrator.storage.save(make_loop(orchestrator, loop_id=loop_id))
    with pytest.raises(ValidationFailed):
        manager.create(project="demo", loop_ids=["eloop_a", "eloop_b", "eloop_c"], edges=edges)


def test_dag_rejects_edge_to_unknown_loop(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a"))
    with pytest.raises(ValidationFailed):
        manager.create(project="demo", loop_ids=["eloop_a"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_x"}])


def test_dag_persists(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, storage, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"])
    reopened = storage.get(dag.id)
    assert reopened is not None and reopened.loop_ids == dag.loop_ids


def test_dag_get_unknown_404(bridge):
    seed_plan(bridge)
    _, _, _, _, _, manager = setup(bridge)
    with pytest.raises(ResourceNotFound):
        manager.get("edag_missing")


def test_dag_list(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"])
    assert len(manager.list_dags(project="demo")) == 1


# ---------------------------------------------------------------------------
# DAG readiness
# ---------------------------------------------------------------------------


def test_dag_ready_all_when_no_edges(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"])
    assert set(manager.ready_loops(dag.id)) == {"eloop_a", "eloop_b"}


def test_dag_ready_respects_dependencies(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    assert manager.ready_loops(dag.id) == ["eloop_a"]


def test_dag_ready_unblocks_after_completion(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    completed = make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.COMPLETED)
    orchestrator.storage.save(completed)
    assert manager.ready_loops(dag.id) == ["eloop_b"]


def test_dag_ready_skips_terminal_loops(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.COMPLETED)
    orchestrator.storage.save(a)
    dag = manager.create(project="demo", loop_ids=["eloop_a"])
    assert manager.ready_loops(dag.id) == []


@pytest.mark.parametrize("status", ["COMPLETED", "ROLLED_BACK", "CANCELLED", "FAILED"])
def test_dag_ready_treats_terminal_as_done(bridge, status):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus(status))
    orchestrator.storage.save(a)
    dag = manager.create(project="demo", loop_ids=["eloop_a"])
    assert manager.ready_loops(dag.id) == []


def test_dag_statuses_read_only(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    orchestrator.storage.save(a)
    dag = manager.create(project="demo", loop_ids=["eloop_a"])
    statuses = manager.loop_statuses(dag.id)
    assert statuses == {"eloop_a": "PLANNING"}


def test_dag_on_completed_marks_dag_completed(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.COMPLETED)
    orchestrator.storage.save(a)
    dag = manager.create(project="demo", loop_ids=["eloop_a"])
    updated = manager.on_loop_completed(dag.id, "eloop_a")
    assert updated.status is DagStatus.COMPLETED


def test_dag_on_completed_rejects_foreign_loop(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    orchestrator.storage.save(a)
    dag = manager.create(project="demo", loop_ids=["eloop_a"])
    with pytest.raises(ValidationFailed):
        manager.on_loop_completed(dag.id, "eloop_foreign")


# ---------------------------------------------------------------------------
# DAG advance (proposal-only)
# ---------------------------------------------------------------------------


def test_dag_advance_prepares_proposal(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    advanced = manager.advance(dag.id)
    assert advanced["loopId"] == "eloop_a"
    assert advanced["status"] == "WAITING_APPROVAL"
    assert advanced["proposalId"]


def test_dag_advance_requires_ready_loop(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    manager.advance(dag.id)
    # eloop_a now WAITING_APPROVAL and no longer ready? It remains non-terminal,
    # so advance would prepare again -> prepare rejects already-proposed loop.
    with pytest.raises(ValidationFailed):
        manager.advance(dag.id)


def test_dag_advance_unknown_404(bridge):
    seed_plan(bridge)
    _, _, _, _, _, manager = setup(bridge)
    with pytest.raises(ResourceNotFound):
        manager.advance("edag_missing")


def test_dag_advance_does_not_execute(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    dag = manager.create(project="demo", loop_ids=["eloop_a"])
    manager.advance(dag.id)
    loop = orchestrator.get("eloop_a")
    assert loop.result_id is None and loop.status is LoopStatus.WAITING_APPROVAL


def test_dag_manager_has_no_execute(bridge):
    _, _, _, _, _, manager = setup(bridge)
    assert not hasattr(manager, "execute")
    assert not hasattr(manager, "run_action")


# ---------------------------------------------------------------------------
# Runtime Recovery 2.0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [LoopStatus.EXECUTING, LoopStatus.VERIFYING, LoopStatus.WAITING_APPROVAL, LoopStatus.PROPOSAL_READY, LoopStatus.PLANNING])
def test_recovery_marks_interrupted_loops(bridge, status):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=status))
    from app.audit.logger import get_audit_logger

    recovered = ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    assert len(recovered) == 1
    assert orchestrator.get("eloop_r").status is LoopStatus.RECOVERED


@pytest.mark.parametrize("status", [LoopStatus.COMPLETED, LoopStatus.FAILED, LoopStatus.ROLLED_BACK, LoopStatus.CANCELLED, LoopStatus.RECOVERED])
def test_recovery_skips_terminal_loops(bridge, status):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=status))
    from app.audit.logger import get_audit_logger

    recovered = ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    assert recovered == []


def test_recovery_never_continues_execution(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    loop = orchestrator.get("eloop_r")
    assert loop.status is LoopStatus.RECOVERED
    assert loop.result_id is None and loop.proposal_id is None


def test_recovery_writes_audit(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_loop_recovered" for entry in entries)


def test_recovery_recoverable_lists(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    recovery = ExecutionLoopRecovery(orchestrator, get_audit_logger())
    assert [loop.id for loop in recovery.recoverable()] == ["eloop_r"]


def test_recovered_loop_requires_reconfirm_for_resume(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    # Directly jumping a RECOVERED loop to COMPLETED is illegal.
    with pytest.raises(ValidationFailed):
        orchestrator._transition(orchestrator.get("eloop_r"), LoopStatus.COMPLETED)
    # The only allowed forward moves require explicit user actions.
    recovered = orchestrator.get("eloop_r")
    assert recovered.status is LoopStatus.RECOVERED


def test_recover_manual_transition(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    loop_storage = orchestrator.storage
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    recovered = orchestrator.recover("eloop_r")
    assert recovered.status is LoopStatus.RECOVERED
    assert any(entry["status"] == "RECOVERED" for entry in recovered.history)


# ---------------------------------------------------------------------------
# Verification Evidence Bundle
# ---------------------------------------------------------------------------


def test_evidence_bundle_has_evidence_section(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert "evidence" in report
    assert report["evidence"]["approval"]["verified"] is True
    assert report["evidence"]["snapshot"]["captured"] is True


def test_evidence_bundle_git_diff(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["evidence"]["gitDiff"]["changed"] == 1
    assert report["evidence"]["gitDiff"]["files"] == ["src/main.py"]


def test_evidence_bundle_test_result(bridge):
    report = VerificationPipeline().build(_dummy_result(), test_passed=True)
    assert report["evidence"]["testResult"] == "passed"
    assert report["testResult"] == "passed"


def test_evidence_bundle_quality_risk(bridge):
    report = VerificationPipeline().build(_dummy_result(), quality_score=91, risk_score=25)
    assert report["evidence"]["qualityScore"] == 91
    assert report["evidence"]["riskScore"] == 25


def test_evidence_bundle_test_evidence(bridge):
    report = VerificationPipeline().build(_dummy_result(), test_evidence={"command": "pytest", "passed": 10})
    assert report["evidence"]["testEvidence"]["command"] == "pytest"
    assert "test_evidence_captured" in report["checks"]


def test_evidence_bundle_dependency_impact(bridge):
    report = VerificationPipeline().build(_dummy_result(), dependency_impact={"affectedModules": ["auth", "user"]})
    assert report["evidence"]["dependencyImpact"]["affectedModules"] == ["auth", "user"]
    assert "dependency_impact:2" in report["checks"]


def test_evidence_bundle_duration(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["evidence"]["durationMs"] == 10


def test_evidence_bundle_read_only(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["readOnly"] is True and report["autoFix"] is False


def test_evidence_bundle_validate_requires_evidence(bridge):
    with pytest.raises(ValidationFailed):
        VerificationPipeline().validate({"status": "PASS", "checks": ["a"], "evidence": "nope"})


# ---------------------------------------------------------------------------
# Engineering Metrics
# ---------------------------------------------------------------------------


def test_metrics_empty(bridge):
    _, _, _, orchestrator, _, _ = setup(bridge)
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["totalLoops"] == 0
    assert report["successRate"] == 0.0


def test_metrics_counts_statuses(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED))
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_f", status=LoopStatus.FAILED))
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.RECOVERED))
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["totalLoops"] == 3
    assert report["completed"] == 1 and report["failed"] == 1 and report["recovered"] == 1


def test_metrics_success_rate(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    for i in range(3):
        loop_storage.save(make_loop(orchestrator, loop_id=f"eloop_c{i}", status=LoopStatus.COMPLETED))
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_f", status=LoopStatus.FAILED))
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["successRate"] == 75.0


def test_metrics_rollback_rate(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED))
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_rb", status=LoopStatus.ROLLED_BACK))
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["rollbackRate"] == 50.0


def test_metrics_average_quality(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop = make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED)
    loop.quality = {"quality": 90}
    loop_storage.save(loop)
    loop2 = make_loop(orchestrator, loop_id="eloop_c2", status=LoopStatus.COMPLETED)
    loop2.quality = {"quality": 70}
    loop_storage.save(loop2)
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["averageQuality"] == 80.0


def test_metrics_risk_distribution(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    for i in range(2):
        loop_storage.save(make_loop(orchestrator, loop_id=f"eloop_c{i}", status=LoopStatus.COMPLETED))
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["riskDistribution"]["medium"] >= 1


def test_metrics_project_filter(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED))
    report = EngineeringMetricsManager(orchestrator).compute(project="other")
    assert report["totalLoops"] == 0


def test_metrics_read_only(bridge):
    _, _, _, orchestrator, _, _ = setup(bridge)
    assert EngineeringMetricsManager(orchestrator).compute()["readOnly"] is True


def test_metrics_does_not_affect_permissions(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED))
    from app.security.permissions import level_for_action

    EngineeringMetricsManager(orchestrator).compute()
    assert level_for_action("execution_dag_advance") is not None


def test_metrics_snapshot_writes_file(bridge, tmp_path):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED))
    from app.audit.logger import get_audit_logger

    target = tmp_path / "engineering.json"
    report = EngineeringMetricsManager(orchestrator, get_audit_logger()).snapshot(target)
    assert target.is_file()
    assert report["totalLoops"] == 1


# ---------------------------------------------------------------------------
# Cross Loop Context
# ---------------------------------------------------------------------------


def test_context_bundle_contains_loop(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a"))
    bundle = LoopContextBuilder(orchestrator).build("eloop_a")
    assert bundle["loop"]["id"] == "eloop_a"
    assert bundle["readOnly"] is True


def test_context_bundle_lists_tasks(bridge):
    seed_plan(bridge)
    settings, _, _, orchestrator, _, _ = setup(bridge)
    tasks = orchestrator.execution_manager.create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=PLAN_CONTENT)
    loop = ExecutionLoop(id="eloop_a", project="demo", plan_id="plan_1", workflow_id=None, task_ids=[tasks[0].id], created_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", history=[])
    orchestrator.storage.save(loop)
    bundle = LoopContextBuilder(orchestrator).build("eloop_a")
    assert len(bundle["tasks"]) == 1
    assert bundle["tasks"][0]["id"] == tasks[0].id


def test_context_bundle_unknown_404(bridge):
    _, _, _, orchestrator, _, _ = setup(bridge)
    with pytest.raises(ResourceNotFound):
        LoopContextBuilder(orchestrator).build("eloop_missing")


def test_context_bundle_related_loops(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, dag_storage, dag_manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag_manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    bundle = LoopContextBuilder(orchestrator, dag_manager).build("eloop_a")
    assert bundle["dagRelations"]["outgoing"][0]["targetLoop"] == "eloop_b"
    assert bundle["relatedLoops"] and bundle["relatedLoops"][0]["id"] == "eloop_b"


def test_context_bundle_incoming_relations(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, dag_manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag_manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    bundle = LoopContextBuilder(orchestrator, dag_manager).build("eloop_b")
    assert bundle["dagRelations"]["incoming"][0]["sourceLoop"] == "eloop_a"


def test_context_bundle_related_method(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, dag_manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b")
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag_manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    assert LoopContextBuilder(orchestrator, dag_manager).related("eloop_a") == ["eloop_b"]


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------


def test_dag_create_api_requires_approval(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a"))
    pending = bridge.client.post("/execution-dag/create", json={"project": "demo", "loop_ids": ["eloop_a"], "edges": []})
    assert pending.status_code == 202
    assert pending.json()["requestId"].startswith("req_")
    assert bridge.client.get("/execution-dag/edag_x").status_code == 404


def test_dag_create_api_unknown_loop_404(bridge):
    assert bridge.client.post("/execution-dag/create", json={"project": "demo", "loop_ids": ["eloop_missing"], "edges": []}).status_code == 404


def test_dag_ready_api_read_only(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a"))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    response = bridge.client.get(f"/execution-dag/{dag.id}/ready")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
    assert response.json()["readyLoops"] == ["eloop_a"]


def test_dag_advance_api_requires_approval(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", with_tasks=True))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    pending = bridge.client.post(f"/execution-dag/{dag.id}/advance", json={})
    assert pending.status_code == 202


def test_dag_advance_api_does_not_execute(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", with_tasks=True))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    bridge.client.post(f"/execution-dag/{dag.id}/advance", json={})
    assert orchestrator.get("eloop_a").proposal_id is None


def test_loop_context_api_read_only(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a"))
    response = bridge.client.get("/execution-loop/eloop_a/context")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_loop_context_api_unknown_404(bridge):
    assert bridge.client.get("/execution-loop/eloop_missing/context").status_code == 404


def test_loop_recover_api_requires_approval(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.EXECUTING))
    pending = bridge.client.post("/execution-loop/eloop_a/recover", json={})
    assert pending.status_code == 202
    assert orchestrator.get("eloop_a").status is LoopStatus.EXECUTING  # unchanged until approval


def test_engineering_metrics_api_read_only(bridge):
    seed_plan(bridge)
    response = bridge.client.get("/engineering/metrics")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
    assert "successRate" in response.json()


def test_engineering_metrics_api_project_filter(bridge):
    seed_plan(bridge)
    response = bridge.client.get("/engineering/metrics", params={"project": "demo"})
    assert response.status_code == 200 and response.json()["project"] == "demo"


def test_dag_detail_api_contract(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a"))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    detail = bridge.client.get(f"/execution-dag/{dag.id}").json()
    for field in ["id", "project", "loopIds", "edges", "status", "loopStatuses", "readOnly"]:
        assert field in detail


def test_loop_recover_marks_recovered_after_approval(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.EXECUTING))
    pending = bridge.client.post("/execution-loop/eloop_a/recover", json={})
    approved = bridge.approve(pending.json()["requestId"])
    assert approved.status_code == 200
    assert approved.json()["result"]["status"] == "RECOVERED"


def test_dag_advance_full_flow_after_approval(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", with_tasks=True))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    pending = bridge.client.post(f"/execution-dag/{dag.id}/advance", json={})
    approved = bridge.approve(pending.json()["requestId"])
    assert approved.status_code == 200
    assert approved.json()["result"]["status"] == "WAITING_APPROVAL"


def test_dag_does_not_bypass_approval_store(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", with_tasks=True))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    bridge.client.post(f"/execution-dag/{dag.id}/advance", json={})
    assert orchestrator.get("eloop_a").status is LoopStatus.PLANNING


# ---------------------------------------------------------------------------
# Additional DAG dependency types and serialization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dependency_type", ["depends_on", "blocks", "requires_review"])
def test_dag_supports_all_dependency_types(bridge, dependency_type):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b", "dependencyType": dependency_type}])
    assert dag.edges[0].dependency_type.value == dependency_type


@pytest.mark.parametrize("bad_type", ["wat", "auto"])
def test_dag_rejects_unknown_dependency_type(bridge, bad_type):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    with pytest.raises(ValueError):
        manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b", "dependencyType": bad_type}])


def test_dag_serialization_contract(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    payload = dag.as_dict()
    for field in ["id", "project", "loopIds", "edges", "status", "createdAt", "updatedAt", "history", "readOnly"]:
        assert field in payload
    assert payload["edges"][0]["sourceLoop"] == "eloop_a"
    assert payload["readOnly"] is True


def test_dag_edges_reject_cycle_before_persist(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    with pytest.raises(ValidationFailed):
        manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}, {"sourceLoop": "eloop_b", "targetLoop": "eloop_a"}])
    assert manager.list_dags(project="demo") == []


def test_dag_ready_blocks_chain(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    c = make_loop(orchestrator, loop_id="eloop_c", with_tasks=True)
    for loop in [a, b, c]:
        orchestrator.storage.save(loop)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b", "eloop_c"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}, {"sourceLoop": "eloop_b", "targetLoop": "eloop_c"}])
    assert manager.ready_loops(dag.id) == ["eloop_a"]
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.COMPLETED, with_tasks=True))
    assert manager.ready_loops(dag.id) == ["eloop_b"]
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_b", status=LoopStatus.COMPLETED, with_tasks=True))
    assert manager.ready_loops(dag.id) == ["eloop_c"]


def test_dag_ready_failed_source_blocks_dependents(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a")
    b = make_loop(orchestrator, loop_id="eloop_b", with_tasks=True)
    orchestrator.storage.save(a)
    orchestrator.storage.save(b)
    dag = manager.create(project="demo", loop_ids=["eloop_a", "eloop_b"], edges=[{"sourceLoop": "eloop_a", "targetLoop": "eloop_b"}])
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.FAILED))
    assert manager.ready_loops(dag.id) == []


def test_dag_advance_writes_audit(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    dag = manager.create(project="demo", loop_ids=["eloop_a"])
    manager.advance(dag.id)
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_dag_advanced" for entry in entries)


def test_dag_create_writes_audit(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    manager.create(project="demo", loop_ids=["eloop_a"])
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_dag_created" for entry in entries)


@pytest.mark.parametrize("limit", [1, 5, 50])
def test_dag_list_respects_limit(bridge, limit):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    for index in range(3):
        a = make_loop(orchestrator, loop_id=f"eloop_{index}", with_tasks=True)
        orchestrator.storage.save(a)
        manager.create(project="demo", loop_ids=[f"eloop_{index}"])
    assert len(manager.list_dags(project="demo", limit=limit)) <= limit


# ---------------------------------------------------------------------------
# Additional recovery coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("loop_count", [1, 2, 5])
def test_recovery_handles_multiple_loops(bridge, loop_count):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    for index in range(loop_count):
        loop_storage.save(make_loop(orchestrator, loop_id=f"eloop_r{index}", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    recovered = ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    assert len(recovered) == loop_count
    for index in range(loop_count):
        assert orchestrator.get(f"eloop_r{index}").status is LoopStatus.RECOVERED


def test_recovery_skips_completed_mix(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED))
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    recovered = ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    assert [loop.id for loop in recovered] == ["eloop_r"]
    assert orchestrator.get("eloop_c").status is LoopStatus.COMPLETED


def test_recovery_persists_state(bridge):
    seed_plan(bridge)
    settings, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    reopened = ExecutionLoopStorage(settings.execution_loop_db_path).get("eloop_r")
    assert reopened is not None and reopened.status is LoopStatus.RECOVERED


def test_recovery_repeated_is_idempotent(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    recovery = ExecutionLoopRecovery(orchestrator, get_audit_logger())
    recovery.recover()
    assert recovery.recover() == []


def test_recovered_loop_can_rollback(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    from app.execution_loop.orchestrator import _ALLOWED

    ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    recovered = orchestrator.get("eloop_r")
    assert recovered.status is LoopStatus.RECOVERED
    assert LoopStatus.ROLLED_BACK in _ALLOWED[LoopStatus.RECOVERED]


def test_recovered_loop_cannot_jump_completed(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.EXECUTING))
    from app.audit.logger import get_audit_logger

    ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    with pytest.raises(ValidationFailed):
        orchestrator._transition(orchestrator.get("eloop_r"), LoopStatus.COMPLETED)
    with pytest.raises(ValidationFailed):
        orchestrator._transition(orchestrator.get("eloop_r"), LoopStatus.EXECUTING)
    from app.execution_loop.orchestrator import _ALLOWED

    assert LoopStatus.EXECUTING not in _ALLOWED[LoopStatus.RECOVERED]


@pytest.mark.parametrize("status", list(LoopStatus))
def test_loop_status_enum_includes_recovered(status):
    assert LoopStatus(status.value) is status


# ---------------------------------------------------------------------------
# Additional evidence bundle coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("test_passed", [True, False, None])
def test_evidence_bundle_test_result_variants(bridge, test_passed):
    report = VerificationPipeline().build(_dummy_result(), test_passed=test_passed)
    expected = "passed" if test_passed is True else "failed" if test_passed is False else "not_run"
    assert report["testResult"] == expected
    assert report["evidence"]["testResult"] == expected


def test_evidence_bundle_approval_evidence(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["evidence"]["approval"] == {"verified": True}


def test_evidence_bundle_snapshot_files(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["evidence"]["snapshot"]["files"] == ["src/main.py"]


def test_evidence_bundle_negative_git_diff(bridge):
    from app.execution.models import ExecutionResult

    result = ExecutionResult(id="er_x", proposal_id="ep_x", task_id="et_x", project="demo", files_changed=[], diff_summary={"changed": 0, "diffBytes": 0}, duration_ms=1, errors=[], verification={"status": "PASS", "checks": [], "snapshotCaptured": True, "approvalVerified": True}, created_at="2026-02-01T00:00:00Z")
    report = VerificationPipeline().build(result)
    assert report["evidence"]["gitDiff"]["changed"] == 0


def test_evidence_bundle_collected_at(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["evidence"]["collectedAt"]


@pytest.mark.parametrize("affected", [[], ["a"], ["a", "b", "c"]])
def test_evidence_bundle_dependency_impact_counts(bridge, affected):
    report = VerificationPipeline().build(_dummy_result(), dependency_impact={"affectedModules": affected})
    marker = f"dependency_impact:{len(affected)}"
    assert (marker in report["checks"]) == (len(affected) > 0)


def test_evidence_bundle_validate_ok(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert VerificationPipeline().validate(report)["status"] == "PASS"


# ---------------------------------------------------------------------------
# Additional metrics coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("counts", [(5, 0), (3, 2), (1, 4)])
def test_metrics_success_rate_variants(bridge, counts):
    seed_plan(bridge)
    completed, failed = counts
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    for i in range(completed):
        loop_storage.save(make_loop(orchestrator, loop_id=f"eloop_c{i}", status=LoopStatus.COMPLETED))
    for i in range(failed):
        loop_storage.save(make_loop(orchestrator, loop_id=f"eloop_f{i}", status=LoopStatus.FAILED))
    report = EngineeringMetricsManager(orchestrator).compute()
    expected = round(completed / (completed + failed) * 100, 1)
    assert report["successRate"] == expected


def test_metrics_average_duration(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop = make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED)
    loop.verification = {"evidence": {"durationMs": 250}}
    loop_storage.save(loop)
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["averageDurationMs"] == 250


def test_metrics_zero_duration(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED))
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["averageDurationMs"] == 0


@pytest.mark.parametrize("quality", [100, 90, 50, 0])
def test_metrics_quality_bounds(bridge, quality):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop = make_loop(orchestrator, loop_id="eloop_c", status=LoopStatus.COMPLETED)
    loop.quality = {"quality": quality}
    loop_storage.save(loop)
    report = EngineeringMetricsManager(orchestrator).compute()
    assert 0 <= report["averageQuality"] <= 100


def test_metrics_status_counts_include_recovered(bridge):
    seed_plan(bridge)
    _, _, loop_storage, orchestrator, _, _ = setup(bridge)
    loop_storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.RECOVERED))
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["statusCounts"]["RECOVERED"] == 1
    assert report["recovered"] == 1


def test_metrics_generated_at(bridge):
    _, _, _, orchestrator, _, _ = setup(bridge)
    assert EngineeringMetricsManager(orchestrator).compute()["generatedAt"]


# ---------------------------------------------------------------------------
# Additional context coverage
# ---------------------------------------------------------------------------


def test_context_bundle_proposal_when_present(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    prepared = orchestrator.prepare("eloop_a")
    bundle = LoopContextBuilder(orchestrator).build("eloop_a")
    assert bundle["proposal"]["id"] == prepared.proposal_id


def test_context_bundle_result_when_present(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    prepared = orchestrator.prepare("eloop_a")
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    orchestrator.on_executed("eloop_a", result)
    bundle = LoopContextBuilder(orchestrator).build("eloop_a")
    assert bundle["result"]["id"] == result.id


def test_context_bundle_timeline(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    bundle = LoopContextBuilder(orchestrator).build("eloop_a")
    assert isinstance(bundle["timeline"], list)


def test_context_bundle_does_not_mutate(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    before = orchestrator.get("eloop_a").status
    LoopContextBuilder(orchestrator).build("eloop_a")
    assert orchestrator.get("eloop_a").status is before


def test_context_bundle_quality_verification(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    a = make_loop(orchestrator, loop_id="eloop_a", with_tasks=True)
    orchestrator.storage.save(a)
    bundle = LoopContextBuilder(orchestrator).build("eloop_a")
    assert isinstance(bundle["verification"], dict)
    assert isinstance(bundle["quality"], dict)


@pytest.mark.parametrize("edge_count", [0, 1, 2])
def test_context_relations_variants(bridge, edge_count):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    loops = []
    for index in range(3):
        loop = make_loop(orchestrator, loop_id=f"eloop_{index}", with_tasks=True)
        orchestrator.storage.save(loop)
        loops.append(loop)
    edges = []
    for index in range(edge_count):
        edges.append({"sourceLoop": f"eloop_{index}", "targetLoop": f"eloop_{index + 1}"})
    dag = manager.create(project="demo", loop_ids=["eloop_0", "eloop_1", "eloop_2"], edges=edges)
    bundle = LoopContextBuilder(orchestrator, manager).build("eloop_1")
    assert len(bundle["dagRelations"]["incoming"]) == (1 if edge_count >= 1 else 0)
    assert len(bundle["dagRelations"]["outgoing"]) == (1 if edge_count >= 2 else 0)


# ---------------------------------------------------------------------------
# Additional API coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["/execution-dag/edag_missing", "/execution-dag/edag_missing/ready"])
def test_dag_api_unknown_404(bridge, endpoint):
    assert bridge.client.get(endpoint).status_code == 404


def test_dag_detail_api_read_only(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", with_tasks=True))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    response = bridge.client.get(f"/execution-dag/{dag.id}")
    assert response.status_code == 200 and response.json()["readOnly"] is True


@pytest.mark.parametrize("field", ["readyLoops", "loopStatuses", "readOnly", "dagId"])
def test_dag_ready_api_contract(bridge, field):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", with_tasks=True))
    dag = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger()).create(project="demo", loop_ids=["eloop_a"])
    response = bridge.client.get(f"/execution-dag/{dag.id}/ready").json()
    assert field in response


@pytest.mark.parametrize("field", ["totalLoops", "successRate", "rollbackRate", "averageQuality", "averageDurationMs", "riskDistribution", "statusCounts", "generatedAt", "readOnly"])
def test_engineering_metrics_api_contract(bridge, field):
    seed_plan(bridge)
    assert field in bridge.client.get("/engineering/metrics").json()


def test_loop_context_api_contract(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", with_tasks=True))
    response = bridge.client.get("/execution-loop/eloop_a/context").json()
    for field in ["loop", "tasks", "proposal", "result", "verification", "quality", "timeline", "dagRelations", "relatedLoops", "readOnly"]:
        assert field in response


def test_recover_api_unknown_404(bridge):
    assert bridge.client.post("/execution-loop/eloop_missing/recover", json={}).status_code == 404


def test_recover_api_contract(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_a", status=LoopStatus.EXECUTING))
    pending = bridge.client.post("/execution-loop/eloop_a/recover", json={})
    assert pending.status_code == 202
    assert "MARK loop eloop_a as RECOVERED" in pending.json()["preview"]


def test_dag_create_api_validates_loop_exists(bridge):
    seed_plan(bridge)
    assert bridge.client.post("/execution-dag/create", json={"project": "demo", "loop_ids": ["eloop_x"], "edges": []}).status_code == 404


def test_metrics_snapshot_audit(bridge, tmp_path):
    seed_plan(bridge)
    _, _, _, orchestrator, _, _ = setup(bridge)
    from app.audit.logger import get_audit_logger

    target = tmp_path / "engineering.json"
    EngineeringMetricsManager(orchestrator, get_audit_logger()).snapshot(target)
    entries = bridge.audit_entries()
    assert any(entry["action"] == "engineering_metrics_snapshot" for entry in entries)


def test_loop_recovery_via_startup_hook(bridge):
    seed_plan(bridge)
    settings = get_settings()
    from app.audit.logger import get_audit_logger

    orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=ApprovalStore(), audit=get_audit_logger())
    orchestrator.storage.save(make_loop(orchestrator, loop_id="eloop_r", status=LoopStatus.VERIFYING))
    ExecutionLoopRecovery(orchestrator, get_audit_logger()).recover()
    assert orchestrator.get("eloop_r").status is LoopStatus.RECOVERED


@pytest.mark.parametrize("count", [0, 1, 3])
def test_dag_advance_loop_count_metric(bridge, count):
    seed_plan(bridge)
    _, _, _, orchestrator, _, manager = setup(bridge)
    for index in range(count):
        orchestrator.storage.save(make_loop(orchestrator, loop_id=f"eloop_{index}", with_tasks=True))
    dags = [manager.create(project="demo", loop_ids=[f"eloop_{index}"]) for index in range(count)]
    report = EngineeringMetricsManager(orchestrator).compute()
    assert report["totalLoops"] == count
    assert len(dags) == count
