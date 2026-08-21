"""Sandbox, permission and payload-limit tests."""

from __future__ import annotations

import pytest

from app.security.permissions import PermissionLevel, evaluate
from tests.conftest import Bridge


@pytest.mark.parametrize(
    "hostile_path",
    [
        "../../secret.txt",
        "../secret.txt",
        "src/../../../secret.txt",
        "/etc/passwd",
        "..%2f..%2fsecret.txt",
    ],
)
def test_path_traversal_is_rejected(bridge: Bridge, hostile_path: str) -> None:
    response = bridge.client.get("/file/read", params={"project": "demo", "path": hostile_path})
    assert response.status_code in (403, 404)
    if response.status_code == 403:
        assert response.json()["error"] == "sandbox_violation"


def test_project_name_traversal_is_rejected(bridge: Bridge) -> None:
    response = bridge.client.get("/file/read", params={"project": "../", "path": "secret.txt"})
    assert response.status_code == 403
    assert response.json()["error"] == "sandbox_violation"


def test_symlink_escape_is_rejected(bridge: Bridge, outside_secret) -> None:
    link = bridge.demo / "escape.txt"
    link.symlink_to(outside_secret)

    response = bridge.client.get("/file/read", params={"project": "demo", "path": "escape.txt"})
    assert response.status_code == 403
    assert response.json()["error"] == "sandbox_violation"


def test_symlinked_directory_escape_is_rejected(bridge: Bridge, outside_secret) -> None:
    link_dir = bridge.demo / "linked"
    link_dir.symlink_to(outside_secret.parent, target_is_directory=True)

    response = bridge.client.get("/file/read", params={"project": "demo", "path": "linked/secret.txt"})
    assert response.status_code == 403


def test_symlinks_are_not_listed_in_tree(bridge: Bridge, outside_secret) -> None:
    (bridge.demo / "escape.txt").symlink_to(outside_secret)
    body = bridge.client.get("/project/tree", params={"project_name": "demo"}).json()
    assert "escape.txt" not in {child["name"] for child in body["tree"]["children"]}


def test_oversized_read_is_rejected(bridge: Bridge) -> None:
    big = bridge.demo / "big.txt"
    big.write_text("x" * (2 * 1024 * 1024), encoding="utf-8")

    response = bridge.client.get("/file/read", params={"project": "demo", "path": "big.txt"})
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_binary_file_read_is_rejected(bridge: Bridge) -> None:
    (bridge.demo / "blob.bin").write_bytes(b"\xff\xfe\x00\x01binary")
    response = bridge.client.get("/file/read", params={"project": "demo", "path": "blob.bin"})
    assert response.status_code == 400


def test_permission_levels() -> None:
    read = evaluate("file_read")
    assert read.allowed is True
    assert read.require_approval is False
    assert read.permission_level is PermissionLevel.LEVEL_0

    write = evaluate("file_write")
    assert write.allowed is False
    assert write.require_approval is True
    assert write.permission_level is PermissionLevel.LEVEL_1

    delete = evaluate("file_delete")
    assert delete.allowed is False
    assert delete.require_approval is True
    assert delete.permission_level is PermissionLevel.LEVEL_2

    # LEVEL_2 stays gated behind an explicit approval record.
    assert evaluate("file_delete", approved=True).allowed is True
    assert evaluate("file_write", approved=True).allowed is True


def test_write_without_approval_does_not_touch_the_file(bridge: Bridge) -> None:
    original = (bridge.demo / "README.md").read_text(encoding="utf-8")
    response = bridge.client.post(
        "/file/write",
        json={"project": "demo", "path": "README.md", "content": "hacked", "reason": "test"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["allowed"] is False
    assert body["requireApproval"] is True
    assert body["permissionLevel"] == "LEVEL_1"
    assert (bridge.demo / "README.md").read_text(encoding="utf-8") == original


def test_denied_operations_are_audited(bridge: Bridge) -> None:
    bridge.client.get("/file/read", params={"project": "demo", "path": "../../secret.txt"})
    results = [entry["result"] for entry in bridge.audit_entries() if entry["action"] == "file_read"]
    assert "rejected" in results
