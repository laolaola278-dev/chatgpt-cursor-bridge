from __future__ import annotations

import inspect

from app.demo.manager import DemoScenarioManager
from app.export import ArtifactExporter
from app.replay import EngineeringReplay


def test_demo_manager_has_no_execute():
    source = inspect.getsource(DemoScenarioManager)
    assert "execute" not in source
    assert "subprocess" not in source
    assert "shell" not in source.lower()


def test_replay_has_no_execution_path():
    source = inspect.getsource(EngineeringReplay)
    assert "execute" not in source
    assert "approve" not in source


def test_artifact_exporter_has_no_permission_mutation():
    source = inspect.getsource(ArtifactExporter)
    assert "execute" not in source
    assert "subprocess" not in source
    assert "permission" in source  # audit metadata only
    assert "mark_approved" not in source
    assert "approvals.create" not in source


def test_demo_catalog_is_static_and_read_only(bridge):
    first = bridge.client.get("/demo/catalog").json()
    second = bridge.client.get("/demo/catalog").json()
    assert first == second
    assert first["readOnly"] is True


def test_replay_list_is_read_only(bridge):
    response = bridge.client.get("/replay/list?project=demo")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_artifacts_list_is_read_only(bridge):
    response = bridge.client.get("/artifacts")
    assert response.status_code == 200
    assert response.json()["readOnly"] is True


def test_approval_cannot_be_auto_granted_by_demo(bridge):
    pending = bridge.client.post("/demo/scenario", json={"name": "x", "issue": "y"})
    assert pending.json()["status"] == "pending"
    assert bridge.client.get("/permission/pending").json()["pending"]
