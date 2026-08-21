from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.execution import ExecutionManager, ExecutionStorage
from app.execution.executor import ControlledExecutor
from app.execution.models import ExecutionProposalStatus, ExecutionTask, ExecutionTaskStatus
from app.execution.proposal import ExecutionProposalGenerator
from app.execution.task_builder import ImplementationTaskBuilder
from app.execution.verifier import VerificationService
from app.intelligence.decision import DecisionManager
from app.intelligence.models import Insight, InsightType, Proposal, Severity
from app.intelligence.storage import IntelligenceStorage
from app.memory.execution import ExecutionMemory
from app.quality.gate7 import QualityGate7Evaluator
from app.security.permissions import ApprovalStore
from app.security.validator import ResourceNotFound, ValidationFailed

PLAN_TEMPLATE = """# Engineering Plan

## Problem
{problem}

## Current State
Simulation predicts impact.

## Selected Scenario
{scenario} (refactor)

## Files
{files}

## Implementation Steps
{steps}

## Testing Plan
- focused regression tests

## Rollback Plan
- restore previous state

## Risks
- medium
"""


def make_plan(files: list[str], steps: list[str], problem: str = "high coupling") -> str:
    file_lines = "\n".join(f"- `{path}`" for path in files)
    step_lines = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1))
    return PLAN_TEMPLATE.format(problem=problem, scenario="Module Extraction", files=file_lines, steps=step_lines)


def make_task(status: ExecutionTaskStatus = ExecutionTaskStatus.PROPOSED, *, files: list[str] | None = None, risk_score: int = 40) -> ExecutionTask:
    return ExecutionTask(
        id="et_test",
        workflow_id=None,
        plan_id="plan_1",
        project="demo",
        title="extract auth service",
        task_type="implementation",
        files=files if files is not None else ["src/main.py"],
        dependencies=[],
        risk="medium",
        risk_score=risk_score,
        status=status,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def approved_id(store: ApprovalStore, action: str = "execution_execute") -> str:
    request = store.create(action=action, project="demo", path="execution", payload={}, reason="test", preview="metadata")
    store.mark_approved(request.request_id)
    return request.request_id


def setup_exec(bridge, plan_content: str | None = None):
    settings = get_settings()
    storage = ExecutionStorage(settings.execution_db_path)
    approvals = ApprovalStore()
    manager = ExecutionManager(storage, settings, approvals=approvals)
    content = plan_content or make_plan(["src/main.py", "src/auth.py"], ["extract auth service", "move token logic"])
    tasks = manager.create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=content)
    return settings, storage, approvals, manager, tasks


def proposal_for(manager: ExecutionManager, task_id: str):
    return manager.generate_proposal(task_id)


# ---------------------------------------------------------------------------
# Task builder
# ---------------------------------------------------------------------------

def test_execution_rejects_empty_plan(bridge):
    _, _, _, manager, _ = setup_exec(bridge, plan_content="")
    with pytest.raises(ValidationFailed):
        manager.create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content="   ")


def test_execution_rejects_plan_without_files(bridge):
    content = make_plan([], ["extract auth service"])
    with pytest.raises(ValidationFailed):
        ExecutionManager(ExecutionStorage(get_settings().execution_db_path), get_settings()).create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=content)


def test_execution_rejects_plan_without_steps(bridge):
    content = make_plan(["src/main.py"], [])
    with pytest.raises(ValidationFailed):
        ExecutionManager(ExecutionStorage(get_settings().execution_db_path), get_settings()).create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=content)


@pytest.mark.parametrize("step_count", [1, 2, 3, 4, 5])
def test_execution_tasks_match_step_count(bridge, step_count):
    content = make_plan(["src/main.py"], [f"step {index}" for index in range(step_count)])
    _, _, _, manager, tasks = setup_exec(bridge, plan_content=content)
    assert len(tasks) == step_count


@pytest.mark.parametrize("file_count", [1, 2, 3, 4])
def test_execution_tasks_preserve_files(bridge, file_count):
    files = [f"src/module_{index}.py" for index in range(file_count)]
    _, _, _, manager, tasks = setup_exec(bridge, plan_content=make_plan(files, ["step one"]))
    assert all(task.files == files for task in tasks)


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4])
def test_execution_task_risk_escalates_with_step(bridge, index):
    content = make_plan(["src/main.py"], [f"step {i}" for i in range(5)])
    _, _, _, manager, tasks = setup_exec(bridge, plan_content=content)
    assert tasks[index].risk_score <= tasks[-1].risk_score


def test_execution_task_dependencies_exclude_self(bridge):
    _, _, _, manager, tasks = setup_exec(bridge, plan_content=make_plan(["src/main.py"], ["step one", "step two", "step three"]))
    for task in tasks:
        assert task.title not in task.dependencies


# ---------------------------------------------------------------------------
# Task state machine
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = [
    (ExecutionTaskStatus.PROPOSED, ExecutionTaskStatus.APPROVAL_REQUIRED),
    (ExecutionTaskStatus.APPROVAL_REQUIRED, ExecutionTaskStatus.APPROVED),
    (ExecutionTaskStatus.APPROVAL_REQUIRED, ExecutionTaskStatus.FAILED),
    (ExecutionTaskStatus.APPROVAL_REQUIRED, ExecutionTaskStatus.ROLLED_BACK),
    (ExecutionTaskStatus.APPROVED, ExecutionTaskStatus.EXECUTING),
    (ExecutionTaskStatus.APPROVED, ExecutionTaskStatus.FAILED),
    (ExecutionTaskStatus.APPROVED, ExecutionTaskStatus.ROLLED_BACK),
    (ExecutionTaskStatus.EXECUTING, ExecutionTaskStatus.VERIFYING),
    (ExecutionTaskStatus.EXECUTING, ExecutionTaskStatus.FAILED),
    (ExecutionTaskStatus.EXECUTING, ExecutionTaskStatus.ROLLED_BACK),
    (ExecutionTaskStatus.VERIFYING, ExecutionTaskStatus.COMPLETED),
    (ExecutionTaskStatus.VERIFYING, ExecutionTaskStatus.FAILED),
    (ExecutionTaskStatus.VERIFYING, ExecutionTaskStatus.ROLLED_BACK),
]


@pytest.mark.parametrize("source,target", VALID_TRANSITIONS)
def test_execution_task_valid_transitions(bridge, source, target):
    _, storage, _, manager, _ = setup_exec(bridge)
    storage.save_task(make_task(source))
    moved = manager._transition(storage.get_task("et_test"), target)
    assert moved.status is target


ILLEGAL_TRANSITIONS = [
    (ExecutionTaskStatus.PROPOSED, ExecutionTaskStatus.EXECUTING),
    (ExecutionTaskStatus.PROPOSED, ExecutionTaskStatus.APPROVED),
    (ExecutionTaskStatus.PROPOSED, ExecutionTaskStatus.COMPLETED),
    (ExecutionTaskStatus.PROPOSED, ExecutionTaskStatus.VERIFYING),
    (ExecutionTaskStatus.APPROVAL_REQUIRED, ExecutionTaskStatus.VERIFYING),
    (ExecutionTaskStatus.APPROVAL_REQUIRED, ExecutionTaskStatus.COMPLETED),
    (ExecutionTaskStatus.APPROVAL_REQUIRED, ExecutionTaskStatus.EXECUTING),
    (ExecutionTaskStatus.APPROVED, ExecutionTaskStatus.COMPLETED),
    (ExecutionTaskStatus.APPROVED, ExecutionTaskStatus.VERIFYING),
    (ExecutionTaskStatus.APPROVED, ExecutionTaskStatus.PROPOSED),
    (ExecutionTaskStatus.EXECUTING, ExecutionTaskStatus.COMPLETED),
    (ExecutionTaskStatus.EXECUTING, ExecutionTaskStatus.APPROVED),
    (ExecutionTaskStatus.EXECUTING, ExecutionTaskStatus.PROPOSED),
    (ExecutionTaskStatus.VERIFYING, ExecutionTaskStatus.EXECUTING),
    (ExecutionTaskStatus.VERIFYING, ExecutionTaskStatus.APPROVED),
    (ExecutionTaskStatus.VERIFYING, ExecutionTaskStatus.PROPOSED),
    (ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.EXECUTING),
    (ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.APPROVED),
    (ExecutionTaskStatus.COMPLETED, ExecutionTaskStatus.PROPOSED),
    (ExecutionTaskStatus.FAILED, ExecutionTaskStatus.COMPLETED),
    (ExecutionTaskStatus.FAILED, ExecutionTaskStatus.EXECUTING),
    (ExecutionTaskStatus.FAILED, ExecutionTaskStatus.PROPOSED),
    (ExecutionTaskStatus.ROLLED_BACK, ExecutionTaskStatus.COMPLETED),
    (ExecutionTaskStatus.ROLLED_BACK, ExecutionTaskStatus.EXECUTING),
    (ExecutionTaskStatus.ROLLED_BACK, ExecutionTaskStatus.APPROVED),
]


@pytest.mark.parametrize("source,target", ILLEGAL_TRANSITIONS)
def test_execution_task_illegal_transitions_rejected(bridge, source, target):
    _, storage, _, manager, _ = setup_exec(bridge)
    storage.save_task(make_task(source))
    with pytest.raises(ValidationFailed):
        manager._transition(storage.get_task("et_test"), target)


@pytest.mark.parametrize("status", list(ExecutionTaskStatus))
def test_execution_task_status_enum_is_stable(status):
    assert ExecutionTaskStatus(status.value) is status


@pytest.mark.parametrize("status", list(ExecutionProposalStatus))
def test_execution_proposal_status_enum_is_stable(status):
    assert ExecutionProposalStatus(status.value) is status


# ---------------------------------------------------------------------------
# Storage persistence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("title", "implement auth extraction"),
    ("files", ["a.py", "b.py", "c.py"]),
    ("risk", "high"),
    ("risk_score", 87),
    ("status", ExecutionTaskStatus.APPROVED),
    ("verification", {"status": "PASS", "checks": ["approval_verified"]}),
])
def test_execution_task_round_trips(bridge, field, value):
    settings, storage, _, _, _ = setup_exec(bridge)
    task = make_task()
    setattr(task, field, value)
    storage.save_task(task)
    reopened = ExecutionStorage(settings.execution_db_path).get_task("et_test")
    assert getattr(reopened, field) == value


@pytest.mark.parametrize("field,value", [
    ("estimated_changes", 7),
    ("risk_score", 55),
    ("status", ExecutionProposalStatus.APPROVED),
    ("approval_id", "req_abc"),
    ("workflow_id", "wf_1"),
])
def test_execution_proposal_persists_generated_values(bridge, field, value):
    settings, storage, _, manager, _ = setup_exec(bridge)
    task = manager.create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=make_plan(["src/main.py"], ["step one"]))[0]
    proposal = ExecutionProposalGenerator().generate(task)
    proposal.created_at = "2026-01-01T00:00:00Z"
    setattr(proposal, field, value)
    storage.save_proposal(proposal)
    reopened = ExecutionStorage(settings.execution_db_path).get_proposal(proposal.id)
    assert getattr(reopened, field) == value


@pytest.mark.parametrize("field,value", [("status", ExecutionProposalStatus.EXECUTED), ("approval_id", "req_abc")])
def test_execution_proposal_status_and_approval_update(bridge, field, value):
    settings, storage, _, manager, _ = setup_exec(bridge)
    task = manager.create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=make_plan(["src/main.py"], ["step one"]))[0]
    proposal = manager.generate_proposal(task.id)
    setattr(proposal, field, value)
    storage.update_proposal(proposal)
    reopened = ExecutionStorage(settings.execution_db_path).get_proposal(proposal.id)
    assert getattr(reopened, field) == value


def test_execution_storage_reopens_after_close(bridge):
    settings, storage, _, manager, _ = setup_exec(bridge)
    task = make_task()
    storage.save_task(task)
    storage.close()
    assert ExecutionStorage(settings.execution_db_path).get_task("et_test").title == task.title


@pytest.mark.parametrize("limit", [1, 2, 3, 10])
def test_execution_list_tasks_respects_limit(bridge, limit):
    _, storage, _, manager, _ = setup_exec(bridge)
    for index in range(5):
        storage.save_task(make_task(status=ExecutionTaskStatus.PROPOSED, files=[f"src/f{index}.py"]))
    assert len(manager.list_tasks(limit=limit)) <= limit


# ---------------------------------------------------------------------------
# Proposal generation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("file_count", [1, 2, 3, 4, 5, 6])
def test_proposal_has_one_operation_per_file(bridge, file_count):
    files = [f"src/module_{index}.py" for index in range(file_count)]
    _, _, _, manager, tasks = setup_exec(bridge, plan_content=make_plan(files, ["step one"]))
    proposal = proposal_for(manager, tasks[0].id)
    assert len(proposal.operations) == file_count
    assert all(operation.operation_type == "file.patch" for operation in proposal.operations)


@pytest.mark.parametrize("risk_score", [5, 20, 45, 75, 95])
def test_proposal_risk_score_is_bounded(bridge, risk_score):
    _, storage, _, manager, _ = setup_exec(bridge)
    storage.save_task(make_task(risk_score=risk_score))
    proposal = ExecutionProposalGenerator().generate(storage.get_task("et_test"))
    assert 0 <= proposal.risk_score <= 100
    assert proposal.risk_score >= risk_score


def test_proposal_is_metadata_read_only(bridge):
    _, _, _, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    assert proposal.as_dict()["readOnly"] is True


def test_proposal_rejects_task_without_files(bridge):
    _, storage, _, _, _ = setup_exec(bridge)
    task = make_task(files=[])
    storage.save_task(task)
    with pytest.raises(ValidationFailed):
        ExecutionProposalGenerator().generate(storage.get_task("et_test"))


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_proposal_generation_moves_task_to_approval_required(bridge, index):
    content = make_plan(["src/main.py"], [f"step {i}" for i in range(5)])
    _, _, _, manager, tasks = setup_exec(bridge, plan_content=content)
    proposal_for(manager, tasks[index].id)
    assert manager.get_task(tasks[index].id).status is ExecutionTaskStatus.APPROVAL_REQUIRED


# ---------------------------------------------------------------------------
# Controlled executor preconditions and behaviour
# ---------------------------------------------------------------------------

def test_execute_requires_approved_approval(bridge):
    _, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    with pytest.raises(ValidationFailed):
        manager.execute(proposal.id, approval_id=None)


def _pending_approval_id(store: ApprovalStore) -> str:
    return store.create(action="execution_execute", project="demo", path="execution", payload={}, reason="x", preview="y").request_id


def _recovered_approval_id(store: ApprovalStore) -> str:
    store.create(action="execution_execute", project="demo", path="execution", payload={}, reason="x", preview="y")
    return store.recover_pending()[0].request_id


def _rejected_approval_id(store: ApprovalStore) -> str:
    request = store.create(action="execution_execute", project="demo", path="execution", payload={}, reason="x", preview="y")
    store.mark_rejected(request.request_id)
    return request.request_id


@pytest.mark.parametrize("request_id_factory", [_pending_approval_id, _recovered_approval_id, _rejected_approval_id])
def test_execute_rejects_non_approved_approval(bridge, request_id_factory):
    _, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    with pytest.raises(ValidationFailed):
        manager.execute(proposal.id, approval_id=request_id_factory(approvals))


def test_execute_rejects_unchanged_risk_after_task_change(bridge):
    _, storage, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    task = manager.get_task(tasks[0].id)
    task.risk_score = 99
    storage.save_task(task)
    with pytest.raises(ValidationFailed):
        manager.execute(proposal.id, approval_id=approved_id(approvals))


@pytest.mark.parametrize("bad_path", ["../escape.py", "/absolute/path.py", "a/../../b.py", "..", "src/../secret.py"])
def test_execute_rejects_invalid_paths(bridge, bad_path):
    _, _, approvals, manager, _ = setup_exec(bridge)
    tasks = manager.create_from_plan(plan_id="plan_1", project="demo", workflow_id=None, plan_content=make_plan([bad_path], ["step one"]))
    proposal = proposal_for(manager, tasks[0].id)
    with pytest.raises(ValidationFailed):
        manager.execute(proposal.id, approval_id=approved_id(approvals))


class _CancelledWorkflowStub:
    class _Status:
        value = "CANCELLED"

    status = _Status()

    def get(self, workflow_id):  # pragma: no cover - stub
        return self


def test_execute_blocks_inactive_workflow(bridge):
    settings, storage, approvals, _, tasks = setup_exec(bridge)
    manager = ExecutionManager(storage, settings, approvals=approvals, workflow_manager=_CancelledWorkflowStub())
    task = tasks[0]
    task.workflow_id = "wf_cancelled"
    storage.save_task(task)
    proposal = manager.generate_proposal(task.id)
    with pytest.raises(ValidationFailed):
        manager.execute(proposal.id, approval_id=approved_id(approvals))


def test_execute_skips_stage_check_when_unbound(bridge):
    settings, storage, approvals, _, tasks = setup_exec(bridge)
    manager = ExecutionManager(storage, settings, approvals=approvals, workflow_manager=None)
    proposal = manager.generate_proposal(tasks[0].id)
    result = manager.execute(proposal.id, approval_id=approved_id(approvals))
    assert result.verification["status"] == "PASS"


def test_execute_creates_snapshot(bridge):
    settings, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    result = manager.execute(proposal.id, approval_id=approved_id(approvals))
    snapshot_dir = settings.execution_snapshot_root / "standalone" / tasks[0].id
    assert (snapshot_dir / "metadata.json").is_file()
    assert result.verification["snapshotCaptured"] is True


@pytest.mark.parametrize("index", [0, 1])
def test_execute_snapshot_exists_for_each_task(bridge, index):
    settings, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[index].id)
    manager.execute(proposal.id, approval_id=approved_id(approvals))
    assert (settings.execution_snapshot_root / "standalone" / tasks[index].id / "metadata.json").is_file()


def test_execute_does_not_modify_sources(bridge):
    before = (bridge.demo / "src" / "main.py").read_bytes()
    _, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    manager.execute(proposal.id, approval_id=approved_id(approvals))
    assert (bridge.demo / "src" / "main.py").read_bytes() == before


def test_execute_records_result_and_verification(bridge):
    _, storage, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    result = manager.execute(proposal.id, approval_id=approved_id(approvals))
    stored = storage.get_result(result.id)
    assert stored is not None and stored.verification["status"] == "PASS"
    assert manager.get_task(tasks[0].id).status is ExecutionTaskStatus.COMPLETED
    assert storage.get_proposal(proposal.id).status is ExecutionProposalStatus.EXECUTED


@pytest.mark.parametrize("field", ["filesChanged", "diffSummary", "durationMs", "errors", "verification"])
def test_execute_result_contract_fields(bridge, field):
    _, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    result = manager.execute(proposal.id, approval_id=approved_id(approvals)).as_dict()
    assert field in result
    assert result["durationMs"] >= 0 and isinstance(result["errors"], list)


@pytest.mark.parametrize("attempt", [1, 2])
def test_execute_is_deterministic(bridge, attempt):
    _, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    result = manager.execute(proposal.id, approval_id=approved_id(approvals))
    assert result.files_changed == tasks[0].files
    assert result.verification["approvalVerified"] is True


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("test_passed", [True, False, None])
def test_verifier_reflects_test_result(bridge, test_passed):
    report = VerificationService(get_settings()).verify(project="demo", files=["a.py"], test_passed=test_passed)
    assert ("tests_passed" in report["checks"]) == (test_passed is True)
    assert ("tests_failed" in report["checks"]) == (test_passed is False)


@pytest.mark.parametrize("dependency_break", [True, False])
def test_verifier_detects_dependency_break(bridge, dependency_break):
    report = VerificationService(get_settings()).verify(project="demo", files=["a.py"], snapshot_captured=True, approval_verified=True, dependency_break=dependency_break)
    assert report["status"] == ("FAIL" if dependency_break else "PASS")


@pytest.mark.parametrize("snapshot_captured", [True, False])
def test_verifier_requires_snapshot(bridge, snapshot_captured):
    report = VerificationService(get_settings()).verify(project="demo", files=["a.py"], snapshot_captured=snapshot_captured, approval_verified=True)
    assert report["status"] == ("PASS" if snapshot_captured else "FAIL")


@pytest.mark.parametrize("approval_verified", [True, False])
def test_verifier_requires_approval(bridge, approval_verified):
    report = VerificationService(get_settings()).verify(project="demo", files=["a.py"], snapshot_captured=True, approval_verified=approval_verified)
    assert report["status"] == ("PASS" if approval_verified else "FAIL")


@pytest.mark.parametrize("quality_score", [None, 0, 50, 91, 100])
def test_verifier_embeds_quality_score(bridge, quality_score):
    report = VerificationService(get_settings()).verify(project="demo", files=["a.py"], quality_score=quality_score)
    if quality_score is None:
        assert not any(check.startswith("quality_score:") for check in report["checks"])
    else:
        assert f"quality_score:{quality_score}" in report["checks"]


@pytest.mark.parametrize("file_count", [0, 1, 3, 10])
def test_verifier_counts_files(bridge, file_count):
    files = [f"f{i}.py" for i in range(file_count)]
    report = VerificationService(get_settings()).verify(project="demo", files=files)
    assert f"files_analyzed:{file_count}" in report["checks"]


def test_verifier_never_auto_fixes(bridge):
    report = VerificationService(get_settings()).verify(project="demo", files=["a.py"], test_passed=False)
    assert report["autoFix"] is False and report["readOnly"] is True


# ---------------------------------------------------------------------------
# Execution memory
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category,filename", [
    ("implementation", "implementation-history.md"),
    ("lessons", "execution-lessons.md"),
    ("rollback", "rollback-history.md"),
])
def test_execution_memory_append_is_append_only(bridge, category, filename):
    settings, _, _, _, _ = setup_exec(bridge)
    memory = ExecutionMemory(settings)
    result = memory.append_after_approval("demo", category, "approved content")
    assert result["document"] == filename
    assert filename in {item["document"] for item in memory.history("demo")}


@pytest.mark.parametrize("category", ["bad", "code", "execution", ""])
def test_execution_memory_rejects_unknown_category(bridge, category):
    settings, _, _, _, _ = setup_exec(bridge)
    with pytest.raises(ValidationFailed):
        ExecutionMemory(settings).preview("demo", category, "no")


def test_execution_memory_preview_does_not_write(bridge):
    settings, _, _, _, _ = setup_exec(bridge)
    memory = ExecutionMemory(settings)
    assert "proposal" in memory.preview("demo", "implementation", "# Implementation")
    assert memory.history("demo") == []


def test_execution_memory_is_project_isolated(bridge):
    settings, _, _, _, _ = setup_exec(bridge)
    ExecutionMemory(settings).append_after_approval("demo", "implementation", "content")
    assert ExecutionMemory(settings).history("other") == []


def index_demo(bridge):
    pending = bridge.client.post("/code/index", json={"project": "demo"})
    assert pending.status_code == 202
    assert bridge.approve(pending.json()["requestId"]).status_code == 200


def test_execution_memory_append_after_approval_via_api(bridge):
    index_demo(bridge)
    created = bridge.approve(bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/simulation/{created['id']}/analyze", json={}).json()["requestId"])
    scenario = bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"][0]
    plan = bridge.approve(bridge.client.post(f"/simulation/{created['id']}/plan", json={"scenario_id": scenario["id"]}).json()["requestId"]).json()["result"]
    tasks = bridge.approve(bridge.client.post("/execution/create", json={"project": "demo", "plan_id": plan["id"]}).json()["requestId"]).json()["result"]["tasks"]
    proposal = bridge.approve(bridge.client.post(f"/execution/{tasks[0]['id']}/proposal", json={}).json()["requestId"]).json()["result"]
    executed = bridge.approve(bridge.client.post(f"/execution/{proposal['id']}/execute", json={}).json()["requestId"]).json()["result"]
    memory_id = executed["memoryProposal"]["requestId"]
    assert bridge.client.get("/memory/execution/history", params={"project": "demo"}).json()["history"] == []
    assert bridge.approve(memory_id).status_code == 200
    assert bridge.client.get("/memory/execution/history", params={"project": "demo"}).json()["history"]


# ---------------------------------------------------------------------------
# Quality Gate 7.0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("confidence", [0, 25, 50, 75, 100])
def test_quality_gate7_confidence_bounded(bridge, confidence):
    report = QualityGate7Evaluator().evaluate(implementation_confidence=confidence)
    assert 0 <= report["quality"] <= 100 and report["implementationConfidence"] == confidence


@pytest.mark.parametrize("risk", [0, 20, 40, 70, 100])
def test_quality_gate7_risk_lowers_quality(bridge, risk):
    report = QualityGate7Evaluator().evaluate(execution_risk=risk)
    assert report["executionRisk"] == risk and 0 <= report["quality"] <= 100


@pytest.mark.parametrize("rollback", [0, 50, 100])
def test_quality_gate7_rollback_readiness(bridge, rollback):
    report = QualityGate7Evaluator().evaluate(rollback_readiness=rollback)
    assert report["rollbackReadiness"] == rollback


@pytest.mark.parametrize("verification", [0, 50, 100])
def test_quality_gate7_verification_confidence(bridge, verification):
    report = QualityGate7Evaluator().evaluate(verification_confidence=verification)
    assert report["verificationConfidence"] == verification


@pytest.mark.parametrize("issues", [[], ["blocking"], ["a", "b", "c"]])
def test_quality_gate7_blocking_issues(bridge, issues):
    report = QualityGate7Evaluator().evaluate(blocking_issues=issues)
    assert report["blockingIssues"] == issues
    assert report["executionReady"] is (len(issues) == 0 and report["quality"] >= 70)


def test_quality_gate7_is_read_only(bridge):
    assert QualityGate7Evaluator().evaluate()["readOnly"] is True


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------

def test_execution_create_requires_approval(bridge):
    pending = bridge.client.post("/execution/create", json={"project": "demo", "plan_id": "plan_missing"})
    assert pending.status_code == 404


def test_execution_create_unknown_plan_returns_404(bridge):
    assert bridge.client.post("/execution/create", json={"project": "demo", "plan_id": "plan_missing"}).status_code == 404


def test_execution_task_unknown_returns_404(bridge):
    assert bridge.client.get("/execution/task/et_missing").status_code == 404
    assert bridge.client.get("/execution/proposal/ep_missing").status_code == 404


@pytest.mark.parametrize("endpoint", ["/execution/tasks", "/execution/proposals", "/execution/results"])
def test_execution_read_endpoints_are_read_only(bridge, endpoint):
    response = bridge.client.get(endpoint)
    assert response.status_code == 200 and response.json()["readOnly"] is True


def test_execution_full_flow_is_approval_gated(bridge):
    index_demo(bridge)
    created = bridge.approve(bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/simulation/{created['id']}/analyze", json={}).json()["requestId"])
    scenario = bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"][0]
    plan = bridge.approve(bridge.client.post(f"/simulation/{created['id']}/plan", json={"scenario_id": scenario["id"]}).json()["requestId"]).json()["result"]
    create_pending = bridge.client.post("/execution/create", json={"project": "demo", "plan_id": plan["id"]})
    assert create_pending.status_code == 202
    assert bridge.client.get("/execution/tasks").json()["tasks"] == []
    tasks = bridge.approve(create_pending.json()["requestId"]).json()["result"]["tasks"]
    assert len(tasks) >= 1 and all(task["status"] == "PROPOSED" for task in tasks)
    proposal_pending = bridge.client.post(f"/execution/{tasks[0]['id']}/proposal", json={})
    assert proposal_pending.status_code == 202
    assert bridge.client.get(f"/execution/task/{tasks[0]['id']}").json()["proposals"] == []
    proposal = bridge.approve(proposal_pending.json()["requestId"]).json()["result"]
    assert proposal["operations"] and proposal["readOnly"] is True
    execute_pending = bridge.client.post(f"/execution/{proposal['id']}/execute", json={})
    assert execute_pending.status_code == 202
    result = bridge.approve(execute_pending.json()["requestId"]).json()["result"]
    assert result["verification"]["status"] == "PASS"
    assert bridge.client.get(f"/execution/{tasks[0]['id']}/verify").json()["status"] == "PASS"
    assert bridge.client.get("/execution/results").json()["results"]


def test_execution_execute_without_approval_does_nothing(bridge):
    index_demo(bridge)
    created = bridge.approve(bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/simulation/{created['id']}/analyze", json={}).json()["requestId"])
    scenario = bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"][0]
    plan = bridge.approve(bridge.client.post(f"/simulation/{created['id']}/plan", json={"scenario_id": scenario["id"]}).json()["requestId"]).json()["result"]
    tasks = bridge.approve(bridge.client.post("/execution/create", json={"project": "demo", "plan_id": plan["id"]}).json()["requestId"]).json()["result"]["tasks"]
    proposal = bridge.approve(bridge.client.post(f"/execution/{tasks[0]['id']}/proposal", json={}).json()["requestId"]).json()["result"]
    bridge.client.post(f"/execution/{proposal['id']}/execute", json={})
    assert bridge.client.get("/execution/results").json()["results"] == []
    assert bridge.client.get(f"/execution/task/{tasks[0]['id']}").json()["status"] == "APPROVAL_REQUIRED"


def test_execution_execute_unknown_proposal_404(bridge):
    pending = bridge.client.post("/execution/ep_missing/execute", json={})
    assert pending.status_code == 404


def test_quality_gate7_api_is_read_only(bridge):
    response = bridge.client.get("/quality/v7/wf_1", params={"implementation_confidence": 92, "execution_risk": 20})
    assert response.status_code == 200 and response.json()["readOnly"] is True


@pytest.mark.parametrize("field", ["quality", "executionReady", "blockingIssues", "implementationConfidence", "executionRisk", "rollbackReadiness", "verificationConfidence", "readOnly"])
def test_quality_gate7_api_contract(bridge, field):
    assert field in bridge.client.get("/quality/v7/wf_1").json()


def test_execution_memory_history_api(bridge):
    assert bridge.client.get("/memory/execution/history", params={"project": "demo"}).json()["readOnly"] is True


def test_execution_does_not_bypass_approval_store(bridge):
    index_demo(bridge)
    created = bridge.approve(bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/simulation/{created['id']}/analyze", json={}).json()["requestId"])
    scenario = bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"][0]
    plan = bridge.approve(bridge.client.post(f"/simulation/{created['id']}/plan", json={"scenario_id": scenario["id"]}).json()["requestId"]).json()["result"]
    pending = bridge.client.post("/execution/create", json={"project": "demo", "plan_id": plan["id"]})
    assert pending.json()["requestId"].startswith("req_")
    assert bridge.client.get("/execution/tasks").json()["tasks"] == []


def test_execution_source_unchanged_through_api(bridge):
    index_demo(bridge)
    before = (bridge.demo / "src" / "main.py").read_bytes()
    created = bridge.approve(bridge.client.post("/simulation/create", json={"project": "demo", "problem": "coupling"}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/simulation/{created['id']}/analyze", json={}).json()["requestId"])
    scenario = bridge.client.get(f"/simulation/{created['id']}/scenarios").json()["scenarios"][0]
    plan = bridge.approve(bridge.client.post(f"/simulation/{created['id']}/plan", json={"scenario_id": scenario["id"]}).json()["requestId"]).json()["result"]
    tasks = bridge.approve(bridge.client.post("/execution/create", json={"project": "demo", "plan_id": plan["id"]}).json()["requestId"]).json()["result"]["tasks"]
    proposal = bridge.approve(bridge.client.post(f"/execution/{tasks[0]['id']}/proposal", json={}).json()["requestId"]).json()["result"]
    bridge.approve(bridge.client.post(f"/execution/{proposal['id']}/execute", json={}).json()["requestId"])
    assert (bridge.demo / "src" / "main.py").read_bytes() == before


def test_execution_recovery_never_auto_approves(tmp_path):
    store = ApprovalStore(tmp_path / "approval.db")
    request = store.create(action="execution_execute", project="demo", path="execution", payload={}, reason="test", preview="metadata")
    recovered = store.recover_pending()
    assert recovered[0].status.value == "recovered"
    with pytest.raises(Exception):
        store.mark_approved(request.request_id)
    store.reconfirm(request.request_id)
    assert store.mark_approved(request.request_id).status.value == "approved"


def test_execution_scheduler_style_execution_has_no_implicit_approval(bridge):
    _, _, approvals, manager, tasks = setup_exec(bridge)
    proposal = proposal_for(manager, tasks[0].id)
    request = approvals.create(action="execution_execute", project="demo", path="execution", payload={}, reason="x", preview="y")
    with pytest.raises(Exception):
        manager.execute(proposal.id, approval_id=request.request_id)


# ---------------------------------------------------------------------------
# Decision integration (Phase 13 extension)
# ---------------------------------------------------------------------------

def seed_decision_storage(bridge) -> IntelligenceStorage:
    settings = get_settings()
    storage = IntelligenceStorage(settings.intelligence_db_path)
    storage.save_insights([Insight("insight_1", "demo", InsightType.ARCHITECTURE_RISK, Severity.HIGH, "coupling", "src/user.py", ["23 deps"], "extract auth", "2026-01-01T00:00:00Z")])
    storage.save_proposals([Proposal("proposal_1", "demo", "insight_1", "refactor", {"file": "src/user.py"}, ["high coupling"], ["reduce dependency"], "medium", 45)])
    return storage


def test_decision_accepts_implementation_plan_id(bridge):
    storage = seed_decision_storage(bridge)
    decision = DecisionManager(storage).create(project="demo", proposal_id="proposal_1", title="Extract Auth", context="complexity", options=[{"name": "keep", "risk": "high"}, {"name": "extract", "risk": "medium"}], recommendation="extract", implementation_plan_id="plan_1", execution_status="PROPOSED")
    assert decision.implementation_plan_id == "plan_1" and decision.execution_status == "PROPOSED"


def test_decision_execution_fields_default(bridge):
    storage = seed_decision_storage(bridge)
    decision = DecisionManager(storage).create(project="demo", proposal_id="proposal_1", title="Extract Auth", context="complexity", options=[{"name": "keep", "risk": "high"}, {"name": "extract", "risk": "medium"}], recommendation="extract")
    assert decision.implementation_plan_id is None and decision.execution_status is None


@pytest.mark.parametrize("execution_status", ["PROPOSED", "APPROVAL_REQUIRED", "APPROVED", "COMPLETED"])
def test_decision_execution_status_persists(bridge, execution_status):
    storage = seed_decision_storage(bridge)
    decision = DecisionManager(storage).create(project="demo", proposal_id="proposal_1", title="Extract Auth", context="complexity", options=[{"name": "keep", "risk": "high"}, {"name": "extract", "risk": "medium"}], recommendation="extract", implementation_plan_id="plan_x", execution_status=execution_status)
    reopened = IntelligenceStorage(get_settings().intelligence_db_path).get_decision(decision.id)
    assert reopened.execution_status == execution_status and reopened.implementation_plan_id == "plan_x"


@pytest.mark.parametrize("plan_id", ["plan_1", "plan_auth_2026"])
def test_decision_plan_id_in_serialization(bridge, plan_id):
    storage = seed_decision_storage(bridge)
    decision = DecisionManager(storage).create(project="demo", proposal_id="proposal_1", title="Extract Auth", context="complexity", options=[{"name": "keep", "risk": "high"}, {"name": "extract", "risk": "medium"}], recommendation="extract", implementation_plan_id=plan_id)
    assert decision.as_dict()["implementationPlanId"] == plan_id
    assert "executionStatus" in decision.as_dict()


def test_decision_api_supports_execution_fields(bridge):
    from app.code_intelligence import CodeIndex, CodeScanner
    from app.config import get_settings as settings_of

    settings = settings_of()
    CodeIndex(settings.code_index_db_path, CodeScanner(settings)).index_project("demo")
    bridge.approve(bridge.client.post("/intelligence/analyze", json={"project": "demo"}).json()["requestId"])
    proposal = bridge.client.get("/intelligence/proposals", params={"project": "demo"}).json()["proposals"][0]
    pending = bridge.client.post("/intelligence/decision/create", json={
        "project": "demo", "proposal_id": proposal["id"], "title": "Extract Auth",
        "context": "complexity", "options": [{"name": "keep", "risk": "high"}, {"name": "extract", "risk": "medium"}],
        "recommendation": "extract", "implementation_plan_id": "plan_1", "execution_status": "PROPOSED",
    })
    assert pending.status_code == 202
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    decision = executed.json()["result"]
    assert decision["implementationPlanId"] == "plan_1" and decision["executionStatus"] == "PROPOSED"
