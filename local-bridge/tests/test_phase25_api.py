from __future__ import annotations

import pytest


@pytest.mark.parametrize("path,key", [
    ("/intelligence/observations", "observations"),
    ("/intelligence/patterns", "patterns"),
    ("/intelligence/predictions", "predictions"),
    ("/intelligence/recommendations", "recommendations"),
    ("/intelligence/decisions", "decisions"),
    ("/intelligence/outcomes", "outcomes"),
    ("/intelligence/knowledge", "knowledge"),
    ("/intelligence/evidence", "evidence"),
])
def test_phase25_get_apis_are_project_scoped_read_only(bridge, path, key):
    response = bridge.client.get(path, params={"project": "demo"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["project"] == "demo" and payload["readOnly"] is True and key in payload


def test_pattern_and_prediction_analysis_are_pending(bridge):
    pattern = bridge.client.post("/intelligence/patterns/analyze", json={"project_id": "demo"})
    prediction = bridge.client.post("/intelligence/predictions/analyze", json={"project_id": "demo"})
    assert pattern.status_code == 202 and prediction.status_code == 202
    assert all(item["status"] == "pending" for item in bridge.client.get("/permission/pending").json()["pending"])


def test_phase25_endpoints_do_not_offer_execute_or_approve_controls(bridge):
    openapi = bridge.client.get("/openapi.json").json()
    phase25_paths = [path for path in openapi["paths"] if path.startswith(("/intelligence/observations", "/intelligence/patterns", "/intelligence/predictions", "/intelligence/recommendations", "/intelligence/decisions", "/intelligence/outcomes", "/intelligence/knowledge", "/intelligence/evidence", "/intelligence/quality", "/quality/v11"))]
    assert phase25_paths
    assert all("post" not in openapi["paths"][path] or path.endswith(("/record", "/analyze", "/propose", "/bundle")) for path in phase25_paths)
    assert bridge.client.get("/intelligence/decisions").status_code == 422
