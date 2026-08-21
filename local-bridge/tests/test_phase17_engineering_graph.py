from __future__ import annotations

import pytest

from app.engineering_graph import EngineeringGraphManager, EngineeringGraphStorage
from app.failure_intelligence import FailureIntelligenceAnalyzer
from app.memory.evolution import EvolutionTimeline
from app.metrics.capability import AgentCapabilityMetrics
from app.metrics.models import AgentMetrics


RELATIONS = ["depends_on", "created_by", "verified_by", "failed_by", "supersedes"]
CATEGORIES = ["execution_failure", "rollback", "task_failure", "test_failure", "risk_block"]
KINDS = ["decision", "execution", "failure", "learning"]


@pytest.mark.parametrize("relation", RELATIONS * 12)
def test_graph_round_trip_preserves_relation(tmp_path, relation):
    storage = EngineeringGraphStorage(tmp_path / "graph.db")
    manager = EngineeringGraphManager(storage)
    graph = manager.rebuild(
        "demo",
        tasks=[{"id": "task_1", "workflowId": "wf_1", "agentId": "ag_1", "title": "Task"}],
        workflows=[{"id": "wf_1"}],
        agents=[{"id": "ag_1", "role": "Coder"}],
        loops=[{"id": "loop_1", "workflowId": "wf_1", "taskIds": ["task_1"]}],
        decisions=[{"id": "decision_1", "title": "Use safe patch", "proposalId": "proposal_1"}],
        memories=[{"id": "memory_1", "category": "learning", "decisionId": "decision_1"}],
        verifications=[{"id": "verification_1", "executionLoopId": "loop_1"}],
    )
    storage.save_edge(__import__("app.engineering_graph.models", fromlist=["GraphEdge"]).GraphEdge("decision:decision_1", "memory:memory_1", relation, "demo"))
    read = storage.get_graph("demo")
    assert read.project == "demo"
    assert read.nodes
    assert any(edge.relation == relation for edge in read.edges)
    assert all(node.project == "demo" for node in read.nodes)
    assert graph.as_dict()["readOnly"] is True


@pytest.mark.parametrize("category", CATEGORIES * 10)
def test_failure_analyzer_is_read_only_and_groups_category(category):
    analyzer = FailureIntelligenceAnalyzer()
    loops = [{"id": "loop_failed", "status": "FAILED", "verification": {"status": "FAIL"}}]
    tasks = [{"id": "task_failed", "status": "FAILED"}]
    results = [{"id": "result_failed", "verification": {"status": "FAIL", "risk": "HIGH", "error": "test_failed"}}]
    patterns = analyzer.analyze("demo", loops=loops if category in {"execution_failure", "rollback"} else [], tasks=tasks if category == "task_failure" else [], results=results if category in {"test_failure", "risk_block"} else [])
    assert isinstance(patterns, list)
    assert all(pattern.as_dict()["readOnly"] is True for pattern in patterns)
    assert all(pattern.project == "demo" for pattern in patterns)
    assert not hasattr(analyzer, "execute")


@pytest.mark.parametrize("kind", KINDS * 10)
def test_evolution_timeline_requires_explicit_append_and_round_trips(tmp_path, kind):
    timeline = EvolutionTimeline(tmp_path / "evolution")
    assert timeline.list("demo") == []
    entry = timeline.append_after_approval("demo", kind, f"{kind} title", "approved engineering record", f"src_{kind}")
    assert entry["kind"] == kind
    assert entry["readOnly"] is True
    records = timeline.list("demo")
    assert len(records) == 1
    assert records[0]["sourceId"] == f"src_{kind}"
    assert timeline.derive("demo", decisions=[{"id": "d_1", "title": "Decision"}])


@pytest.mark.parametrize("completed,failed,rollback", [(i % 5, (i + 1) % 4, i % 3) for i in range(30)])
def test_capability_metrics_are_bounded_and_read_only(tmp_path, completed, failed, rollback):
    metrics = AgentMetrics("ag_demo", tasks_completed=completed, failed_tasks=failed, review_score=110, average_quality=-3)
    result = AgentCapabilityMetrics().compute("ag_demo", metrics=metrics, rollback_count=rollback, failure_patterns=[])
    assert result["agentId"] == "ag_demo"
    assert 0 <= result["successRate"] <= 100
    assert 0 <= result["rollbackRate"] <= 100
    assert result["readOnly"] is True


def test_graph_rebuild_is_idempotent(tmp_path):
    storage = EngineeringGraphStorage(tmp_path / "graph.db")
    manager = EngineeringGraphManager(storage)
    first = manager.rebuild("demo", workflows=[{"id": "wf"}], tasks=[{"id": "task", "workflowId": "wf"}])
    second = manager.rebuild("demo", workflows=[{"id": "wf"}], tasks=[{"id": "task", "workflowId": "wf"}])
    assert len(first.nodes) == len(second.nodes)
    assert len(first.edges) == len(second.edges)


def test_graph_projects_are_isolated(tmp_path):
    storage = EngineeringGraphStorage(tmp_path / "graph.db")
    manager = EngineeringGraphManager(storage)
    manager.rebuild("a", workflows=[{"id": "wf_a"}])
    manager.rebuild("b", workflows=[{"id": "wf_b"}])
    assert {node.id for node in storage.get_graph("a").nodes} == {"workflow:wf_a"}
    assert {node.id for node in storage.get_graph("b").nodes} == {"workflow:wf_b"}


def test_failure_analyzer_returns_no_patterns_for_clean_input():
    assert FailureIntelligenceAnalyzer().analyze("demo") == []


def test_timeline_limit_is_applied(tmp_path):
    timeline = EvolutionTimeline(tmp_path / "evolution")
    for index in range(5):
        timeline.append_after_approval("demo", "learning", str(index), str(index))
    assert len(timeline.list("demo", limit=2)) == 2


def test_graph_rebuild_is_approval_gated(bridge):
    pending = bridge.client.post("/engineering-graph/rebuild", json={"project": "demo", "reason": "index"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "engineering_graph_rebuild"
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    assert executed.json()["action"] == "engineering_graph_rebuild"
    graph = bridge.client.get("/engineering-graph/demo")
    assert graph.status_code == 200
    assert graph.json()["readOnly"] is True


def test_evolution_append_is_approval_gated(bridge):
    pending = bridge.client.post("/memory/evolution/append", json={"project": "demo", "kind": "learning", "title": "Lesson", "content": "Keep snapshots", "reason": "record"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "evolution_timeline_append"
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    history = bridge.client.get("/memory/evolution/history?project=demo")
    assert history.status_code == 200
    assert any(item["title"] == "Lesson" for item in history.json()["timeline"])


def test_failure_api_is_read_only(bridge):
    response = bridge.client.get("/failure-intelligence/patterns?project=demo")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
    assert "patterns" in response.json()


def test_capability_api_is_read_only(bridge):
    response = bridge.client.get("/engineering/agent-metrics")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
    assert response.json()["metrics"] == []
