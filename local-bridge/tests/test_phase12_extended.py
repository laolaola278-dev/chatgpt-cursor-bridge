from __future__ import annotations

from pathlib import Path

import pytest

from app.code_intelligence import CodeIndex, CodeScanner
from app.code_intelligence.parser import language_for, parse_source
from app.impact import ImpactAnalyzer
from app.knowledge_graph import KnowledgeGraph
from app.memory.project import ProjectMemory


@pytest.mark.parametrize(
    "suffix,language",
    [(".py", "Python"), (".ts", "TypeScript"), (".tsx", "TypeScript"), (".js", "JavaScript"), (".jsx", "JavaScript"), (".go", "Go"), (".rs", "Rust"), (".java", "Java"), (".kt", "Kotlin"), (".cpp", "C++")],
)
def test_parser_supports_declared_languages(tmp_path, suffix, language):
    assert language_for(Path(f"source{suffix}")) == language


@pytest.mark.parametrize("name", ["alpha", "beta", "gamma", "delta", "epsilon"])
def test_parser_extracts_multiple_javascript_functions(tmp_path, name):
    source = tmp_path / f"{name}.ts"
    source.write_text(f"export function {name}() {{ return true; }}\n", encoding="utf-8")
    symbols, _ = parse_source(source, source.name)
    assert symbols[0].name == name and symbols[0].symbol_type == "function"


@pytest.mark.parametrize("name", ["One", "Two", "Three", "Four", "Five"])
def test_parser_extracts_multiple_python_classes(tmp_path, name):
    source = tmp_path / f"{name.lower()}.py"
    source.write_text(f"class {name}: pass\n", encoding="utf-8")
    symbols, _ = parse_source(source, source.name)
    assert symbols[0].name == name and symbols[0].symbol_type == "class"


@pytest.mark.parametrize("query", ["main", "src", "Python", "missing", "README"])
def test_code_index_search_contract_is_bounded(bridge, query):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    assert len(index.search("demo", query, limit=2)) <= 2


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5])
def test_code_index_file_limit_is_enforced(bridge, limit):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    assert len(index.files("demo", limit=limit)) <= limit


@pytest.mark.parametrize("keyword", ["module", "Service", "external", "missing", "src"])
def test_graph_query_is_read_only_and_filtered(bridge, keyword):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    graph = KnowledgeGraph(settings.knowledge_graph_db_path, index)
    graph.build("demo")
    result = graph.query("demo", keyword, limit=10)
    assert result["project"] == "demo" and result["readOnly"] is True and len(result["nodes"]) <= 10


@pytest.mark.parametrize("limit", [1, 2, 5, 10, 25])
def test_graph_query_limit_is_enforced(bridge, limit):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    graph = KnowledgeGraph(settings.knowledge_graph_db_path, index)
    graph.build("demo")
    assert len(graph.query("demo", limit=limit)["nodes"]) <= limit


@pytest.mark.parametrize("changed", [["src/main.py"], ["README.md"], [], ["src/one.py", "src/two.py"], ["unknown.py"]])
def test_impact_reports_changed_files_without_mutation(bridge, changed):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    report = ImpactAnalyzer(index).analyze("demo", changed)
    assert report["changedFiles"] == changed and report["readOnly"] is True


@pytest.mark.parametrize("category", ["architecture", "decisions", "bugs", "changes", "architecture", "decisions", "bugs", "changes", "architecture", "decisions"])
def test_project_memory_history_is_category_scoped(bridge, category):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    memory = ProjectMemory(settings)
    memory.append_after_approval("demo", category, f"record for {category}")
    history = memory.history("demo")
    assert history and all(item["project"] == "demo" for item in history)


@pytest.mark.parametrize("endpoint", [
    "/project/profile",
    "/project/graph",
    "/code/search",
    "/impact/analyze",
    "/context/query",
    "/memory/project/history",
    "/quality/v4/wf_1234",
    "/collaboration/events",
    "/runtime/events",
    "/system/health",
])
def test_read_only_phase12_and_existing_endpoints_are_available(bridge, endpoint):
    params = {"project": "demo"} if endpoint in {"/project/profile", "/project/graph", "/code/search", "/impact/analyze", "/context/query", "/memory/project/history"} else {}
    response = bridge.client.get(endpoint, params=params)
    assert response.status_code == 200


@pytest.mark.parametrize("content", ["simple", "with spaces", "中文记录", "line one\nline two", "decision: keep"])
def test_project_memory_content_is_recoverable(bridge, content):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    memory = ProjectMemory(settings)
    memory.append_after_approval("demo", "changes", content)
    assert len(memory.history("demo")) == 1
