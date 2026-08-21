from __future__ import annotations

import hashlib

import pytest

from app.demo import DEMO_FLOW, CATALOG, DemoScenarioManager
from app.export import ArtifactExporter
from app.replay import EngineeringReplay, ReplayStorage
from app.validation import ValidationManager, ValidationStorage


def test_demo_flow_is_complete():
    assert DEMO_FLOW == ["ISSUE", "AGENT_ANALYSIS", "PROPOSAL", "APPROVAL", "EXECUTION", "VERIFICATION", "REPORT"]


@pytest.mark.parametrize("scenario_id", ["bug_fix_demo", "feature_demo", "recovery_demo"] * 5)
def test_demo_catalog_is_record_only(scenario_id):
    assert scenario_id in CATALOG
    assert CATALOG[scenario_id]["name"]
    assert CATALOG[scenario_id]["issue"]
    assert DemoScenarioManager().catalog()[0]["readOnly"] is True


def test_demo_scenario_creation_is_read_only(tmp_path):
    scenario = DemoScenarioManager().create("Demo", "issue")
    assert scenario.id.startswith("demo_")
    assert scenario.stages == DEMO_FLOW
    assert scenario.as_dict()["readOnly"] is True


def test_replay_build_from_events_is_ordered(tmp_path):
    storage = ReplayStorage(tmp_path / "replay.db")
    events = [
        type("E", (), {"as_dict": lambda self: {"eventType": "approval.completed", "source": "approval", "timestamp": "2026-01-01T00:00:01Z"}})(),
        type("E", (), {"as_dict": lambda self: {"eventType": "execution.finished", "source": "execution", "timestamp": "2026-01-01T00:00:02Z"}})(),
    ]
    replay = EngineeringReplay(storage).build("demo", "Timeline", events=events, audit_entries=[{"action": "execution_started", "timestamp": "2026-01-01T00:00:00Z"}])
    timestamps = [step["timestamp"] for step in replay["steps"]]
    assert timestamps == sorted(timestamps)
    stored = storage.get(replay["id"])
    assert stored is not None
    assert stored["readOnly"] is True
    assert stored["steps"] == replay["steps"]


@pytest.mark.parametrize("kind", ["report", "replay", "scenario"] * 5)
def test_artifact_export_round_trip(tmp_path, kind):
    exporter = ArtifactExporter(tmp_path / "artifacts")
    record = exporter.export(kind, "demo", {"hello": "world"}, "# markdown")
    assert record["id"].startswith("artifact_")
    assert record["readOnly"] is True
    listed = exporter.list("demo")
    assert listed and listed[0]["id"] == record["id"]


def test_artifact_export_is_project_scoped(tmp_path):
    exporter = ArtifactExporter(tmp_path / "artifacts")
    exporter.export("report", "demo", {}, "")
    assert exporter.list("other") == []


def test_demo_api_catalog_read_only(bridge):
    response = bridge.client.get("/demo/catalog")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True
    assert len(response.json()["scenarios"]) == 3


def test_demo_flow_api_read_only(bridge):
    response = bridge.client.get("/demo/flow")
    assert response.status_code == 200
    assert response.json()["flow"] == DEMO_FLOW


def test_demo_scenario_write_requires_approval(bridge):
    pending = bridge.client.post("/demo/scenario", json={"name": "Demo", "issue": "issue"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "demo_scenario_create"


def test_replay_create_requires_approval(bridge):
    pending = bridge.client.post("/replay/create", json={"project": "demo", "title": "Timeline"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "replay_create"


def test_artifact_export_requires_approval(bridge):
    pending = bridge.client.post("/artifacts/export", json={"project": "demo", "kind": "report", "payload": {}, "markdown": "# Report"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "artifact_export"


def test_approved_artifact_export_is_read_only(bridge):
    pending = bridge.client.post("/artifacts/export", json={"project": "demo", "kind": "report", "payload": {}, "markdown": "# Report"})
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    artifacts = bridge.client.get("/artifacts?project=demo").json()["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["readOnly"] is True


def test_approved_replay_persists_timeline(bridge):
    pending = bridge.client.post("/replay/create", json={"project": "demo", "title": "Timeline"})
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    replays = bridge.client.get("/replay/list?project=demo").json()["replays"]
    assert len(replays) == 1
    assert replays[0]["title"] == "Timeline"


def test_demo_flow_does_not_modify_source(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    bridge.client.get("/demo/catalog")
    bridge.client.get("/demo/flow")
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_validation_flow_integration(bridge):
    storage = ValidationStorage(bridge.projects_root.parent / "validation" / "validation.db")
    record = ValidationManager(storage).create("demo", "repo", "python", "fastapi", [{"type": "BUG_FIX", "description": "demo"}])
    run = ValidationManager(storage).record_run(storage.scenarios(record.id)[0].id, workflow_id="wf_demo", result="COMPLETED")
    assert run.result == "COMPLETED"
