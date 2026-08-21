"""Test runner unit and API tests."""

from __future__ import annotations

import subprocess

import pytest

from app.config import get_settings
from app.test_runner.policy import truncate_output
from app.test_runner.runner import TestRunner
from tests.conftest import Bridge


def test_runner_uses_array_argv_shell_false_and_safe_cwd(bridge: Bridge) -> None:
    captured = {}

    def fake(argv, **kwargs):
        captured.update({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout=b"ok", stderr=b"")

    result = TestRunner(get_settings(), run_function=fake).execute("demo", "pytest")
    assert captured["argv"] == ["pytest"]
    assert captured["shell"] is False
    assert captured["cwd"] == str(bridge.demo)
    assert result.passed is True


def test_runner_captures_failure(bridge: Bridge) -> None:
    def fake(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 2, stdout=b"failed test", stderr=b"trace")

    result = TestRunner(get_settings(), run_function=fake).execute("demo", "pytest")
    assert result.passed is False
    assert result.exit_code == 2
    assert "trace" in result.stderr


def test_runner_handles_timeout(bridge: Bridge) -> None:
    def fake(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"partial")

    result = TestRunner(get_settings(), run_function=fake).execute("demo", "pytest")
    assert result.timed_out is True
    assert result.exit_code is None
    assert "timed out" in result.stderr


def test_output_is_limited(bridge: Bridge) -> None:
    def fake(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout=b"x" * 10000, stderr=b"y" * 10000)

    settings = get_settings()
    result = TestRunner(settings, run_function=fake).execute("demo", "pytest")
    total = len(result.stdout.encode()) + len(result.stderr.encode())
    assert total <= settings.test_max_output_bytes + 100
    assert result.output_truncated is True


def test_truncate_output_preserves_small_output() -> None:
    assert truncate_output(b"hello", 20) == ("hello", False)


def test_runner_rejects_workspace_escape(bridge: Bridge) -> None:
    with pytest.raises(Exception):
        TestRunner(get_settings()).preview("../demo", "pytest")


def _create_testing_stage(bridge: Bridge) -> tuple[str, str]:
    wf = bridge.client.post(
        "/workflow/create", json={"project": "demo", "name": "Test flow"}
    ).json()
    # Directly use manager storage to create a TESTING-compatible workflow state.
    from app.audit.logger import get_audit_logger
    from app.security.permissions import get_approval_store
    from app.workflow.manager import WorkflowManager
    from app.workflow.models import WorkflowStatus
    from app.workflow.storage import WorkflowStorage

    settings = get_settings()
    storage = WorkflowStorage(settings.workflow_root)
    state = storage.load(wf["id"])
    state.status = WorkflowStatus.IMPLEMENTING
    storage.save(state)
    manager = WorkflowManager(
        settings=settings, storage=storage, approvals=get_approval_store(), audit=get_audit_logger()
    )
    stage = manager.start_stage(wf["id"], "TESTING")
    return wf["id"], stage.id


def test_test_api_only_stages_before_approval(bridge: Bridge) -> None:
    workflow_id, stage_id = _create_testing_stage(bridge)
    response = bridge.client.post(
        "/test/run",
        json={
            "project": "demo", "workflow_id": workflow_id, "stage_id": stage_id,
            "command": "pytest", "reason": "verify",
        },
    )
    assert response.status_code == 202
    assert response.json()["requireApproval"] is True
    detail = bridge.client.get(f"/workflow/{workflow_id}").json()
    assert detail["stages"][-1]["report"] is None


def test_test_api_rejects_command_injection_before_approval(bridge: Bridge) -> None:
    workflow_id, stage_id = _create_testing_stage(bridge)
    response = bridge.client.post(
        "/test/run",
        json={"project": "demo", "workflow_id": workflow_id, "stage_id": stage_id, "command": "pytest; whoami"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "command_policy_violation"


def test_test_api_requires_testing_stage(bridge: Bridge) -> None:
    wf = bridge.client.post("/workflow/create", json={"project": "demo", "name": "x"}).json()
    stage = bridge.client.post(
        f"/workflow/{wf['id']}/stage/start", json={"stage_type": "REQUIREMENT"}
    ).json()
    response = bridge.client.post(
        "/test/run",
        json={"project": "demo", "workflow_id": wf["id"], "stage_id": stage["id"], "command": "pytest"},
    )
    assert response.status_code == 400


def test_test_preview_exposes_fixed_limits(bridge: Bridge) -> None:
    preview = TestRunner(get_settings()).preview("demo", "npm test")
    assert preview["argv"] == ["npm", "test", "--"]
    assert preview["timeoutSeconds"] == 5
    assert preview["maxOutputBytes"] == 4096
