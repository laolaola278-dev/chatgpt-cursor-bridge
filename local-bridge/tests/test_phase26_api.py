from __future__ import annotations

import pytest


@pytest.mark.parametrize("path,key", [
    ("/intelligence/trends", "trends"),
    ("/intelligence/correlations", "correlations"),
    ("/intelligence/impact", "impact"),
    ("/intelligence/dependencies", "dependencies"),
    ("/intelligence/evaluations", "evaluations"),
    ("/intelligence/evidence/graph", "nodes"),
    ("/intelligence/recommendations/ranking", "ranked"),
    ("/intelligence/evidence", "evidence"),
] * 4)
def test_phase26_get_matrix_is_project_scoped_read_only(bridge, path, key):
    response = bridge.client.get(path, params={"project": "demo"})
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("readOnly") is True and key in payload
    if "project" in payload:
        assert payload["project"] == "demo"


def test_phase26_endpoints_do_not_offer_unsafe_post_paths(bridge):
    openapi = bridge.client.get("/openapi.json").json()
    paths = [path for path in openapi["paths"] if path.startswith("/intelligence/")]
    assert "/intelligence/trends" in paths
    for path in ("/intelligence/trends", "/intelligence/correlations", "/intelligence/impact", "/intelligence/dependencies", "/intelligence/evaluations", "/intelligence/evidence/graph", "/intelligence/recommendations/ranking"):
        assert "post" not in openapi["paths"][path]


def test_phase26_project_isolation(bridge):
    for path, key in (("/intelligence/trends", "trends"), ("/intelligence/correlations", "correlations"), ("/intelligence/dependencies", "dependencies"), ("/intelligence/evaluations", "evaluations")):
        result = bridge.client.get(path, params={"project": "other"})
        assert result.status_code == 200
        assert result.json()[key] == []


def test_phase26_impact_accepts_repeated_read_only_query_parameters(bridge):
    response = bridge.client.get("/intelligence/impact?project=demo&changed_file=src%2Fmain.py&changed_symbol=main")
    assert response.status_code == 200 and response.json()["readOnly"] is True


def test_phase26_correlation_payload_disclaims_causation(bridge):
    response = bridge.client.get("/intelligence/correlations", params={"project": "demo"})
    assert response.status_code == 200
    assert response.json()["causationClaims"] == []
