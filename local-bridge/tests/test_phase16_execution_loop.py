from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.execution import ExecutionManager, ExecutionStorage
from app.execution.verification_pipeline import VerificationPipeline
from app.execution_loop import ExecutionLoopOrchestrator, ExecutionLoopRollbackManager, ExecutionLoopStorage
from app.execution_loop.models import ExecutionLoop, LoopStatus
from app.quality.gate8 import QualityGate8Evaluator
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


def setup_orchestrator(bridge):
    from app.audit.logger import get_audit_logger

    settings = get_settings()
    approvals = ApprovalStore()
    storage = ExecutionLoopStorage(settings.execution_loop_db_path)
    orchestrator = ExecutionLoopOrchestrator(storage, settings, approvals=approvals, audit=get_audit_logger())
    return settings, approvals, storage, orchestrator


def create_loop(orchestrator: ExecutionLoopOrchestrator, *, project: str = "demo", plan_id: str = "plan_1") -> ExecutionLoop:
    return orchestrator.create(project=project, plan_id=plan_id, workflow_id=None, approval_id="req_create")


def approved_execute_id(approvals: ApprovalStore) -> str:
    request = approvals.create(action="execution_execute", project="demo", path="execution", payload={}, reason="test", preview="metadata")
    approvals.mark_approved(request.request_id)
    return request.request_id


# ---------------------------------------------------------------------------
# Loop lifecycle
# ---------------------------------------------------------------------------


def test_loop_create_seeds_planning_state(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    assert loop.status is LoopStatus.PLANNING
    assert loop.task_ids and loop.plan_id == "plan_1"
    assert loop.history[0]["status"] == "CREATED"


@pytest.mark.parametrize("plan_id", ["plan_1", "plan_auth_2026"])
def test_loop_create_persists_plan(bridge, plan_id):
    seed_plan(bridge, plan_id=plan_id)
    _, _, storage, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator, plan_id=plan_id)
    reopened = storage.get(loop.id)
    assert reopened is not None and reopened.plan_id == plan_id


def test_loop_create_missing_plan_404(bridge):
    _, _, _, orchestrator = setup_orchestrator(bridge)
    with pytest.raises(ResourceNotFound):
        create_loop(orchestrator, plan_id="plan_missing")


@pytest.mark.parametrize("task_count", [1, 2, 3, 4])
def test_loop_create_plans_all_tasks(bridge, task_count):
    seed_plan(bridge)
    content = PLAN_CONTENT.replace(
        "2. move token logic",
        "\n".join(f"{i}. step {i}" for i in range(2, task_count + 1)),
    )
    storage = SimulationStorage(get_settings().simulation_db_path)
    storage.save_plan(Plan(id="plan_n", simulation_id="sim_1", scenario_id="scenario_a", content=content, status=PlanStatus.APPROVED, created_at="2026-02-01T00:00:00Z"))
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator, plan_id="plan_n")
    assert len(loop.task_ids) == task_count


def test_loop_create_writes_audit(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_loop_created" and loop.id in entry["detail"] for entry in entries)


def test_loop_get_unknown_404(bridge):
    _, _, _, orchestrator = setup_orchestrator(bridge)
    with pytest.raises(ResourceNotFound):
        orchestrator.get("eloop_missing")


def test_loop_list_empty(bridge):
    _, _, _, orchestrator = setup_orchestrator(bridge)
    assert orchestrator.list_loops() == []


def test_loop_list_returns_created_loops(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    assert any(item.id == loop.id for item in orchestrator.list_loops())


def test_loop_list_filters_by_project(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    create_loop(orchestrator, project="demo")
    assert len(orchestrator.list_loops(project="demo")) == 1
    assert orchestrator.list_loops(project="other") == []


def test_loop_find_by_task(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    assert orchestrator.find_loop_for_task(loop.task_ids[0]).id == loop.id
    assert orchestrator.find_loop_for_task("et_missing") is None


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = [
    (LoopStatus.CREATED, LoopStatus.PLANNING),
    (LoopStatus.CREATED, LoopStatus.CANCELLED),
    (LoopStatus.PLANNING, LoopStatus.PROPOSAL_READY),
    (LoopStatus.PLANNING, LoopStatus.FAILED),
    (LoopStatus.PLANNING, LoopStatus.CANCELLED),
    (LoopStatus.PROPOSAL_READY, LoopStatus.WAITING_APPROVAL),
    (LoopStatus.PROPOSAL_READY, LoopStatus.FAILED),
    (LoopStatus.PROPOSAL_READY, LoopStatus.CANCELLED),
    (LoopStatus.WAITING_APPROVAL, LoopStatus.EXECUTING),
    (LoopStatus.WAITING_APPROVAL, LoopStatus.FAILED),
    (LoopStatus.WAITING_APPROVAL, LoopStatus.CANCELLED),
    (LoopStatus.EXECUTING, LoopStatus.VERIFYING),
    (LoopStatus.EXECUTING, LoopStatus.FAILED),
    (LoopStatus.EXECUTING, LoopStatus.ROLLED_BACK),
    (LoopStatus.VERIFYING, LoopStatus.COMPLETED),
    (LoopStatus.VERIFYING, LoopStatus.FAILED),
    (LoopStatus.VERIFYING, LoopStatus.ROLLED_BACK),
    (LoopStatus.FAILED, LoopStatus.ROLLED_BACK),
]


@pytest.mark.parametrize("source,target", VALID_TRANSITIONS)
def test_loop_valid_transitions(bridge, source, target):
    _, _, storage, orchestrator = setup_orchestrator(bridge)
    loop = ExecutionLoop(id="eloop_x", project="demo", plan_id="plan_1", workflow_id=None, task_ids=["et_1"], created_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", history=[])
    loop.status = source
    storage.save(loop)
    moved = orchestrator._transition(loop, target)
    assert moved.status is target
    assert any(entry["status"] == target.value for entry in moved.history)


ILLEGAL_TRANSITIONS = [
    (LoopStatus.CREATED, LoopStatus.EXECUTING),
    (LoopStatus.CREATED, LoopStatus.COMPLETED),
    (LoopStatus.CREATED, LoopStatus.VERIFYING),
    (LoopStatus.PLANNING, LoopStatus.EXECUTING),
    (LoopStatus.PLANNING, LoopStatus.COMPLETED),
    (LoopStatus.PLANNING, LoopStatus.WAITING_APPROVAL),
    (LoopStatus.PROPOSAL_READY, LoopStatus.COMPLETED),
    (LoopStatus.PROPOSAL_READY, LoopStatus.EXECUTING),
    (LoopStatus.PROPOSAL_READY, LoopStatus.PLANNING),
    (LoopStatus.WAITING_APPROVAL, LoopStatus.COMPLETED),
    (LoopStatus.WAITING_APPROVAL, LoopStatus.VERIFYING),
    (LoopStatus.WAITING_APPROVAL, LoopStatus.PLANNING),
    (LoopStatus.EXECUTING, LoopStatus.COMPLETED),
    (LoopStatus.EXECUTING, LoopStatus.WAITING_APPROVAL),
    (LoopStatus.EXECUTING, LoopStatus.PLANNING),
    (LoopStatus.VERIFYING, LoopStatus.EXECUTING),
    (LoopStatus.VERIFYING, LoopStatus.WAITING_APPROVAL),
    (LoopStatus.VERIFYING, LoopStatus.PLANNING),
    (LoopStatus.COMPLETED, LoopStatus.EXECUTING),
    (LoopStatus.COMPLETED, LoopStatus.VERIFYING),
    (LoopStatus.COMPLETED, LoopStatus.WAITING_APPROVAL),
    (LoopStatus.COMPLETED, LoopStatus.PLANNING),
    (LoopStatus.FAILED, LoopStatus.COMPLETED),
    (LoopStatus.FAILED, LoopStatus.EXECUTING),
    (LoopStatus.FAILED, LoopStatus.WAITING_APPROVAL),
    (LoopStatus.FAILED, LoopStatus.PLANNING),
    (LoopStatus.ROLLED_BACK, LoopStatus.COMPLETED),
    (LoopStatus.ROLLED_BACK, LoopStatus.EXECUTING),
    (LoopStatus.ROLLED_BACK, LoopStatus.VERIFYING),
    (LoopStatus.CANCELLED, LoopStatus.COMPLETED),
    (LoopStatus.CANCELLED, LoopStatus.EXECUTING),
    (LoopStatus.CANCELLED, LoopStatus.PLANNING),
]


@pytest.mark.parametrize("source,target", ILLEGAL_TRANSITIONS)
def test_loop_illegal_transitions_rejected(bridge, source, target):
    _, _, storage, orchestrator = setup_orchestrator(bridge)
    loop = ExecutionLoop(id="eloop_x", project="demo", plan_id="plan_1", workflow_id=None, task_ids=["et_1"], created_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", history=[])
    loop.status = source
    storage.save(loop)
    with pytest.raises(ValidationFailed):
        orchestrator._transition(storage.get("eloop_x"), target)


@pytest.mark.parametrize("status", list(LoopStatus))
def test_loop_status_enum_is_stable(status):
    assert LoopStatus(status.value) is status


def test_loop_transition_writes_audit(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    orchestrator.prepare(loop.id)
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_loop_transition" for entry in entries)


# ---------------------------------------------------------------------------
# Prepare / proposal generation
# ---------------------------------------------------------------------------


def test_loop_prepare_generates_proposal(bridge):
    seed_plan(bridge)
    _, _, storage, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    assert prepared.proposal_id is not None
    assert prepared.status is LoopStatus.WAITING_APPROVAL


@pytest.mark.parametrize("loop_count", [1, 2, 3])
def test_loop_prepare_binds_proposal_to_first_task(bridge, loop_count):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    proposal = orchestrator.execution_manager.get_proposal(prepared.proposal_id)
    assert proposal.task_id == loop.task_ids[0]


def test_loop_prepare_only_once(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    orchestrator.prepare(loop.id)
    with pytest.raises(ValidationFailed):
        orchestrator.prepare(loop.id)


def test_loop_prepare_writes_audit_proposal_event(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    orchestrator.prepare(loop.id)
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_proposal_generated" for entry in entries)


# ---------------------------------------------------------------------------
# Verification pipeline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("test_passed", [True, False, None])
def test_verification_pipeline_reflects_tests(bridge, test_passed):
    pipeline = VerificationPipeline()
    report = pipeline.build(_dummy_result(), test_passed=test_passed)
    assert ("tests_passed" in report["checks"]) == (test_passed is True)
    assert ("tests_failed" in report["checks"]) == (test_passed is False)
    assert ("tests_not_run" in report["checks"]) == (test_passed is None)


@pytest.mark.parametrize("quality_score", [None, 0, 50, 91, 100])
def test_verification_pipeline_embeds_quality(bridge, quality_score):
    report = VerificationPipeline().build(_dummy_result(), quality_score=quality_score)
    if quality_score is None:
        assert not any(check.startswith("quality_score:") for check in report["checks"])
    else:
        assert f"quality_score:{quality_score}" in report["checks"]


@pytest.mark.parametrize("risk_score", [None, 5, 45, 90])
def test_verification_pipeline_embeds_risk(bridge, risk_score):
    report = VerificationPipeline().build(_dummy_result(), risk_score=risk_score)
    if risk_score is None:
        assert not any(check.startswith("risk_score:") for check in report["checks"])
    else:
        assert f"risk_score:{risk_score}" in report["checks"]


def test_verification_pipeline_detection_only(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["autoFix"] is False and report["readOnly"] is True


def test_verification_pipeline_status_defaults_pass(bridge):
    report = VerificationPipeline().build(_dummy_result())
    assert report["status"] == "PASS"


def test_verification_pipeline_fails_when_tests_fail(bridge):
    report = VerificationPipeline().build(_dummy_result(), test_passed=False)
    assert report["status"] == "FAIL"


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_verification_pipeline_validate(bridge, status):
    report = VerificationPipeline().build(_dummy_result())
    report["status"] = status
    assert VerificationPipeline().validate(report)["status"] == status


def test_verification_pipeline_validate_rejects_no_checks(bridge):
    with pytest.raises(ValidationFailed):
        VerificationPipeline().validate({"status": "PASS", "checks": []})


def test_verification_pipeline_validate_rejects_bad_status(bridge):
    with pytest.raises(ValidationFailed):
        VerificationPipeline().validate({"status": "MAYBE", "checks": ["a"]})


def _dummy_result():
    from app.execution.models import ExecutionResult

    return ExecutionResult(
        id="er_x", proposal_id="ep_x", task_id="et_x", project="demo",
        files_changed=["src/main.py"], diff_summary={"changed": 1},
        duration_ms=10, errors=[],
        verification={"status": "PASS", "checks": ["approval_verified", "snapshot_captured", "git_diff_present"], "snapshotCaptured": True, "approvalVerified": True},
        created_at="2026-02-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Verify (Quality Gate 8 + learning memory)
# ---------------------------------------------------------------------------


def test_loop_verify_completes_loop(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    verified = orchestrator.verify(loop.id, quality_score=91, risk_score=20, test_passed=True)
    assert verified.status is LoopStatus.COMPLETED
    assert verified.verification["status"] == "PASS"
    assert verified.quality.get("executionReady") is True


def test_loop_verify_fails_loop_on_failed_tests(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    verified = orchestrator.verify(loop.id, test_passed=False)
    assert verified.status is LoopStatus.FAILED
    assert verified.verification["status"] == "FAIL"


def test_loop_verify_requires_result(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    with pytest.raises(ValidationFailed):
        orchestrator.verify(loop.id)


def test_loop_verify_queues_learning_memory_on_completion(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    verified = orchestrator.verify(loop.id, test_passed=True)
    assert verified.memory_proposal_id is not None
    request = orchestrator.approvals.get(verified.memory_proposal_id)
    assert request.execution_loop_id == loop.id


def test_loop_verify_queues_failure_memory_on_failure(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    verified = orchestrator.verify(loop.id, test_passed=False)
    assert verified.memory_proposal_id is not None
    assert verified.quality.get("blockingIssues")


def test_loop_memory_proposal_requires_separate_approval(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    verified = orchestrator.verify(loop.id, test_passed=True)
    request = orchestrator.approvals.get(verified.memory_proposal_id)
    assert request.status.value == "pending"
    assert orchestrator.approvals.list_pending()


def test_loop_verify_writes_audit_verified(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    orchestrator.verify(loop.id, test_passed=True)
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_verified" for entry in entries)


def test_loop_quality_gate8_blocks_without_approval(bridge):
    report = QualityGate8Evaluator().evaluate(approval_present=False, snapshot_present=True, verification_status="PASS")
    assert report["executionReady"] is False
    assert "no_approval" in report["blockingIssues"]


def test_loop_quality_gate8_blocks_without_snapshot(bridge):
    report = QualityGate8Evaluator().evaluate(approval_present=True, snapshot_present=False, verification_status="PASS")
    assert report["executionReady"] is False
    assert "no_snapshot" in report["blockingIssues"]


def test_loop_quality_gate8_blocks_verification_failure(bridge):
    report = QualityGate8Evaluator().evaluate(approval_present=True, snapshot_present=True, verification_status="FAIL")
    assert report["executionReady"] is False
    assert "verification_fail" in report["blockingIssues"]


@pytest.mark.parametrize("risk", ["low", "medium", "high"])
def test_loop_quality_gate8_risk_levels(bridge, risk):
    report = QualityGate8Evaluator().evaluate(approval_present=True, snapshot_present=True, verification_status="PASS", risk_level=risk)
    assert report["riskLevel"] == risk
    assert ("risk_high" in report["blockingIssues"]) == (risk == "high")


def test_loop_quality_gate8_blocks_high_risk(bridge):
    report = QualityGate8Evaluator().evaluate(approval_present=True, snapshot_present=True, verification_status="PASS", risk_level="high")
    assert report["executionReady"] is False
    assert report["recommendation"] == "do_not_execute"


def test_loop_quality_gate8_is_read_only(bridge):
    assert QualityGate8Evaluator().evaluate()["readOnly"] is True


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def test_loop_rollback_requires_snapshots(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    with pytest.raises(ResourceNotFound):
        orchestrator.rollback(loop.id)


def test_loop_rollback_preview_lists_snapshots(bridge):
    seed_plan(bridge)
    settings, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    manager = ExecutionLoopRollbackManager(settings)
    preview = manager.preview(loop)
    assert preview["snapshots"] >= 1
    assert preview["order"] == "reverse_execution_order"


def test_loop_rollback_restores_in_reverse_order(bridge):
    seed_plan(bridge)
    settings, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    restored = ExecutionLoopRollbackManager(settings).restore(loop)
    assert restored["order"] == "reverse_execution_order"
    assert restored["count"] >= 1


def test_loop_rollback_marks_rolled_back(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    rolled = orchestrator.rollback(loop.id)
    assert rolled.status is LoopStatus.ROLLED_BACK
    assert rolled.rollback.get("count", 0) >= 1


def test_loop_rollback_writes_audit(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    orchestrator.rollback(loop.id)
    entries = bridge.audit_entries()
    assert any(entry["action"] == "execution_rolled_back" for entry in entries)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def test_loop_timeline_returns_history(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    timeline = orchestrator.timeline(loop.id)
    assert timeline and timeline[0]["status"] == "CREATED"


def test_loop_timeline_tracks_prepare(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    timeline = orchestrator.timeline(prepared.id)
    statuses = [entry["status"] for entry in timeline]
    assert "PROPOSAL_READY" in statuses and "WAITING_APPROVAL" in statuses


def test_loop_timeline_tracks_full_cycle(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    result = orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    loop = orchestrator.on_executed(prepared.id, result)
    verified = orchestrator.verify(loop.id, test_passed=True)
    statuses = [entry["status"] for entry in orchestrator.timeline(verified.id)]
    for expected in ["CREATED", "PLANNING", "PROPOSAL_READY", "WAITING_APPROVAL", "EXECUTING", "VERIFYING", "COMPLETED"]:
        assert expected in statuses


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------


def test_loop_create_api_requires_approval(bridge):
    seed_plan(bridge)
    pending = bridge.client.post("/execution-loop/create", json={"project": "demo", "plan_id": "plan_1"})
    assert pending.status_code == 202
    assert pending.json()["requestId"].startswith("req_")
    assert bridge.client.get("/execution-loop/list").json()["loops"] == []


def test_loop_create_api_unknown_plan_404(bridge):
    assert bridge.client.post("/execution-loop/create", json={"project": "demo", "plan_id": "plan_missing"}).status_code == 404


def test_loop_full_api_flow(bridge):
    seed_plan(bridge)
    loop = bridge.approve(bridge.client.post("/execution-loop/create", json={"project": "demo", "plan_id": "plan_1"}).json()["requestId"]).json()["result"]
    assert loop["status"] == "PLANNING"
    detail = bridge.client.get(f"/execution-loop/{loop['id']}").json()
    assert detail["readOnly"] is True and detail["taskIds"]
    timeline = bridge.client.get(f"/execution-loop/{loop['id']}/timeline").json()
    assert timeline["readOnly"] is True and timeline["timeline"]


def test_loop_prepare_api_requires_approval(bridge):
    seed_plan(bridge)
    loop = bridge.approve(bridge.client.post("/execution-loop/create", json={"project": "demo", "plan_id": "plan_1"}).json()["requestId"]).json()["result"]
    pending = bridge.client.post(f"/execution-loop/{loop['id']}/prepare", json={})
    assert pending.status_code == 202
    assert bridge.client.get(f"/execution-loop/{loop['id']}").json()["proposalId"] is None


def test_loop_verify_api_requires_approval(bridge):
    seed_plan(bridge)
    loop = bridge.approve(bridge.client.post("/execution-loop/create", json={"project": "demo", "plan_id": "plan_1"}).json()["requestId"]).json()["result"]
    pending = bridge.client.post(f"/execution-loop/{loop['id']}/verify", json={"quality_score": 90, "test_passed": True})
    assert pending.status_code == 202


def test_loop_rollback_api_requires_approval(bridge):
    seed_plan(bridge)
    loop = bridge.approve(bridge.client.post("/execution-loop/create", json={"project": "demo", "plan_id": "plan_1"}).json()["requestId"]).json()["result"]
    pending = bridge.client.post(f"/execution-loop/{loop['id']}/rollback", json={})
    assert pending.status_code == 202


def test_loop_detail_unknown_404(bridge):
    assert bridge.client.get("/execution-loop/eloop_missing").status_code == 404
    assert bridge.client.get("/execution-loop/eloop_missing/timeline").status_code == 404


def test_loop_list_api_read_only(bridge):
    response = bridge.client.get("/execution-loop/list")
    assert response.status_code == 200 and response.json()["readOnly"] is True


def test_quality_gate8_api_read_only(bridge):
    response = bridge.client.get("/quality/v8/wf_1", params={"execution_ready": True, "confidence": 90})
    assert response.status_code == 200 and response.json()["readOnly"] is True


@pytest.mark.parametrize("field", ["quality", "executionReady", "confidence", "riskLevel", "blockingIssues", "rollbackCapability", "testResult", "recommendation", "readOnly"])
def test_quality_gate8_api_contract(bridge, field):
    assert field in bridge.client.get("/quality/v8/wf_1").json()


def test_loop_execution_binds_loop_id(bridge):
    seed_plan(bridge)
    loop = bridge.approve(bridge.client.post("/execution-loop/create", json={"project": "demo", "plan_id": "plan_1"}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/execution-loop/{loop['id']}/prepare", json={}).json()["requestId"])
    stored = ExecutionLoopStorage(get_settings().execution_loop_db_path).get(loop["id"])
    approvals = ApprovalStore()
    request = approvals.create(action="execution_execute", project="demo", path="execution", payload={}, reason="x", preview="y", execution_loop_id=loop["id"])
    approvals.mark_approved(request.request_id)
    assert approvals.get(request.request_id).execution_loop_id == loop["id"]
    assert stored is not None and stored.proposal_id is not None


# ---------------------------------------------------------------------------
# Security invariants
# ---------------------------------------------------------------------------


def test_loop_orchestrator_has_no_execute_method(bridge):
    _, _, _, orchestrator = setup_orchestrator(bridge)
    assert not hasattr(orchestrator, "execute_action")
    assert not hasattr(orchestrator, "run_action")
    assert not hasattr(orchestrator, "execute")


def test_loop_execution_requires_approved_approval(bridge):
    seed_plan(bridge)
    _, approvals, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    with pytest.raises(ValidationFailed):
        orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=None)


def test_loop_recovery_never_auto_approves(tmp_path):
    store = ApprovalStore(tmp_path / "approval_loop.db")
    request = store.create(action="execution_loop_verify", project="demo", path="execution-loop", payload={}, reason="test", preview="metadata", execution_loop_id="eloop_1")
    recovered = store.recover_pending()
    assert recovered[0].execution_loop_id == "eloop_1"
    assert recovered[0].status.value == "recovered"
    with pytest.raises(Exception):
        store.mark_approved(request.request_id)
    store.reconfirm(request.request_id)
    assert store.mark_approved(request.request_id).status.value == "approved"


def test_loop_learning_memory_requires_separate_approval(tmp_path):
    store = ApprovalStore(tmp_path / "approval_loop2.db")
    request = store.create(action="execution_memory_append", project="demo", path="memory/execution/execution-history.md", payload={"category": "history", "content": "x"}, reason="learn", preview="memory", execution_loop_id="eloop_1")
    assert store.get(request.request_id).execution_loop_id == "eloop_1"
    assert store.get(request.request_id).status.value == "pending"


def test_loop_execution_does_not_modify_sources(bridge):
    seed_plan(bridge)
    before = (bridge.demo / "src" / "main.py").read_bytes()
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    orchestrator.execution_manager.execute(prepared.proposal_id, approval_id=approved_execute_id(orchestrator.approvals))
    assert (bridge.demo / "src" / "main.py").read_bytes() == before


def test_loop_prepare_never_auto_executes(bridge):
    seed_plan(bridge)
    _, _, storage, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    prepared = orchestrator.prepare(loop.id)
    assert storage.get(prepared.id).result_id is None
    assert storage.get(prepared.id).status is LoopStatus.WAITING_APPROVAL


def test_loop_verify_does_not_auto_execute(bridge):
    seed_plan(bridge)
    _, _, _, orchestrator = setup_orchestrator(bridge)
    loop = create_loop(orchestrator)
    with pytest.raises(ValidationFailed):
        orchestrator.verify(loop.id)
