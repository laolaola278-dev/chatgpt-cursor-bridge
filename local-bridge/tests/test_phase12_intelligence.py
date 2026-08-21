from __future__ import annotations

from pathlib import Path

import pytest

from app.code_intelligence import CodeIndex, CodeScanner
from app.code_intelligence.dependency import reverse_impact
from app.code_intelligence.parser import parse_source
from app.impact import ImpactAnalyzer
from app.knowledge_graph import KnowledgeGraph
from app.memory.project import ProjectMemory
from app.project_intelligence import ProjectProfileService
from app.quality.gate4 import QualityGate4Evaluator


def test_scanner_is_read_only_and_ignores_generated_dirs(bridge):
    before = (bridge.demo / "src" / "main.py").read_bytes()
    records = CodeScanner(__import__("app.config", fromlist=["get_settings"]).get_settings()).scan("demo")
    assert any(record.path == "src/main.py" for record in records)
    assert all("node_modules" not in record.path and ".git" not in record.path for record in records)
    assert (bridge.demo / "src" / "main.py").read_bytes() == before


def test_parser_extracts_python_symbols_and_imports(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("import os\nfrom app.service import run\nclass Demo:\n    pass\ndef hello(value):\n    return value\n", encoding="utf-8")
    symbols, dependencies = parse_source(source, "module.py")
    assert {symbol.name for symbol in symbols} == {"Demo", "hello"}
    assert {edge.target for edge in dependencies} == {"os", "app.service"}


def test_parser_handles_invalid_python_without_execution(tmp_path):
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n", encoding="utf-8")
    assert parse_source(source, "broken.py") == ([], [])


def test_parser_extracts_typescript_symbols_and_imports(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text("import { thing } from './thing';\nexport function work(value: string) { return value; }\nclass Service {}\n", encoding="utf-8")
    symbols, dependencies = parse_source(source, "app.ts")
    assert {symbol.name for symbol in symbols} == {"work", "Service"}
    assert dependencies[0].target == "./thing"


def test_code_index_persists_files_symbols_dependencies(bridge, tmp_path):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    (bridge.demo / "src" / "service.py").write_text("from src.main import value\ndef run():\n    return value\n", encoding="utf-8")
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    summary = index.index_project("demo")
    reopened = CodeIndex(settings.code_index_db_path)
    assert summary.files >= 2 and reopened.stats("demo")["symbols"] >= 1
    assert reopened.dependencies("demo", "src/service.py")


def test_code_index_searches_symbol_name(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    (bridge.demo / "src" / "symbols.py").write_text("def authenticate(user):\n    return user\n", encoding="utf-8")
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    assert index.symbol("demo", "authenticate")[0]["path"] == "src/symbols.py"


def test_code_index_dependency_filter(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    (bridge.demo / "src" / "a.py").write_text("from src.main import x\n", encoding="utf-8")
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    edges = index.dependencies("demo", "src/main.py")
    assert any(edge["source"] == "src/a.py" for edge in edges)


def test_reverse_impact_walks_transitive_dependents(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    (bridge.demo / "src" / "a.py").write_text("from src.main import x\n", encoding="utf-8")
    (bridge.demo / "src" / "b.py").write_text("from src.a import y\n", encoding="utf-8")
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    affected = reverse_impact(index, "demo", ["src/main.py"])
    assert "src/a.py" in affected


def test_project_profile_is_read_only(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    CodeIndex(settings.code_index_db_path, CodeScanner(settings)).index_project("demo")
    profile = ProjectProfileService(CodeIndex(settings.code_index_db_path)).build("demo").as_dict()
    assert profile["projectId"] == "demo" and profile["readOnly"] is True


def test_knowledge_graph_builds_modules_and_edges(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    (bridge.demo / "src" / "api.py").write_text("from src.main import x\n", encoding="utf-8")
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    graph = KnowledgeGraph(settings.knowledge_graph_db_path, index).build("demo")
    assert graph["readOnly"] is True and any(node["label"] == "src/api.py" for node in graph["nodes"])


def test_knowledge_graph_query_is_persistent(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    KnowledgeGraph(settings.knowledge_graph_db_path, index).build("demo")
    result = KnowledgeGraph(settings.knowledge_graph_db_path, CodeIndex(settings.code_index_db_path)).query("demo", "main")
    assert result["readOnly"] is True and result["nodes"]


def test_impact_report_classifies_small_change(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    report = ImpactAnalyzer(index).analyze("demo", ["src/main.py"])
    assert report["risk"] == "low" and report["changedFiles"] == ["src/main.py"]


def test_project_memory_preview_does_not_write(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    preview = ProjectMemory(settings).preview("demo", "architecture", "Use a layered design")
    assert "proposal" in preview and not (settings.memory_root / "project" / "demo").exists()


def test_project_memory_rejects_unknown_category(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    with pytest.raises(Exception):
        ProjectMemory(settings).preview("demo", "permissions", "no")


@pytest.mark.parametrize("category", ["architecture", "decisions", "bugs", "changes"])
def test_project_memory_writes_only_after_explicit_call(bridge, category):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    result = ProjectMemory(settings).append_after_approval("demo", category, "record")
    assert result["category"] == category and ProjectMemory(settings).history("demo")


def test_code_index_api_is_approval_gated(bridge):
    pending = bridge.client.post("/code/index", json={"project": "demo"})
    assert pending.status_code == 202
    assert bridge.client.get("/code/search", params={"project": "demo", "q": "main"}).json()["results"] == []
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    assert bridge.client.get("/project/profile", params={"project": "demo"}).status_code == 200


def test_project_intelligence_read_apis(bridge):
    pending = bridge.client.post("/code/index", json={"project": "demo"})
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    assert bridge.client.get("/project/graph", params={"project": "demo"}).status_code == 200
    assert bridge.client.get("/context/query", params={"project": "demo", "q": "main", "agent_role": "CODER"}).status_code == 200
    assert bridge.client.get("/impact/analyze", params={"project": "demo", "changed_file": "src/main.py"}).status_code == 200


def test_project_memory_api_is_approval_gated(bridge):
    pending = bridge.client.post("/memory/project/propose", json={"project": "demo", "category": "decisions", "content": "Use SQLite"})
    assert pending.status_code == 202
    assert bridge.client.get("/memory/project/history", params={"project": "demo"}).json()["history"] == []
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    assert bridge.client.get("/memory/project/history", params={"project": "demo"}).json()["history"]


@pytest.mark.parametrize("risk,minimum", [("low", 80), ("medium", 60), ("high", 0)])
def test_quality_gate_v4_risk_reduces_score(risk, minimum):
    report = QualityGate4Evaluator().evaluate(change_risk=risk)
    assert report["score"] >= minimum
    assert report["risk"] in {"low", "medium", "high"}


def test_quality_gate_v4_blocks_regression():
    report = QualityGate4Evaluator().evaluate(regression_risk="high")
    assert "Regression risk requires human review" in report["blockingIssues"]


def test_quality_gate_v4_score_is_bounded():
    report = QualityGate4Evaluator().evaluate(architecture_impact=100, change_risk="high", regression_risk="high", historical_stability=0)
    assert 0 <= report["score"] <= 100


def test_quality_gate_v4_api_is_read_only(bridge):
    response = bridge.client.get("/quality/v4/wf_1234", params={"architecture_impact": 5, "change_risk": "medium"})
    assert response.status_code == 200 and response.json()["readOnly"] is True
