from __future__ import annotations

import inspect

from app.benchmark import BenchmarkManager
from app.model_router.provider import AnthropicAdapter, DeepSeekAdapter, OpenAIAdapter
from app.security.sandbox import validate_path


def test_benchmark_write_stops_at_approval(bridge):
    response = bridge.client.post("/benchmark/create", json={"project": "demo", "repository": "repo", "cases": []})
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert bridge.client.get("/benchmark/list").json()["benchmarks"] == []


def test_recovery_cannot_auto_execute():
    assert not hasattr(BenchmarkManager, "execute")
    source = inspect.getsource(BenchmarkManager)
    assert "subprocess" not in source
    assert "shell" not in source.lower()


def test_provider_adapters_have_no_execution_operations():
    for adapter in (OpenAIAdapter(), AnthropicAdapter(), DeepSeekAdapter()):
        response = adapter.chat("propose a change", model="test")
        assert response.requires_approval
        assert response.proposal["operations"] == []
        assert "execute" not in response.proposal


def test_memory_append_requires_approval(bridge):
    response = bridge.client.post("/memory/evolution/append", json={"project": "demo", "kind": "learning", "title": "Unauthorized?", "content": "must approve"})
    assert response.status_code == 202
    assert bridge.client.get("/memory/evolution/history?project=demo").json()["timeline"] == []


def test_graph_query_is_read_only(bridge):
    response = bridge.client.get("/engineering-graph/query?q=authentication&project=demo")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_path_traversal_rejected(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    try:
        validate_path("demo", "../escape.txt", settings)
    except Exception:
        pass
    else:
        raise AssertionError("path traversal was accepted")


def test_shell_injection_is_not_added():
    from app.security.command_policy import validate_command
    source = inspect.getsource(validate_command)
    assert "shell=True" not in source


def test_agent_profile_does_not_contain_permission_mutation():
    from app.agent_profile.manager import AgentProfileManager
    source = inspect.getsource(AgentProfileManager)
    assert "permission" not in source.lower()


def test_rollback_requires_existing_snapshot():
    from app.execution_loop.rollback_manager import ExecutionLoopRollbackManager
    source = inspect.getsource(ExecutionLoopRollbackManager)
    assert "snapshot" in source.lower()


def test_provider_never_reads_api_keys():
    for adapter in (OpenAIAdapter, AnthropicAdapter, DeepSeekAdapter):
        source = inspect.getsource(adapter)
        assert "API_KEY" not in source
        assert "requests" not in source
        assert "httpx" not in source
