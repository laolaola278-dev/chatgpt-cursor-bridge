from __future__ import annotations

import pytest

from app.task import DependencyCycleError, TaskDependencyGraph


def graph(tmp_path):
    return TaskDependencyGraph(tmp_path / "dependencies.jsonl")


def test_add_dependency(tmp_path):
    edge = graph(tmp_path).add(source_task="requirement", target_task="architecture")
    assert edge.source_task == "requirement"


def test_dependency_type_is_persisted(tmp_path):
    graph(tmp_path).add(source_task="a", target_task="b", dependency_type="blocks")
    assert graph(tmp_path).list()[0].dependency_type == "blocks"


def test_duplicate_dependency_is_idempotent(tmp_path):
    item = graph(tmp_path); first = item.add(source_task="a", target_task="b"); second = item.add(source_task="a", target_task="b")
    assert first == second and len(item.list()) == 1


def test_dependencies_for_target(tmp_path):
    item = graph(tmp_path); item.add(source_task="a", target_task="c"); item.add(source_task="b", target_task="c")
    assert {edge.source_task for edge in item.dependencies_for("c")} == {"a", "b"}


def test_dependents_for_source(tmp_path):
    item = graph(tmp_path); item.add(source_task="a", target_task="b"); item.add(source_task="a", target_task="c")
    assert {edge.target_task for edge in item.dependents_for("a")} == {"b", "c"}


def test_task_filter_returns_incident_edges(tmp_path):
    item = graph(tmp_path); item.add(source_task="a", target_task="b"); item.add(source_task="b", target_task="c")
    assert len(item.list("b")) == 2


def test_direct_cycle_is_rejected(tmp_path):
    item = graph(tmp_path); item.add(source_task="a", target_task="b")
    with pytest.raises(DependencyCycleError): item.add(source_task="b", target_task="a")


def test_indirect_cycle_is_rejected(tmp_path):
    item = graph(tmp_path); item.add(source_task="a", target_task="b"); item.add(source_task="b", target_task="c")
    with pytest.raises(DependencyCycleError): item.add(source_task="c", target_task="a")


def test_self_dependency_is_rejected(tmp_path):
    with pytest.raises(DependencyCycleError): graph(tmp_path).add(source_task="a", target_task="a")

@pytest.mark.parametrize("kind", ["depends_on", "blocks", "requires_review"])
def test_supported_dependency_types(tmp_path, kind):
    assert graph(tmp_path).add(source_task="a", target_task="b", dependency_type=kind).dependency_type == kind


def test_unknown_dependency_type_is_rejected(tmp_path):
    with pytest.raises(Exception): graph(tmp_path).add(source_task="a", target_task="b", dependency_type="executes")


def test_empty_source_is_rejected(tmp_path):
    with pytest.raises(DependencyCycleError): graph(tmp_path).add(source_task="", target_task="b")


def test_empty_target_is_rejected(tmp_path):
    with pytest.raises(DependencyCycleError): graph(tmp_path).add(source_task="a", target_task="")


def test_acyclic_graph_reports_false(tmp_path):
    item = graph(tmp_path); item.add(source_task="a", target_task="b"); item.add(source_task="b", target_task="c")
    assert item.has_cycle() is False


def test_graph_serialization_reports_edges(tmp_path):
    item = graph(tmp_path); item.add(source_task="a", target_task="b")
    value = item.as_dict("b")
    assert value["taskId"] == "b" and value["dependencies"][0]["sourceTask"] == "a"
