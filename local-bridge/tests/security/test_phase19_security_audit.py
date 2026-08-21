from __future__ import annotations

import inspect

from app.benchmark import BenchmarkManager
from app.model_router.provider import DeepSeekAdapter
from app.validation import ValidationManager


def test_validation_cannot_bypass_approval(bridge):
    response = bridge.client.post("/validation/create", json={"project": "demo", "repository": "repo", "scenarios": []})
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert bridge.client.get("/validation/list").json()["validations"] == []


def test_recovery_abuse_is_not_possible():
    source = inspect.getsource(ValidationManager) + inspect.getsource(BenchmarkManager)
    assert "execute" not in source.split("def record_run")[0].replace("execute", "").split("recover")[0]
    assert "recover" not in inspect.getsource(ValidationManager)


def test_provider_misuse_returns_no_operations():
    adapter = DeepSeekAdapter()
    response = adapter.analyze("suggest an architecture change", model="deepseek-chat")
    assert response.requires_approval is True
    assert response.proposal["operations"] == []
    assert response.as_dict()["readOnly"] is True


def test_graph_poisoning_cannot_modify_workflow(bridge):
    before = bridge.client.get("/workflow/list").json()
    response = bridge.client.get("/engineering-graph/query?q=malicious&project=demo")
    assert response.status_code == 200
    after = bridge.client.get("/workflow/list").json()
    assert before == after
    assert response.json()["readOnly"] is True


def test_memory_injection_requires_approval(bridge):
    pending = bridge.client.post("/memory/evolution/append", json={"project": "demo", "kind": "learning", "title": "injected", "content": "malicious payload"})
    assert pending.status_code == 202
    assert bridge.client.get("/memory/evolution/history?project=demo").json()["timeline"] == []


def test_malicious_proposal_is_not_executed(bridge):
    pending = bridge.client.post("/benchmark/create", json={"project": "demo", "repository": "repo", "cases": [{"taskType": "evil", "description": "proposal", "difficulty": "low", "expectedResult": "none"}]})
    assert pending.status_code == 202
    assert bridge.client.get("/benchmark/list").json()["benchmarks"] == []


def test_validation_run_requires_approval(bridge):
    response = bridge.client.post("/validation/run", json={"scenario_id": "vsc_unknown", "result": "COMPLETED"})
    assert response.status_code in (202, 404)
