from __future__ import annotations


def test_team_create_is_approval_gated(bridge):
    pending = bridge.client.post("/team/create", json={"workflow_id": "wf_1234", "members": ["ag_1234", "ag_5678"], "leader": "ag_1234"})
    assert pending.status_code == 202
    assert bridge.client.get("/team/list").json()["teams"] == []
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    teams = bridge.client.get("/team/list", params={"workflow_id": "wf_1234"}).json()["teams"]
    assert len(teams) == 1 and teams[0]["status"] == "CREATED"
    assert bridge.client.get(f"/team/{teams[0]['id']}").json()["leader"] == "ag_1234"


def test_team_create_rejects_non_agent_ids(bridge):
    response = bridge.client.post("/team/create", json={"workflow_id": "wf_1234", "members": ["planner", "ag_5678"], "leader": "planner"})
    assert response.status_code == 400


def test_phase11_read_only_endpoints_are_available(bridge):
    assert bridge.client.get("/collaboration/events").status_code == 200
    assert bridge.client.get("/task/task_missing/dependencies").status_code in {200, 404}
    assert bridge.client.get("/agent/ag_1234/metrics").status_code == 200


def test_phase11_quality_report_contains_consensus_shape(bridge):
    report = bridge.client.get("/quality/wf_1234").json()
    assert "score" in report and "agentConsensus" in report and "blockingIssues" in report


def test_phase11_context_bundle_exposes_read_only_route(bridge):
    result = bridge.client.get("/context/bundle", params={"project": "demo", "agent_role": "REVIEWER"})
    assert result.status_code == 200
    assert result.json()["readOnly"] is True
    assert result.json()["route"] == ["all reports", "quality score"]
