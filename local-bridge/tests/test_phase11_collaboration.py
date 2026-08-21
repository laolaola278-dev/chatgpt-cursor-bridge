from __future__ import annotations

import pytest

from app.audit.logger import AuditLogger
from app.collaboration import AgentCoordinator, CollaborationCommunication, CollaborationStorage, ConflictManager
from app.collaboration.models import AgentTeamStatus, CollaborationMessageType
from app.event import EventBus, EventStorage
from app.metrics import AgentMetrics, MetricsManager
from app.quality import MultiAgentQualityEvaluator
from app.security.validator import ApprovalError, ValidationFailed
from app.task import DependencyCycleError, TaskDependencyGraph


def parts(tmp_path):
    audit = AuditLogger(tmp_path / "logs" / "audit.jsonl")
    storage = CollaborationStorage(tmp_path / "collaboration")
    events = EventBus(EventStorage(tmp_path / "events"), audit)
    return audit, storage, AgentCoordinator(storage, audit, events)


def test_team_create_has_scoped_members(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    assert team.status is AgentTeamStatus.CREATED and team.members == ["ag_1", "ag_2"]


def test_team_persists_across_storage_instances(tmp_path):
    _, storage, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    assert CollaborationStorage(tmp_path / "collaboration").get_team(team.id).id == team.id


def test_team_list_filters_workflow(tmp_path):
    _, _, coordinator = parts(tmp_path)
    coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    coordinator.create_team(workflow_id="wf_2", members=["ag_1", "ag_2"], leader="ag_2")
    assert len(coordinator.list("wf_1")) == 1

@pytest.mark.parametrize("target", [AgentTeamStatus.PLANNING, AgentTeamStatus.FAILED])
def test_team_created_transitions(tmp_path, target):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    assert coordinator.transition(team.id, target).status is target


def test_team_planning_to_approval_to_review(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    coordinator.transition(team.id, "PLANNING")
    coordinator.transition(team.id, "WAITING_APPROVAL")
    coordinator.transition(team.id, "REVIEWING")
    assert coordinator.transition(team.id, "COMPLETED").status is AgentTeamStatus.COMPLETED


def test_team_invalid_transition_rejected(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    with pytest.raises(ApprovalError): coordinator.transition(team.id, "COMPLETED")


def test_team_unknown_status_rejected(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    with pytest.raises(ValidationFailed): coordinator.transition(team.id, "NOPE")

@pytest.mark.parametrize("members,leader", [([], "ag_1"), (["ag_1"], "ag_1"), (["ag_1", "ag_2"], "ag_3")])
def test_team_requires_valid_membership(tmp_path, members, leader):
    _, _, coordinator = parts(tmp_path)
    with pytest.raises(ValidationFailed): coordinator.create_team(workflow_id="wf_1", members=members, leader=leader)


def test_planner_has_five_ordered_roles(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    plan = coordinator.plan(team.id, ["task_1"])
    assert plan.ordered_roles == ("PLANNER", "ARCHITECT", "CODER", "TESTER", "REVIEWER")
    assert plan.as_dict()["requiresApproval"] is True


def test_assignment_is_proposal_only(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    proposal = coordinator.propose_assignment(team.id, agent_id="ag_2", task_id="task_1")
    assert proposal["requiresApproval"] is True and proposal["execution"] == "blocked"


def test_assignment_rejects_non_member(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    with pytest.raises(ValidationFailed): coordinator.propose_assignment(team.id, agent_id="ag_3", task_id="task_1")


def test_coordinator_cannot_execute(tmp_path):
    _, _, coordinator = parts(tmp_path)
    with pytest.raises(ApprovalError): coordinator.execute("action")


def test_coordinator_collects_without_execution(tmp_path):
    _, _, coordinator = parts(tmp_path)
    team = coordinator.create_team(workflow_id="wf_1", members=["ag_1", "ag_2"], leader="ag_1")
    result = coordinator.collect_result(team.id, {"status": "reported"})
    assert result["execution"] == "not performed"

@pytest.mark.parametrize("kind", list(CollaborationMessageType))
def test_negotiation_messages_are_typed_and_stored(tmp_path, kind):
    audit, storage, _ = parts(tmp_path)
    message = CollaborationCommunication(storage, audit).send(message_type=kind, sender="ag_1", receiver="ag_2", task_id="task_1", workflow_id="wf_1", context="proposal discussion")
    assert message.message_type is kind and storage.list_messages()[0]["type"] == kind.value


def test_negotiation_rejects_same_agent(tmp_path):
    _, storage, _ = parts(tmp_path)
    with pytest.raises(ValueError): CollaborationCommunication(storage).send(message_type="DISCUSS", sender="ag_1", receiver="ag_1", task_id="task_1", workflow_id="wf_1", context="x")


def test_conflict_is_open_and_audited(tmp_path):
    audit, storage, _ = parts(tmp_path)
    conflict = ConflictManager(storage, audit).create(workflow_id="wf_1", task_id="task_1", agents=["ag_1", "ag_2"], issue="database", options=["postgres", "sqlite"])
    assert conflict.status == "OPEN" and any(entry["action"] == "conflict_created" for entry in audit.read_entries())


def test_conflict_cannot_auto_resolve(tmp_path):
    _, storage, _ = parts(tmp_path)
    conflict = ConflictManager(storage).create(workflow_id="wf_1", task_id="task_1", agents=["ag_1", "ag_2"], issue="database", options=["postgres", "sqlite"])
    with pytest.raises(ApprovalError): ConflictManager(storage).resolve(conflict.id, "sqlite")


def test_conflict_requires_known_option(tmp_path):
    _, storage, _ = parts(tmp_path)
    conflict = ConflictManager(storage).create(workflow_id="wf_1", task_id="task_1", agents=["ag_1", "ag_2"], issue="database", options=["postgres", "sqlite"])
    with pytest.raises(ValidationFailed): ConflictManager(storage).resolve(conflict.id, "mysql", human_confirmed=True)


def test_conflict_human_resolution_persists(tmp_path):
    _, storage, _ = parts(tmp_path)
    manager = ConflictManager(storage)
    conflict = manager.create(workflow_id="wf_1", task_id="task_1", agents=["ag_1", "ag_2"], issue="database", options=["postgres", "sqlite"])
    resolved = manager.resolve(conflict.id, "sqlite", human_confirmed=True)
    assert resolved.status == "RESOLVED" and CollaborationStorage(tmp_path / "collaboration").get_conflict(conflict.id).resolution == "sqlite"


def test_metrics_default_does_not_grant_permissions(tmp_path):
    manager = MetricsManager(tmp_path / "metrics")
    metrics = manager.get("ag_1")
    assert metrics.tasks_completed == 0 and not hasattr(metrics, "permissions")

@pytest.mark.parametrize("completed", [True, False])
def test_metrics_record_task(tmp_path, completed):
    manager = MetricsManager(tmp_path / "metrics")
    metrics = manager.record_task("ag_1", completed=completed, quality=80)
    assert (metrics.tasks_completed if completed else metrics.failed_tasks) == 1


def test_metrics_quality_is_bounded(tmp_path):
    metrics = MetricsManager(tmp_path / "metrics").record_review("ag_1", 120)
    assert metrics.review_score == 100


def test_metrics_average_quality_is_persisted(tmp_path):
    manager = MetricsManager(tmp_path / "metrics")
    manager.record_task("ag_1", completed=True, quality=90)
    assert manager.get("ag_1").average_quality == 90


def test_metrics_list_reads_records(tmp_path):
    manager = MetricsManager(tmp_path / "metrics")
    manager.record_task("ag_1", completed=True)
    manager.record_task("ag_2", completed=False)
    assert {item.agent_id for item in manager.list()} == {"ag_1", "ag_2"}


def test_metrics_audit_is_metadata_only(tmp_path):
    audit = AuditLogger(tmp_path / "audit.jsonl")
    MetricsManager(tmp_path / "metrics", audit).record_task("ag_1", completed=True)
    assert any(entry["action"] == "agent_metrics_updated" for entry in audit.read_entries())


def test_quality_gate_consensus_and_dimensions():
    report = MultiAgentQualityEvaluator().evaluate(architecture_quality=90, code_quality=85, test_quality=95, review_quality=88, agent_scores={"ag_1": 90, "ag_2": 85})
    assert report.score == 90 and report.agent_consensus is True and report.blocking_issues == []


def test_quality_gate_detects_disagreement():
    report = MultiAgentQualityEvaluator().evaluate(agent_scores={"ag_1": 95, "ag_2": 40})
    assert report.agent_consensus is False and "agent_consensus_missing" in report.blocking_issues

@pytest.mark.parametrize("risk", ["low", "medium", "high", "critical"])
def test_quality_gate_risk_levels(risk):
    report = MultiAgentQualityEvaluator().evaluate(architecture_quality=80, code_quality=80, test_quality=80, review_quality=80, risk=risk)
    assert report.risk == risk


def test_quality_gate_requires_test_quality():
    report = MultiAgentQualityEvaluator().evaluate(test_quality=20)
    assert "test_quality_below_gate" in report.blocking_issues


def test_quality_gate_requires_review_quality():
    report = MultiAgentQualityEvaluator().evaluate(review_quality=20)
    assert "review_quality_below_gate" in report.blocking_issues


def test_quality_gate_human_review_for_high_risk():
    report = MultiAgentQualityEvaluator().evaluate(risk="high")
    assert "risk_requires_human_review" in report.blocking_issues


def test_quality_gate_score_is_bounded():
    report = MultiAgentQualityEvaluator().evaluate(architecture_quality=100, code_quality=100, test_quality=100, review_quality=100, risk="critical")
    assert 0 <= report.score <= 100


def test_quality_gate_is_serializable():
    value = MultiAgentQualityEvaluator().evaluate().as_dict()
    assert {"score", "agentConsensus", "blockingIssues", "dimensions", "risk"}.issubset(value)


def test_quality_gate_does_not_execute_actions():
    report = MultiAgentQualityEvaluator().evaluate()
    assert not hasattr(report, "execute")


def test_quality_gate_empty_scores_are_not_consensus_blocked():
    report = MultiAgentQualityEvaluator().evaluate()
    assert report.agent_consensus is True
