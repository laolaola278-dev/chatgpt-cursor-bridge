from __future__ import annotations


def test_runtime_read_apis_are_available(bridge):
    status = bridge.client.get("/runtime/status")
    events = bridge.client.get("/runtime/events")
    quality = bridge.client.get("/quality/wf_1234")
    assert status.status_code == 200
    assert events.status_code == 200
    assert quality.status_code == 200
    assert "runtimes" in status.json() and "events" in events.json()


def test_runtime_create_requires_approval_and_does_not_auto_start(bridge):
    pending = bridge.client.post("/runtime/create", json={"agent_id": "ag_1234", "session_id": "ses_1234", "workflow_id": "wf_1234", "stage_id": "stg_1234"})
    assert pending.status_code == 202
    assert bridge.client.get("/runtime/status").json()["runtimes"] == []
    approved = bridge.approve(pending.json()["requestId"])
    assert approved.status_code == 200
    records = bridge.client.get("/runtime/status").json()["runtimes"]
    assert records[0]["state"] == "CREATED"


def test_task_create_and_transition_are_approval_gated(bridge):
    pending = bridge.client.post("/task/create", json={"workflow_id": "wf_1234", "stage_id": "stg_1234", "agent_id": "ag_1234", "context": {"action": "file.write"}})
    assert pending.status_code == 202
    assert bridge.client.get("/task/list").json()["tasks"] == []
    approved = bridge.approve(pending.json()["requestId"])
    assert approved.status_code == 200
    tasks = bridge.client.get("/task/list").json()["tasks"]
    assert len(tasks) == 1 and tasks[0]["status"] == "PENDING"

    transition = bridge.client.post(f"/task/{tasks[0]['id']}/transition", json={"status": "RUNNING"})
    assert transition.status_code == 202
    assert bridge.approve(transition.json()["requestId"]).status_code == 200
    assert bridge.client.get(f"/task/{tasks[0]['id']}").json()["status"] == "RUNNING"


def test_runtime_events_expose_audit_bound_events_after_approval(bridge):
    pending = bridge.client.post("/runtime/create", json={"agent_id": "ag_1234", "session_id": "ses_1234", "workflow_id": "wf_1234", "stage_id": "stg_1234"})
    bridge.approve(pending.json()["requestId"])
    events = bridge.client.get("/runtime/events").json()["events"]
    assert any(event["type"] == "runtime.created" and event["auditId"] for event in events)
