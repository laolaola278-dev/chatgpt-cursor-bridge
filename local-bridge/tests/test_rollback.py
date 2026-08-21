"""Enhanced stage rollback tests (6+)."""

from __future__ import annotations

import json

from app.config import get_settings
from app.security.permissions import ApprovalRequest, PermissionLevel
from app.workflow.rollback import RollbackManager
from tests.conftest import Bridge

REPORT = "## Goal\n\ng\n\n## Scope\n\ns\n\n## Constraints\n\nc\n"


def workflow_stage(bridge: Bridge) -> tuple[str, str]:
    wf = bridge.client.post("/workflow/create", json={"project": "demo", "name": "Rollback"}).json()
    stage = bridge.client.post(
        f"/workflow/{wf['id']}/stage/start", json={"stage_type": "REQUIREMENT"}
    ).json()
    return wf["id"], stage["id"]


def apply_bound_write(bridge: Bridge, workflow_id: str, stage_id: str, path: str, content: str) -> str:
    pending = bridge.client.post(
        "/file/write", json={"project": "demo", "path": path, "content": content}
    ).json()
    bridge.client.post(
        f"/workflow/{workflow_id}/stage/attach",
        json={"stage_id": stage_id, "request_id": pending["requestId"]},
    )
    return pending["requestId"]


def approve_stage(bridge: Bridge, workflow_id: str, stage_id: str) -> None:
    bridge.client.post(
        f"/workflow/{workflow_id}/stage/report",
        json={"stage_id": stage_id, "title": "Req", "body": REPORT},
    )
    pending = bridge.client.post(
        f"/workflow/{workflow_id}/stage/approve",
        json={"stage_id": stage_id, "reason": "ready"},
    ).json()
    assert bridge.approve(pending["approval"]["requestId"]).status_code == 200


def test_stage_rollback_restores_modified_file_after_approval(bridge: Bridge) -> None:
    workflow_id, stage_id = workflow_stage(bridge)
    original = (bridge.demo / "README.md").read_text(encoding="utf-8")
    apply_bound_write(bridge, workflow_id, stage_id, "README.md", "changed\n")
    approve_stage(bridge, workflow_id, stage_id)
    assert (bridge.demo / "README.md").read_text() == "changed\n"

    pending = bridge.client.post(
        f"/workflow/{workflow_id}/stage/rollback",
        json={"stage_id": stage_id, "reason": "revert bad stage"},
    )
    assert pending.status_code == 202
    # Preview does not restore.
    assert (bridge.demo / "README.md").read_text() == "changed\n"
    result = bridge.approve(pending.json()["requestId"])
    assert result.status_code == 200
    assert (bridge.demo / "README.md").read_text() == original


def test_rollback_requires_existing_snapshot(bridge: Bridge) -> None:
    workflow_id, stage_id = workflow_stage(bridge)
    response = bridge.client.post(
        f"/workflow/{workflow_id}/stage/rollback",
        json={"stage_id": stage_id, "reason": "nothing"},
    )
    assert response.status_code == 404


def test_rollback_snapshot_stays_under_configured_root(bridge: Bridge) -> None:
    workflow_id, stage_id = workflow_stage(bridge)
    apply_bound_write(bridge, workflow_id, stage_id, "README.md", "changed")
    approve_stage(bridge, workflow_id, stage_id)
    snapshots = list((bridge.rollback_root / workflow_id / stage_id).glob("*.json"))
    assert len(snapshots) == 1
    data = json.loads(snapshots[0].read_text())
    assert data["path"] == "README.md"
    assert data["existed"] is True


def test_rollback_manager_removes_new_file(bridge: Bridge) -> None:
    workflow_id, stage_id = workflow_stage(bridge)
    request = ApprovalRequest(
        request_id="req_aaaaaaaaaaaaaaaa", action="file_create",
        permission_level=PermissionLevel.LEVEL_1, risk="medium", project="demo",
        path="new.txt", payload={"content": "new"}, reason="x", preview="x",
        created_at="now", workflow_id=workflow_id, stage_id=stage_id,
    )
    manager = RollbackManager(get_settings())
    manager.capture(request)
    (bridge.demo / "new.txt").write_text("new")
    manager.restore(workflow_id, stage_id)
    assert not (bridge.demo / "new.txt").exists()


def test_rollback_reverses_multiple_actions_in_reverse_order(bridge: Bridge) -> None:
    workflow_id, stage_id = workflow_stage(bridge)
    manager = RollbackManager(get_settings())
    target = bridge.demo / "README.md"
    original = target.read_text()
    first = ApprovalRequest(
        request_id="req_1111111111111111", action="file_write", permission_level=PermissionLevel.LEVEL_1,
        risk="medium", project="demo", path="README.md", payload={}, reason="", preview="",
        created_at="now", workflow_id=workflow_id, stage_id=stage_id,
    )
    manager.capture(first)
    target.write_text("one")
    second = ApprovalRequest(
        request_id="req_2222222222222222", action="file_write", permission_level=PermissionLevel.LEVEL_1,
        risk="medium", project="demo", path="README.md", payload={}, reason="", preview="",
        created_at="now", workflow_id=workflow_id, stage_id=stage_id,
    )
    manager.capture(second)
    target.write_text("two")
    result = manager.restore(workflow_id, stage_id)
    assert result["count"] == 2
    assert target.read_text() == original


def test_rollback_is_audited(bridge: Bridge) -> None:
    workflow_id, stage_id = workflow_stage(bridge)
    apply_bound_write(bridge, workflow_id, stage_id, "README.md", "changed")
    approve_stage(bridge, workflow_id, stage_id)
    pending = bridge.client.post(
        f"/workflow/{workflow_id}/stage/rollback",
        json={"stage_id": stage_id, "reason": "revert"},
    ).json()
    bridge.approve(pending["requestId"])
    entries = [e for e in bridge.audit_entries() if e["action"] == "workflow_rollback"]
    assert {e["result"] for e in entries} >= {"pending_approval", "success"}
    assert all(workflow_id in e.get("detail", "") or workflow_id in e["path"] for e in entries)
