"""Phase 28 · Engineering Graph integration tests.

The governance graph is read-only. Building it never mutates the Engineering
Graph or any other state.
"""

from __future__ import annotations

from app.intelligence.governance import GovernanceGraphBuilder

from phase28_helpers import (
    decision_outcome,
    effectiveness,
    evaluation,
    record,
    risk_finding,
)


def _graph(**overrides):
    defaults = dict(
        project="demo",
        evaluations=[],
        effectiveness=[],
        decision_outcomes=[],
        risks=[],
        governance_records=[],
    )
    defaults.update(overrides)
    return GovernanceGraphBuilder().build(**defaults)


def test_empty_graph_has_project_node():
    graph = _graph()
    assert graph["nodeCount"] >= 1
    assert any(node["node_type"] == "PROJECT" for node in graph["nodes"])


def test_empty_graph_is_readonly():
    graph = _graph()
    assert graph["readOnly"] is True
    assert graph["nodes"][0]["readOnly"] is True


def test_project_node_label():
    graph = _graph(project="demo")
    assert any(node["node_id"] == "project:demo" for node in graph["nodes"])


def test_evaluation_adds_prediction_node():
    graph = _graph(evaluations=[evaluation()])
    assert any(node["node_type"] == "PREDICTION" for node in graph["nodes"])
    assert any(node["node_type"] == "EVALUATION" for node in graph["nodes"])


def test_evaluation_links_prediction_to_evaluation():
    graph = _graph(evaluations=[evaluation(prediction_id="pred-1")])
    assert any(edge["source"] == "source:pred-1" and edge["relation"] == "EVALUATED_BY" for edge in graph["edges"])


def test_project_has_prediction_edge():
    graph = _graph(evaluations=[evaluation(prediction_id="pred-1")])
    assert any(edge["source"] == "project:demo" and edge["target"] == "source:pred-1" for edge in graph["edges"])


def test_agent_node_and_edges():
    graph = _graph(evaluations=[evaluation(agent_id="agent-9")])
    assert any(node["node_id"] == "agent:agent-9" for node in graph["nodes"])
    assert any(edge["source"] == "agent:agent-9" and edge["relation"] == "PRODUCED" for edge in graph["edges"])


def test_model_node_added():
    graph = _graph(evaluations=[evaluation(model_id="router")])
    assert any(node["node_id"] == "model:router" for node in graph["nodes"])


def test_effectiveness_adds_recommendation_nodes():
    graph = _graph(effectiveness=[effectiveness(recommendation_id="rec-1")])
    assert any(node["node_id"] == "recommendation:rec-1" for node in graph["nodes"])


def test_decision_nodes_added():
    graph = _graph(decision_outcomes=[decision_outcome(decision_id="dec-1")])
    assert any(node["node_id"] == "decision:dec-1" for node in graph["nodes"])


def test_risk_node_links_to_source():
    graph = _graph(
        evaluations=[evaluation(prediction_id="pred-1")],
        risks=[risk_finding(source_id="pred-1")],
    )
    assert any(edge["source"] == "source:pred-1" and edge["relation"] == "HAS_RISK" for edge in graph["edges"])


def test_governance_finding_linked_from_risk():
    graph = _graph(
        evaluations=[evaluation(prediction_id="pred-1")],
        risks=[risk_finding(source_id="pred-1")],
        governance_records=[record(source_id="pred-1")],
    )
    assert any(node["node_type"] == "GOVERNANCE_FINDING" for node in graph["nodes"])
    assert any(edge["relation"] == "GOVERNED_BY" for edge in graph["edges"])


def test_governance_finding_only_linked_to_matching_source():
    graph = _graph(
        risks=[risk_finding(source_id="pred-1")],
        governance_records=[record(source_id="pred-other")],
    )
    assert not any(edge["relation"] == "GOVERNED_BY" for edge in graph["edges"])


def test_nodes_deduplicated():
    graph = _graph(evaluations=[evaluation(prediction_id="pred-1"), evaluation(prediction_id="pred-1")])
    ids = [node["node_id"] for node in graph["nodes"]]
    assert len(ids) == len(set(ids))


def test_edges_have_unique_ids():
    graph = _graph(evaluations=[evaluation(prediction_id="pred-1")])
    ids = [edge["edge_id"] for edge in graph["edges"]]
    assert len(ids) == len(set(ids))


def test_counts_match():
    graph = _graph(evaluations=[evaluation()])
    assert graph["nodeCount"] == len(graph["nodes"])
    assert graph["edgeCount"] == len(graph["edges"])


def test_graph_build_is_deterministic():
    kwargs = dict(evaluations=[evaluation(prediction_id="pred-1")], risks=[risk_finding(source_id="pred-1")])
    first = _graph(**kwargs)
    second = _graph(**kwargs)
    assert first == second


def test_graph_never_mutates_store(tmp_path):
    from phase28_helpers import governance_store, validation_store

    gov = governance_store(tmp_path / "g.db")
    validation = validation_store(tmp_path / "i.db")
    validation.save_evaluation(evaluation(prediction_id="pred-1"))
    gov.save_record(record(source_id="pred-1"))
    before_gov = gov.records("demo")
    before_val = validation.evaluations("demo")
    GovernanceGraphBuilder().build(
        project="demo",
        evaluations=before_val,
        effectiveness=[],
        decision_outcomes=[],
        risks=[],
        governance_records=before_gov,
    )
    assert gov.records("demo") == before_gov
    assert validation.evaluations("demo") == before_val


def test_graph_readonly_flags_on_edges():
    graph = _graph(evaluations=[evaluation(prediction_id="pred-1")])
    assert all(edge["readOnly"] is True for edge in graph["edges"])
