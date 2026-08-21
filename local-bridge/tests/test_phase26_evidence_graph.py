from __future__ import annotations

import pytest

from app.intelligence.evidence_graph import EvidenceRelation, IntelligenceEvidenceGraph
from app.intelligence.recommendation import IntelligenceRecommendation
from app.intelligence.risk_prediction import PredictionResult, PredictionType
from tests.phase26_helpers import observations
from app.intelligence.pattern_intelligence import PatternIntelligence


@pytest.mark.parametrize("index", list(range(30)))
def test_evidence_graph_matrix_is_read_only(index, tmp_path):
    rows = observations(tmp_path / f"graph-{index}.db")
    patterns = PatternIntelligence().detect("demo", rows)
    predictions = [PredictionResult(f"pred-{index}", "demo", PredictionType.REGRESSION_RISK, "review evidence", 0.6, [rows[0].id], [rows[0].id], "medium")]
    recommendations = [IntelligenceRecommendation(f"rec-{index}", "demo", f"pred-{index}", "review", "because", [rows[0].id], 0.6, "medium")]
    graph = IntelligenceEvidenceGraph().build("demo", observations=rows, patterns=patterns, predictions=predictions, recommendations=recommendations)
    assert graph.project_id == "demo" and graph.as_dict()["readOnly"] is True
    assert all(node.project_id == "demo" for node in graph.nodes)
    assert all(edge.project_id == "demo" for edge in graph.edges)
    assert all(edge.relation != EvidenceRelation.RESULTED_IN.value for edge in graph.edges if not any(node.node_type == "OUTCOME" for node in graph.nodes))


def test_graph_contains_observation_support_edges(tmp_path):
    rows = observations(tmp_path / "edges.db")
    prediction = PredictionResult("pred", "demo", PredictionType.TEST_FAILURE_RISK, "risk", 0.7, [rows[0].id], [rows[0].id], "high")
    graph = IntelligenceEvidenceGraph().build("demo", observations=rows, predictions=[prediction])
    assert any(edge.relation == EvidenceRelation.SUPPORTS.value and edge.target_id == "pred" for edge in graph.edges)


def test_graph_does_not_include_other_project_records(tmp_path):
    rows = observations(tmp_path / "isolation.db")
    other = observations(tmp_path / "other.db", project="other")
    graph = IntelligenceEvidenceGraph().build("demo", observations=[*rows, *other])
    other_ids = {item.id for item in other}
    assert not other_ids.intersection({node.node_id for node in graph.nodes})


def test_graph_deduplicates_edges(tmp_path):
    rows = observations(tmp_path / "dedupe.db")
    prediction = PredictionResult("pred", "demo", PredictionType.TEST_FAILURE_RISK, "risk", 0.7, [rows[0].id, rows[0].id], [rows[0].id], "high")
    graph = IntelligenceEvidenceGraph().build("demo", observations=rows, predictions=[prediction])
    keys = {(edge.source_id, edge.target_id, edge.relation) for edge in graph.edges}
    assert len(keys) == len(graph.edges)


def test_graph_build_does_not_mutate_inputs(tmp_path):
    rows = observations(tmp_path / "immutable.db")
    before = [item.as_dict() for item in rows]
    IntelligenceEvidenceGraph().build("demo", observations=rows)
    assert before == [item.as_dict() for item in rows]
