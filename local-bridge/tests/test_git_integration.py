"""Git integration tests (7+)."""

from __future__ import annotations

import subprocess

from app.config import get_settings
from app.git.manager import GitManager
from tests.conftest import Bridge


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def init_repo(bridge: Bridge) -> None:
    git(bridge.demo, "init", "-b", "main")
    git(bridge.demo, "config", "user.email", "test@example.com")
    git(bridge.demo, "config", "user.name", "CCB Test")
    git(bridge.demo, "add", "--all")
    git(bridge.demo, "commit", "-m", "initial")


def active_stage(bridge: Bridge) -> tuple[str, str]:
    wf = bridge.client.post("/workflow/create", json={"project": "demo", "name": "Git flow"}).json()
    stage = bridge.client.post(
        f"/workflow/{wf['id']}/stage/start", json={"stage_type": "REQUIREMENT"}
    ).json()
    return wf["id"], stage["id"]


def test_git_status_reports_branch_modified_untracked(bridge: Bridge) -> None:
    init_repo(bridge)
    (bridge.demo / "README.md").write_text("changed\n", encoding="utf-8")
    (bridge.demo / "new.txt").write_text("new", encoding="utf-8")
    body = bridge.client.get("/git/status", params={"project": "demo"}).json()
    assert body["branch"] == "main"
    assert "README.md" in body["modifiedFiles"]
    assert "new.txt" in body["untrackedFiles"]
    assert body["clean"] is False


def test_git_status_clean_repo(bridge: Bridge) -> None:
    init_repo(bridge)
    assert bridge.client.get("/git/status", params={"project": "demo"}).json()["clean"] is True


def test_git_diff_is_read_only(bridge: Bridge) -> None:
    init_repo(bridge)
    (bridge.demo / "README.md").write_text("changed\n", encoding="utf-8")
    response = bridge.client.get("/git/diff", params={"project": "demo"})
    assert response.status_code == 200
    assert "README.md" in response.json()["diff"]
    assert git(bridge.demo, "status", "--porcelain").stdout


def test_git_rejects_non_repository(bridge: Bridge) -> None:
    response = bridge.client.get("/git/status", params={"project": "demo"})
    assert response.status_code == 400


def test_git_commit_requires_approval_and_binding(bridge: Bridge) -> None:
    init_repo(bridge)
    workflow_id, stage_id = active_stage(bridge)
    (bridge.demo / "README.md").write_text("changed\n", encoding="utf-8")
    before = git(bridge.demo, "rev-parse", "HEAD").stdout.strip()
    response = bridge.client.post(
        "/git/commit",
        json={
            "project": "demo", "message": "feat: change readme",
            "workflow_id": workflow_id, "stage_id": stage_id,
        },
    )
    assert response.status_code == 202
    assert response.json()["workflowId"] == workflow_id
    assert git(bridge.demo, "rev-parse", "HEAD").stdout.strip() == before

    approved = bridge.approve(response.json()["requestId"])
    assert approved.status_code == 200
    assert approved.json()["result"]["message"] == "feat: change readme"
    assert git(bridge.demo, "rev-parse", "HEAD").stdout.strip() != before


def test_git_commit_rejects_clean_tree(bridge: Bridge) -> None:
    init_repo(bridge)
    workflow_id, stage_id = active_stage(bridge)
    response = bridge.client.post(
        "/git/commit",
        json={"project": "demo", "message": "nothing", "workflow_id": workflow_id, "stage_id": stage_id},
    )
    assert response.status_code == 409


def test_git_commit_rejects_invalid_workflow_binding(bridge: Bridge) -> None:
    init_repo(bridge)
    (bridge.demo / "README.md").write_text("changed", encoding="utf-8")
    response = bridge.client.post(
        "/git/commit",
        json={
            "project": "demo", "message": "change",
            "workflow_id": "wf_aaaaaaaaaaaaaaaa", "stage_id": "stg_bbbbbbbbbbbbbbbb",
        },
    )
    assert response.status_code == 404


def test_git_subprocess_never_uses_shell(bridge: Bridge) -> None:
    calls = []

    def fake(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[1:3] == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(argv, 0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    GitManager(get_settings(), run_function=fake).status("demo")
    assert calls
    assert all(call[1]["shell"] is False for call in calls)
    assert all(isinstance(call[0], list) for call in calls)


def test_git_operations_are_audited(bridge: Bridge) -> None:
    init_repo(bridge)
    bridge.client.get("/git/status", params={"project": "demo"})
    bridge.client.get("/git/diff", params={"project": "demo"})
    actions = [entry["action"] for entry in bridge.audit_entries()]
    assert "git_status" in actions and "git_diff" in actions
