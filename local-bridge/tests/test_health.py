"""Service bootstrap tests."""

from __future__ import annotations

from tests.conftest import Bridge


def test_health_reports_ok(bridge: Bridge) -> None:
    response = bridge.client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "chatgpt-cursor-bridge-local"
    assert body["phase"] == "phase-6-engineering-toolchain"
    assert body["workspaceRoot"] == str(bridge.projects_root)
    assert body["logPath"] == str(bridge.logs_root)
    assert body["memoryRoot"] == str(bridge.memory_root)
    assert body["workflowRoot"] == str(bridge.workflow_root)


def test_openapi_exposes_phase_1_contract(bridge: Bridge) -> None:
    paths = bridge.client.get("/openapi.json").json()["paths"]
    for endpoint in (
        "/health",
        "/workspace/list",
        "/project/tree",
        "/file/read",
        "/file/create",
        "/file/write",
        "/patch/apply",
        "/permission/approve",
        "/memory/read",
        "/memory/append",
        "/memory/decision",
        "/workflow/create",
        "/workflow/list",
        "/workflow/{workflow_id}",
        "/workflow/{workflow_id}/stage/start",
        "/workflow/{workflow_id}/stage/report",
        "/workflow/{workflow_id}/stage/approve",
        "/workflow/{workflow_id}/cancel",
        "/workflow/{workflow_id}/stage/rollback",
        "/git/status",
        "/git/diff",
        "/git/commit",
        "/test/run",
    ):
        assert endpoint in paths


def test_arbitrary_shell_endpoints_are_absent(bridge: Bridge) -> None:
    paths = bridge.client.get("/openapi.json").json()["paths"]
    assert not any("shell" in path or path == "/command/run" for path in paths)
    assert "/git/status" in paths and "/git/diff" in paths
