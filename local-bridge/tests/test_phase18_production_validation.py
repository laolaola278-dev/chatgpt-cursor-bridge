from __future__ import annotations

import hashlib

import pytest

from app.agent_profile import AgentProfileManager, AgentProfileStorage
from app.benchmark import BenchmarkManager, BenchmarkStatus, BenchmarkStorage
from app.engineering_graph import EngineeringGraphManager, EngineeringGraphStorage
from app.metrics.models import AgentMetrics
from app.model_router.provider import AnthropicAdapter, DeepSeekAdapter, OpenAIAdapter, ProviderCapabilityRegistry


@pytest.mark.parametrize("status", [BenchmarkStatus.RUNNING, BenchmarkStatus.CANCELLED])
def test_benchmark_lifecycle_transitions(tmp_path, status):
    manager = BenchmarkManager(BenchmarkStorage(tmp_path / "benchmark.db"))
    benchmark = manager.create("demo", "local/demo", [{"taskType": "review", "description": "review diff", "difficulty": "medium", "expectedResult": "report"}])
    assert benchmark.status is BenchmarkStatus.CREATED
    changed = manager.transition(benchmark.id, status.value)
    assert changed.status is status


def test_benchmark_rejects_invalid_transition(tmp_path):
    manager = BenchmarkManager(BenchmarkStorage(tmp_path / "benchmark.db"))
    benchmark = manager.create("demo", "repo", [])
    with pytest.raises(ValueError):
        manager.transition(benchmark.id, BenchmarkStatus.COMPLETED.value)


@pytest.mark.parametrize("case_count", range(1, 21))
def test_benchmark_cases_are_record_only(tmp_path, case_count):
    storage = BenchmarkStorage(tmp_path / "benchmark.db")
    benchmark = BenchmarkManager(storage).create("demo", "repo", [{"taskType": "coding", "description": str(i), "difficulty": "low", "expectedResult": "proposal"} for i in range(case_count)])
    assert len(storage.cases(benchmark.id)) == case_count
    assert not hasattr(BenchmarkManager, "execute")


def test_graph_query_returns_only_related_nodes(tmp_path):
    storage = EngineeringGraphStorage(tmp_path / "graph.db")
    manager = EngineeringGraphManager(storage)
    manager.rebuild("demo", tasks=[{"id": "task_auth", "title": "authentication failures"}, {"id": "task_other", "title": "unrelated"}])
    result = manager.query("demo", "authentication")
    assert result["readOnly"] is True
    assert any(node["id"] == "task:task_auth" for node in result["nodes"])
    assert all(node["id"] != "task:task_other" for node in result["nodes"])


@pytest.mark.parametrize("query", ["problem", "solution", "experiment", "risk", "pattern", "authentication", "rollback", "decision", "verified", "coupling"])
def test_graph_query_is_deterministic(tmp_path, query):
    storage = EngineeringGraphStorage(tmp_path / "graph.db")
    manager = EngineeringGraphManager(storage)
    manager.rebuild("demo", decisions=[{"id": "d1", "title": "authentication decision", "metadata": query}], memories=[{"id": "m1", "category": "learning"}])
    first = manager.query("demo", query)
    second = manager.query("demo", query)
    assert first == second
    assert first["readOnly"] is True


@pytest.mark.parametrize("provider", [OpenAIAdapter(), AnthropicAdapter(), DeepSeekAdapter()])
def test_provider_adapters_only_create_proposals(provider):
    response = provider.review("review authentication", model="test-model")
    assert response.requires_approval is True
    assert response.status == "adapter_only"
    assert response.proposal["operations"] == []
    assert response.as_dict()["readOnly"] is True


def test_provider_registry_is_metadata_only():
    models = ProviderCapabilityRegistry().all()
    assert {item["provider"] for item in models} == {"openai", "anthropic", "deepseek"}
    assert all(item["enabled"] is False for item in models)


@pytest.mark.parametrize("completed,failed", [(i, i % 3) for i in range(20)])
def test_agent_profile_derivation_is_analysis_only(tmp_path, completed, failed):
    manager = AgentProfileManager(AgentProfileStorage(tmp_path / "profile.db"))
    profile = manager.derive(AgentMetrics("ag_test", completed, failed, 90, 85), role="Reviewer")
    assert profile.agent_id == "ag_test"
    assert profile.role == "Reviewer"
    assert 0 <= profile.success_rate <= 100
    assert profile.as_dict()["readOnly"] is True


def test_agent_profile_storage_history(tmp_path):
    storage = AgentProfileStorage(tmp_path / "profile.db")
    profile = AgentProfileManager(storage).derive(AgentMetrics("ag_test", 3, 1, 90, 80))
    storage.save(profile)
    assert storage.get("ag_test") is not None
    assert len(storage.history("ag_test")) == 1
    assert storage.list()[0].agent_id == "ag_test"


def test_benchmark_api_requires_approval(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    pending = bridge.client.post("/benchmark/create", json={"project": "demo", "repository": "local/demo", "cases": [{"taskType": "review", "description": "review", "difficulty": "low", "expectedResult": "report"}]})
    assert pending.status_code == 202
    assert pending.json()["action"] == "benchmark_create"
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after
    assert bridge.client.get("/benchmark/list").json()["benchmarks"] == []


def test_models_api_read_only(bridge):
    response = bridge.client.get("/models")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
    assert response.json()["models"]


def test_graph_query_api_is_read_only(bridge):
    response = bridge.client.get("/engineering-graph/query?q=authentication&project=demo")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_agent_profile_api_is_read_only(bridge):
    response = bridge.client.get("/agent-profile/ag_test")
    assert response.status_code == 200
    assert response.json()["agentId"] == "ag_test"
    assert response.json()["readOnly"] is True


def test_agent_profile_ranking_api_is_read_only(bridge):
    response = bridge.client.get("/agent-profile/ranking")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_provider_capabilities_api_is_read_only(bridge):
    response = bridge.client.get("/models/capabilities?model=gpt-4o")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
    assert response.json()["capabilities"][0]["provider"] == "openai"


def test_approved_benchmark_is_still_record_only(bridge):
    pending = bridge.client.post("/benchmark/create", json={"project": "demo", "repository": "repo", "cases": []})
    assert pending.status_code == 202
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    records = bridge.client.get("/benchmark/list").json()["benchmarks"]
    assert len(records) == 1
    detail = bridge.client.get(f"/benchmark/{records[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["readOnly"] is True
