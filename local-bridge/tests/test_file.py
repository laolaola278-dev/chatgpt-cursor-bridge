"""File read/create/write, approval flow and patch application tests."""

from __future__ import annotations

from tests.conftest import Bridge


def test_read_file_returns_content(bridge: Bridge) -> None:
    response = bridge.client.get("/file/read", params={"project": "demo", "path": "src/main.py"})
    assert response.status_code == 200

    body = response.json()
    assert body["file"] == "src/main.py"
    assert body["content"] == "print('hello')\nprint('world')\n"
    assert body["size"] > 0


def test_read_missing_file_returns_404(bridge: Bridge) -> None:
    response = bridge.client.get("/file/read", params={"project": "demo", "path": "src/nope.py"})
    assert response.status_code == 404


def test_create_requires_approval_then_writes(bridge: Bridge) -> None:
    pending = bridge.client.post(
        "/file/create",
        json={
            "project": "demo",
            "path": "src/new_module.py",
            "content": "VALUE = 1\n",
            "reason": "add module",
        },
    )
    assert pending.status_code == 202
    request_id = pending.json()["requestId"]
    assert not (bridge.demo / "src" / "new_module.py").exists()

    listed = bridge.client.get("/permission/pending").json()["pending"]
    assert [item["requestId"] for item in listed] == [request_id]

    approved = bridge.client.post("/permission/approve", json={"request_id": request_id})
    assert approved.status_code == 200

    body = approved.json()
    assert body["allowed"] is True
    assert body["action"] == "file_create"
    assert (bridge.demo / "src" / "new_module.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_create_existing_file_conflicts(bridge: Bridge) -> None:
    response = bridge.client.post(
        "/file/create",
        json={"project": "demo", "path": "README.md", "content": "x"},
    )
    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


def test_write_flow_updates_existing_file(bridge: Bridge) -> None:
    pending = bridge.client.post(
        "/file/write",
        json={"project": "demo", "path": "README.md", "content": "# demo updated\n"},
    ).json()
    assert "preview" in pending and pending["preview"]

    bridge.client.post("/permission/approve", json={"request_id": pending["requestId"]})
    assert (bridge.demo / "README.md").read_text(encoding="utf-8") == "# demo updated\n"


def test_write_missing_file_returns_404(bridge: Bridge) -> None:
    response = bridge.client.post(
        "/file/write",
        json={"project": "demo", "path": "src/ghost.py", "content": "x"},
    )
    assert response.status_code == 404


def test_double_approval_is_rejected(bridge: Bridge) -> None:
    pending = bridge.client.post(
        "/file/write",
        json={"project": "demo", "path": "README.md", "content": "# once\n"},
    ).json()
    first = bridge.client.post("/permission/approve", json={"request_id": pending["requestId"]})
    assert first.status_code == 200

    second = bridge.client.post("/permission/approve", json={"request_id": pending["requestId"]})
    assert second.status_code == 400
    assert second.json()["error"] == "approval_error"


def test_unknown_approval_id_returns_404(bridge: Bridge) -> None:
    response = bridge.client.post("/permission/approve", json={"request_id": "req_" + "a" * 16})
    assert response.status_code == 404


def test_malformed_approval_id_returns_400(bridge: Bridge) -> None:
    response = bridge.client.post("/permission/approve", json={"request_id": "not-an-id"})
    assert response.status_code == 400


def test_patch_apply_flow(bridge: Bridge) -> None:
    patch = (
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -1,2 +1,3 @@\n"
        " print('hello')\n"
        "+print('patched')\n"
        " print('world')\n"
    )
    pending = bridge.client.post(
        "/patch/apply",
        json={"project": "demo", "path": "src/main.py", "patch": patch, "reason": "add line"},
    )
    assert pending.status_code == 202
    assert (bridge.demo / "src" / "main.py").read_text(encoding="utf-8") == (
        "print('hello')\nprint('world')\n"
    )

    approved = bridge.client.post(
        "/permission/approve", json={"request_id": pending.json()["requestId"]}
    )
    assert approved.status_code == 200
    assert (bridge.demo / "src" / "main.py").read_text(encoding="utf-8") == (
        "print('hello')\nprint('patched')\nprint('world')\n"
    )


def test_patch_with_bad_context_is_rejected(bridge: Bridge) -> None:
    patch = "@@ -1,1 +1,1 @@\n-print('nope')\n+print('bad')\n"
    response = bridge.client.post(
        "/patch/apply",
        json={"project": "demo", "path": "src/main.py", "patch": patch},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "validation_failed"


def test_patch_without_hunk_is_rejected(bridge: Bridge) -> None:
    response = bridge.client.post(
        "/patch/apply",
        json={"project": "demo", "path": "src/main.py", "patch": "just text"},
    )
    assert response.status_code == 400


def test_audit_log_records_pending_and_success(bridge: Bridge) -> None:
    pending = bridge.client.post(
        "/file/create",
        json={"project": "demo", "path": "notes.md", "content": "hi\n"},
    ).json()
    bridge.client.post("/permission/approve", json={"request_id": pending["requestId"]})

    entries = [entry for entry in bridge.audit_entries() if entry["action"] == "file_create"]
    results = [entry["result"] for entry in entries]
    assert "pending_approval" in results
    assert "success" in results
    assert all(entry["permission"] == "LEVEL_1" for entry in entries)
    assert all("timestamp" in entry and "path" in entry for entry in entries)

    api_entries = bridge.client.get("/audit/log").json()["entries"]
    assert len(api_entries) >= len(entries)
