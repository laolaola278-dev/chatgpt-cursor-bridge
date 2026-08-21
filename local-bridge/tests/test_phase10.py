"""Phase 10 autonomous runtime tests.

These tests exercise metadata-only lifecycle behavior. They deliberately never
invoke a shell or an execution implementation.
"""

from __future__ import annotations

import json

import pytest

from app.audit.logger import AuditLogger
from app.event import EventBus, EventStorage, EventType
from app.quality import QualityEvaluator
from app.runtime import RuntimeExecutor, RuntimeRecovery, RuntimeScheduler, RuntimeState, RuntimeStateStore
from app.security.validator import ApprovalError
from app.task import TaskManager, TaskStatus, TaskStorage, TaskTransitionError


def runtime_parts(tmp_path):
    audit = AuditLogger(tmp_path / "logs" / "audit.jsonl")
    events = EventBus(EventStorage(tmp_path / "events"), audit)
    tasks = TaskManager(TaskStorage(tmp_path / "task.db"), audit, events)
    scheduler = RuntimeScheduler(store=RuntimeStateStore(tmp_path / "runtimes"), tasks=tasks, audit=audit, events=events)
    return audit, events, tasks, scheduler


@pytest.mark.parametrize("target", [RuntimeState.READY, RuntimeState.FAILED], ids=["ready", "failed"])
def test_runtime_created_transitions(tmp_path, target):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    assert runtime.state is RuntimeState.CREATED
    assert scheduler.transition(runtime.id, target).state is target


def test_runtime_ready_running_waiting_approval(tmp_path):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    scheduler.transition(runtime.id, "RUNNING")
    assert scheduler.transition(runtime.id, "WAITING_APPROVAL").state is RuntimeState.WAITING_APPROVAL


def test_runtime_waiting_approval_can_return_to_running(tmp_path):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    scheduler.transition(runtime.id, "RUNNING")
    scheduler.transition(runtime.id, "WAITING_APPROVAL")
    assert scheduler.transition(runtime.id, "RUNNING").state is RuntimeState.RUNNING


def test_runtime_waiting_feedback_lifecycle(tmp_path):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    scheduler.transition(runtime.id, "RUNNING")
    scheduler.transition(runtime.id, "WAITING_FEEDBACK")
    assert scheduler.transition(runtime.id, "COMPLETED").state is RuntimeState.COMPLETED


def test_runtime_failed_is_terminal(tmp_path):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    failed = scheduler.transition(runtime.id, "FAILED")
    with pytest.raises(ApprovalError): scheduler.transition(failed.id, "READY")


@pytest.mark.parametrize("target", ["RUNNING", "WAITING_APPROVAL", "COMPLETED", "RECOVERED", "UNKNOWN"])
def test_invalid_created_runtime_transitions_are_rejected(tmp_path, target):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    if target == "UNKNOWN":
        with pytest.raises(ApprovalError): scheduler.transition(runtime.id, target)
    elif target == "RUNNING" or target == "WAITING_APPROVAL" or target == "COMPLETED" or target == "RECOVERED":
        with pytest.raises(ApprovalError): scheduler.transition(runtime.id, target)


def test_runtime_persists_across_store_instances(tmp_path):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    restored = RuntimeStateStore(tmp_path / "runtimes").get(runtime.id)
    assert restored.id == runtime.id and restored.state is RuntimeState.CREATED


def test_runtime_audits_and_events_lifecycle(tmp_path):
    audit, events, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    assert any(entry["action"] == "runtime_created" for entry in audit.read_entries())
    assert events.list_events()[0].event_type == EventType.RUNTIME_CREATED.value


def test_runtime_recovery_never_resumes(tmp_path):
    audit, events, tasks, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    scheduler.transition(runtime.id, "RUNNING")
    recovered = RuntimeRecovery(scheduler, audit, events).recover()
    assert recovered[0]["autoResumed"] is False
    assert scheduler.get(runtime.id).state is RuntimeState.RECOVERED
    assert scheduler.proposals(runtime.id) == []


def test_recovered_runtime_requires_explicit_ready_transition(tmp_path):
    _, _, _, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    scheduler.transition(runtime.id, "RUNNING")
    RuntimeRecovery(scheduler).recover()
    assert scheduler.transition(runtime.id, "READY").state is RuntimeState.READY


def test_scheduler_requires_active_and_bound_runtime_dependencies(tmp_path):
    _, _, tasks, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1", context={"action": "file.write"})
    assert scheduler.proposals(runtime.id)


def test_scheduler_filters_other_tasks(tmp_path):
    _, _, tasks, scheduler = runtime_parts(tmp_path)
    runtime = scheduler.create(agent_id="ag_1", session_id="ses_1", workflow_id="wf_1", stage_id="stg_1")
    scheduler.transition(runtime.id, "READY")
    tasks.create_task(workflow_id="wf_other", stage_id="stg_1", agent_id="ag_1")
    assert scheduler.proposals(runtime.id) == []


def test_scheduler_execute_is_forbidden(tmp_path):
    _, _, _, scheduler = runtime_parts(tmp_path)
    with pytest.raises(ApprovalError): scheduler.execute("proposal")
    with pytest.raises(ApprovalError): RuntimeExecutor().execute({"action": "file.write"})


def test_event_publish_subscribe_and_recovery(tmp_path):
    audit = AuditLogger(tmp_path / "audit.jsonl")
    storage = EventStorage(tmp_path / "events")
    bus = EventBus(storage, audit)
    seen = []
    bus.subscribe(EventType.TASK_CREATED, seen.append)
    event = bus.publish(EventType.TASK_CREATED, source="test", payload={"id": "task_1"})
    assert seen[0].event_id == event.event_id
    recovered = bus.recover_events()
    assert recovered["valid"] is True and len(recovered["events"]) == 1


def test_event_tamper_is_detected(tmp_path):
    storage = EventStorage(tmp_path / "events")
    bus = EventBus(storage)
    bus.publish("task.created", source="test", payload={"id": "task_1"})
    path = tmp_path / "events" / "runtime.jsonl"
    raw = json.loads(path.read_text().splitlines()[0]); raw["payload"]["id"] = "tampered"
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    recovered = storage.recover_events()
    assert recovered["valid"] is False and recovered["invalidCount"] == 1


def test_event_audit_has_matching_audit_id(tmp_path):
    audit = AuditLogger(tmp_path / "audit.jsonl")
    event = EventBus(EventStorage(tmp_path / "events"), audit).publish("memory.updated", source="test", payload={})
    assert any(entry.get("auditId") == event.audit_id for entry in audit.read_entries())


@pytest.mark.parametrize("status", [TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL, TaskStatus.BLOCKED, TaskStatus.CANCELLED])
def test_task_pending_valid_transitions(tmp_path, status):
    _, _, tasks, _ = runtime_parts(tmp_path)
    task = tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1")
    assert tasks.transition(task.id, status).status is status


@pytest.mark.parametrize("status", ["NOPE", "done", "EXECUTING"])
def test_task_unknown_status_rejected(tmp_path, status):
    _, _, tasks, _ = runtime_parts(tmp_path)
    task = tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1")
    with pytest.raises(TaskTransitionError): tasks.transition(task.id, status)


def test_task_crud_and_persistence(tmp_path):
    _, _, tasks, _ = runtime_parts(tmp_path)
    task = tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1", priority=9, context={"action": "test.run"})
    assert tasks.get_task(task.id).priority == 9
    assert TaskManager(TaskStorage(tmp_path / "task.db")).get_task(task.id).context["action"] == "test.run"


def test_task_start_complete(tmp_path):
    _, _, tasks, _ = runtime_parts(tmp_path)
    task = tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1")
    assert tasks.start_task(task.id).status is TaskStatus.RUNNING
    assert tasks.complete_task(task.id).status is TaskStatus.COMPLETED


def test_task_cancel_is_terminal(tmp_path):
    _, _, tasks, _ = runtime_parts(tmp_path)
    task = tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1")
    cancelled = tasks.cancel_task(task.id)
    with pytest.raises(TaskTransitionError): tasks.start_task(cancelled.id)


def test_task_list_priority_order(tmp_path):
    _, _, tasks, _ = runtime_parts(tmp_path)
    tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1", priority=1)
    high = tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1", priority=10)
    assert tasks.list_tasks()[0].id == high.id


def test_task_completed_event(tmp_path):
    _, events, tasks, _ = runtime_parts(tmp_path)
    task = tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1")
    tasks.start_task(task.id); tasks.complete_task(task.id)
    assert any(event.event_type == EventType.TASK_COMPLETED.value for event in events.list_events())


def test_task_invalid_priority(tmp_path):
    _, _, tasks, _ = runtime_parts(tmp_path)
    with pytest.raises(TaskTransitionError): tasks.create_task(workflow_id="wf_1", stage_id="stg_1", agent_id="ag_1", priority=101)


@pytest.mark.parametrize("risk,expected", [("low", "low"), ("medium", "medium"), ("high", "high"), ("critical", "critical")])
def test_quality_risk_mapping(risk, expected):
    report = QualityEvaluator().evaluate(risk=risk, test_result={"passed": True}, memory_recorded=True)
    assert report.risk == expected


@pytest.mark.parametrize("passed", [True, False, None])
def test_quality_test_result_signal(passed):
    result = {} if passed is None else {"passed": passed}
    report = QualityEvaluator().evaluate(test_result=result)
    if passed is False: assert "test_result_failed" in report.blocking_issues
    if passed is None: assert "test_result_missing" in report.blocking_issues


def test_quality_modified_file_penalty():
    small = QualityEvaluator().evaluate(git_diff={"files": ["a.py"]}, test_result={"passed": True})
    large = QualityEvaluator().evaluate(git_diff={"files": [str(i) for i in range(15)]}, test_result={"passed": True})
    assert large.quality_score < small.quality_score


def test_quality_memory_penalty():
    with_memory = QualityEvaluator().evaluate(test_result={"passed": True}, memory_recorded=True)
    without_memory = QualityEvaluator().evaluate(test_result={"passed": True}, memory_recorded=False)
    assert without_memory.quality_score < with_memory.quality_score


def test_quality_high_risk_blocks_human_delivery():
    report = QualityEvaluator().evaluate(risk="high", test_result={"passed": True})
    assert "high_risk_requires_human_review" in report.blocking_issues


def test_quality_critical_test_failure_is_critical():
    report = QualityEvaluator().evaluate(risk="critical", test_result={"passed": False})
    assert report.risk == "critical" and report.quality_score == 25


def test_quality_score_is_bounded():
    report = QualityEvaluator().evaluate(git_diff={"files": [str(i) for i in range(100)]}, test_result={"passed": False}, risk="critical", memory_recorded=False)
    assert 0 <= report.quality_score <= 100


def test_quality_report_is_serializable():
    report = QualityEvaluator().evaluate(test_result={"passed": True})
    value = report.as_dict()
    assert set(value) == {"qualityScore", "risk", "blockingIssues", "checks"}


def test_quality_neutral_report_has_no_blockers_when_observations_are_complete():
    report = QualityEvaluator().evaluate(git_diff={"files": ["a.py"]}, test_result={"passed": True}, risk="low", memory_recorded=True)
    assert report.blocking_issues == [] and report.quality_score == 100
