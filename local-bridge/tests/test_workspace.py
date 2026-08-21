"""Workspace scanning and project tree tests."""

from __future__ import annotations

from tests.conftest import Bridge


def test_workspace_list_returns_projects(bridge: Bridge) -> None:
    (bridge.projects_root / "second").mkdir()
    (bridge.projects_root / ".hidden").mkdir()

    response = bridge.client.get("/workspace/list")
    assert response.status_code == 200

    names = [project["name"] for project in response.json()["projects"]]
    assert names == ["demo", "second"]


def test_project_tree_ignores_noise_directories(bridge: Bridge) -> None:
    response = bridge.client.get("/project/tree", params={"project_name": "demo"})
    assert response.status_code == 200

    body = response.json()
    assert body["project"] == "demo"
    top_level = {child["name"] for child in body["tree"]["children"]}
    assert "src" in top_level
    assert "README.md" in top_level
    assert "node_modules" not in top_level
    assert ".git" not in top_level


def test_project_tree_respects_max_depth(bridge: Bridge) -> None:
    deep = bridge.demo / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_text("deep", encoding="utf-8")

    body = bridge.client.get("/project/tree", params={"project_name": "demo"}).json()
    assert body["maxDepth"] == 3

    node = next(child for child in body["tree"]["children"] if child["name"] == "a")
    node = next(child for child in node["children"] if child["name"] == "b")
    node = next(child for child in node["children"] if child["name"] == "c")
    assert node["truncated"] is True
    assert node["children"] == []


def test_project_tree_unknown_project_returns_404(bridge: Bridge) -> None:
    response = bridge.client.get("/project/tree", params={"project_name": "nope"})
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_workspace_operations_are_audited(bridge: Bridge) -> None:
    bridge.client.get("/workspace/list")
    actions = [entry["action"] for entry in bridge.audit_entries()]
    assert "workspace_list" in actions
