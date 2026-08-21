"""Project memory system tests (Phase 3)."""

from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import Bridge

DOCS = ["project.md", "architecture.md", "decisions.md", "tasks.md", "changelog.md"]


def init_memory(bridge: Bridge, project: str = "demo") -> dict:
    pending, executed = bridge.submit_and_approve("/memory/init", {"project": project})
    assert pending.status_code == 202
    assert executed is not None and executed.status_code == 200
    return executed.json()


# --- 1. creating project memory --------------------------------------


def test_memory_init_requires_approval(bridge: Bridge) -> None:
    pending = bridge.client.post("/memory/init", json={"project": "demo"})
    assert pending.status_code == 202

    body = pending.json()
    assert body["allowed"] is False
    assert body["requireApproval"] is True
    assert body["permissionLevel"] == "LEVEL_1"
    # Nothing on disk before approval.
    assert not bridge.memory_dir("demo").joinpath("project.md").exists()


def test_memory_init_creates_all_documents(bridge: Bridge) -> None:
    result = init_memory(bridge)["result"]
    assert sorted(result["created"]) == sorted(DOCS)

    memory_dir = bridge.memory_dir("demo")
    for name in DOCS:
        assert memory_dir.joinpath(name).is_file()
    assert memory_dir.joinpath("memory.db").is_file()


def test_memory_init_is_idempotent(bridge: Bridge) -> None:
    init_memory(bridge)
    bridge.client.post(
        "/memory/append",
        json={"project": "demo", "document": "tasks.md", "content": "keep me"},
    )
    before = bridge.memory_dir("demo").joinpath("project.md").read_text(encoding="utf-8")

    second = init_memory(bridge)["result"]
    assert second["created"] == []
    after = bridge.memory_dir("demo").joinpath("project.md").read_text(encoding="utf-8")
    assert after == before


def test_memory_documents_are_human_readable_markdown(bridge: Bridge) -> None:
    init_memory(bridge)
    content = bridge.memory_dir("demo").joinpath("architecture.md").read_text(encoding="utf-8")
    assert content.startswith("# Architecture")
    assert "_Created:" in content


# --- 2. reading memory -----------------------------------------------


def test_memory_read_returns_content(bridge: Bridge) -> None:
    init_memory(bridge)
    response = bridge.client.get("/memory/read", params={"project": "demo", "document": "project.md"})
    assert response.status_code == 200

    body = response.json()
    assert body["project"] == "demo"
    assert body["document"] == "project.md"
    assert body["size"] > 0
    assert "# Project" in body["content"]


def test_memory_read_accepts_name_without_extension(bridge: Bridge) -> None:
    init_memory(bridge)
    response = bridge.client.get("/memory/read", params={"project": "demo", "document": "tasks"})
    assert response.status_code == 200
    assert response.json()["document"] == "tasks.md"


def test_memory_read_is_level_0_and_needs_no_approval(bridge: Bridge) -> None:
    init_memory(bridge)
    bridge.client.get("/memory/read", params={"project": "demo", "document": "tasks.md"})
    entry = next(
        item for item in reversed(bridge.audit_entries()) if item["action"] == "memory_read"
    )
    assert entry["permission"] == "LEVEL_0"
    assert entry["approved"] is True


def test_memory_read_unknown_document_is_rejected(bridge: Bridge) -> None:
    init_memory(bridge)
    response = bridge.client.get(
        "/memory/read", params={"project": "demo", "document": "secrets.md"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "validation_failed"


def test_memory_read_before_init_returns_404(bridge: Bridge) -> None:
    response = bridge.client.get(
        "/memory/read", params={"project": "demo", "document": "project.md"}
    )
    assert response.status_code == 404


def test_memory_list_and_status(bridge: Bridge) -> None:
    init_memory(bridge)
    listed = bridge.client.get("/memory/list").json()["projects"]
    assert listed[0]["project"] == "demo"
    assert sorted(listed[0]["documents"]) == sorted(DOCS)

    status = bridge.client.get("/memory/status", params={"project": "demo"}).json()
    assert status["project"] == "demo"
    assert len(status["documents"]) == len(DOCS)


# --- 3. appending memory ---------------------------------------------


def test_memory_append_requires_approval_and_never_overwrites(bridge: Bridge) -> None:
    init_memory(bridge)
    original = bridge.memory_dir("demo").joinpath("tasks.md").read_text(encoding="utf-8")

    pending = bridge.client.post(
        "/memory/append",
        json={"project": "demo", "document": "tasks.md", "content": "- [ ] build memory"},
    )
    assert pending.status_code == 202
    assert pending.json()["permissionLevel"] == "LEVEL_1"
    # Not written yet.
    assert bridge.memory_dir("demo").joinpath("tasks.md").read_text(encoding="utf-8") == original

    approved = bridge.approve(pending.json()["requestId"])
    assert approved.status_code == 200

    after = bridge.memory_dir("demo").joinpath("tasks.md").read_text(encoding="utf-8")
    assert after.startswith(original)
    assert "- [ ] build memory" in after


def test_memory_append_is_cumulative(bridge: Bridge) -> None:
    init_memory(bridge)
    for text in ("first entry", "second entry", "third entry"):
        bridge.submit_and_approve(
            "/memory/append", {"project": "demo", "document": "changelog.md", "content": text}
        )

    content = bridge.memory_dir("demo").joinpath("changelog.md").read_text(encoding="utf-8")
    assert content.index("first entry") < content.index("second entry") < content.index("third entry")
    assert content.count("_Entry:") == 3


def test_memory_append_auto_initialises_documents(bridge: Bridge) -> None:
    _, executed = bridge.submit_and_approve(
        "/memory/append", {"project": "demo", "document": "project.md", "content": "goal: bridge"}
    )
    assert executed is not None and executed.status_code == 200
    assert bridge.memory_dir("demo").joinpath("memory.db").is_file()


def test_memory_append_rejects_empty_and_oversized_content(bridge: Bridge) -> None:
    init_memory(bridge)
    empty = bridge.client.post(
        "/memory/append", json={"project": "demo", "document": "tasks.md", "content": "   "}
    )
    assert empty.status_code == 400

    huge = bridge.client.post(
        "/memory/append",
        json={"project": "demo", "document": "tasks.md", "content": "x" * (32 * 1024)},
    )
    assert huge.status_code == 413


def test_memory_append_rejects_control_characters(bridge: Bridge) -> None:
    init_memory(bridge)
    response = bridge.client.post(
        "/memory/append",
        json={"project": "demo", "document": "tasks.md", "content": "bad\x07payload"},
    )
    assert response.status_code == 400


# --- 4. ADR writing ---------------------------------------------------


ADR_BODY = {
    "project": "demo",
    "title": "Use FastAPI for the bridge",
    "context": "We need a typed local HTTP service.",
    "decision": "Adopt FastAPI with Pydantic models.",
    "consequence": "Automatic OpenAPI docs; Python runtime required.",
}


def test_memory_decision_writes_structured_adr(bridge: Bridge) -> None:
    init_memory(bridge)
    pending, executed = bridge.submit_and_approve("/memory/decision", ADR_BODY)
    assert pending.status_code == 202
    assert executed is not None and executed.status_code == 200

    result = executed.json()["result"]
    assert result["id"] == "ADR-001"

    content = bridge.memory_dir("demo").joinpath("decisions.md").read_text(encoding="utf-8")
    assert "## ADR-001" in content
    assert "Title: Use FastAPI for the bridge" in content
    assert "Context: We need a typed local HTTP service." in content
    assert "Decision: Adopt FastAPI with Pydantic models." in content
    assert "Consequence: Automatic OpenAPI docs; Python runtime required." in content
    assert "Created:" in content


def test_memory_decision_increments_adr_ids(bridge: Bridge) -> None:
    init_memory(bridge)
    ids = []
    for index in range(3):
        _, executed = bridge.submit_and_approve(
            "/memory/decision", {**ADR_BODY, "title": f"Decision {index}"}
        )
        assert executed is not None
        ids.append(executed.json()["result"]["id"])
    assert ids == ["ADR-001", "ADR-002", "ADR-003"]


@pytest.mark.parametrize("missing", ["title", "context", "decision", "consequence"])
def test_memory_decision_requires_all_fields(bridge: Bridge, missing: str) -> None:
    init_memory(bridge)
    body = {**ADR_BODY, missing: "   "}
    response = bridge.client.post("/memory/decision", json=body)
    assert response.status_code in (400, 422)


# --- 5. permission denial --------------------------------------------


def test_memory_writes_are_level_1_and_reads_level_0(bridge: Bridge) -> None:
    from app.security.permissions import PermissionLevel, evaluate

    assert evaluate("memory_read").permission_level is PermissionLevel.LEVEL_0
    assert evaluate("memory_read").allowed is True

    for action in ("memory_append", "memory_decision", "memory_init"):
        decision = evaluate(action)
        assert decision.allowed is False
        assert decision.require_approval is True
        assert decision.permission_level is PermissionLevel.LEVEL_1


def test_unapproved_memory_writes_leave_disk_untouched(bridge: Bridge) -> None:
    init_memory(bridge)
    before = bridge.memory_dir("demo").joinpath("decisions.md").read_text(encoding="utf-8")

    bridge.client.post("/memory/decision", json=ADR_BODY)
    bridge.client.post(
        "/memory/append", json={"project": "demo", "document": "tasks.md", "content": "nope"}
    )

    assert bridge.memory_dir("demo").joinpath("decisions.md").read_text(encoding="utf-8") == before
    assert "nope" not in bridge.memory_dir("demo").joinpath("tasks.md").read_text(encoding="utf-8")


def test_memory_double_approval_is_rejected(bridge: Bridge) -> None:
    init_memory(bridge)
    pending = bridge.client.post(
        "/memory/append",
        json={"project": "demo", "document": "tasks.md", "content": "only once"},
    ).json()

    assert bridge.approve(pending["requestId"]).status_code == 200
    assert bridge.approve(pending["requestId"]).status_code == 400

    content = bridge.memory_dir("demo").joinpath("tasks.md").read_text(encoding="utf-8")
    assert content.count("only once") == 1


# --- 6. path isolation ------------------------------------------------


@pytest.mark.parametrize(
    "document",
    ["../beta/project.md", "../../secret.txt", "/etc/passwd", "sub/dir/project.md", "..\\beta\\a.md"],
)
def test_memory_path_traversal_is_rejected(bridge: Bridge, document: str) -> None:
    init_memory(bridge)
    response = bridge.client.get(
        "/memory/read", params={"project": "demo", "document": document}
    )
    assert response.status_code in (400, 403)


def test_project_a_cannot_read_project_b_memory(bridge: Bridge) -> None:
    init_memory(bridge, "alpha")
    init_memory(bridge, "beta")

    bridge.submit_and_approve(
        "/memory/append",
        {"project": "beta", "document": "project.md", "content": "BETA_SECRET_VALUE"},
    )

    alpha = bridge.client.get(
        "/memory/read", params={"project": "alpha", "document": "project.md"}
    ).json()
    assert "BETA_SECRET_VALUE" not in alpha["content"]

    escape = bridge.client.get(
        "/memory/read", params={"project": "alpha", "document": "../beta/project.md"}
    )
    assert escape.status_code in (400, 403)


def test_invalid_project_name_is_rejected(bridge: Bridge) -> None:
    response = bridge.client.get(
        "/memory/read", params={"project": "../evil", "document": "project.md"}
    )
    assert response.status_code == 403
    assert response.json()["error"] == "sandbox_violation"


def test_memory_is_separate_from_project_files(bridge: Bridge) -> None:
    """Memory lives under MEMORY_ROOT, not inside the code project directory."""
    init_memory(bridge)
    assert not bridge.demo.joinpath("project.md").exists()
    assert bridge.memory_dir("demo").joinpath("project.md").exists()

    # The project file API cannot reach the memory directory.
    response = bridge.client.get(
        "/file/read", params={"project": "demo", "path": "../../memory/demo/project.md"}
    )
    assert response.status_code in (403, 404)


def test_memory_symlink_escape_is_rejected(bridge: Bridge, outside_secret) -> None:
    init_memory(bridge)
    link = bridge.memory_dir("demo") / "tasks.md"
    link.unlink()
    link.symlink_to(outside_secret)

    response = bridge.client.get(
        "/memory/read", params={"project": "demo", "document": "tasks.md"}
    )
    assert response.status_code == 403


# --- 7. audit logging -------------------------------------------------


def test_memory_operations_are_audited(bridge: Bridge) -> None:
    init_memory(bridge)
    bridge.submit_and_approve(
        "/memory/append", {"project": "demo", "document": "tasks.md", "content": "task one"}
    )
    bridge.submit_and_approve("/memory/decision", ADR_BODY)
    bridge.client.get("/memory/read", params={"project": "demo", "document": "tasks.md"})

    entries = bridge.audit_entries()
    by_action: dict[str, list[dict]] = {}
    for entry in entries:
        by_action.setdefault(entry["action"], []).append(entry)

    assert {"memory_init", "memory_append", "memory_decision", "memory_read"} <= by_action.keys()

    for action in ("memory_init", "memory_append", "memory_decision"):
        results = [item["result"] for item in by_action[action]]
        assert "pending_approval" in results
        assert "success" in results
        assert all(item["permission"] == "LEVEL_1" for item in by_action[action])

    assert all(item["permission"] == "LEVEL_0" for item in by_action["memory_read"])
    assert all("timestamp" in item and "path" in item for item in entries)

    adr_entry = next(
        item
        for item in by_action["memory_decision"]
        if item["result"] == "success"
    )
    assert "ADR-001" in adr_entry["detail"]


def test_rejected_memory_reads_are_audited(bridge: Bridge) -> None:
    init_memory(bridge)
    bridge.client.get("/memory/read", params={"project": "demo", "document": "../beta/x.md"})
    rejected = [
        item
        for item in bridge.audit_entries()
        if item["action"] == "memory_read" and item["result"] == "rejected"
    ]
    assert rejected


# --- 8. SQLite index --------------------------------------------------


def test_sqlite_index_is_created_with_expected_schema(bridge: Bridge) -> None:
    init_memory(bridge)
    db_path = bridge.memory_dir("demo") / "memory.db"
    assert db_path.is_file()

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"documents", "decisions"} <= tables

        doc_cols = [row[1] for row in connection.execute("PRAGMA table_info(documents)")]
        assert doc_cols == ["id", "project", "type", "path", "created_at", "updated_at"]

        dec_cols = [row[1] for row in connection.execute("PRAGMA table_info(decisions)")]
        assert dec_cols == ["id", "title", "created_at"]
    finally:
        connection.close()


def test_sqlite_index_never_stores_full_text(bridge: Bridge) -> None:
    init_memory(bridge)
    marker = "UNIQUE_MEMORY_BODY_MARKER_42"
    bridge.submit_and_approve(
        "/memory/append", {"project": "demo", "document": "project.md", "content": marker}
    )
    bridge.submit_and_approve(
        "/memory/decision",
        {**ADR_BODY, "context": marker, "decision": marker, "consequence": marker},
    )

    db_bytes = (bridge.memory_dir("demo") / "memory.db").read_bytes()
    assert marker.encode("utf-8") not in db_bytes

    # The markdown files DO contain the text.
    assert marker in bridge.memory_dir("demo").joinpath("project.md").read_text(encoding="utf-8")


def test_sqlite_index_tracks_documents_and_decisions(bridge: Bridge) -> None:
    init_memory(bridge)
    bridge.submit_and_approve("/memory/decision", ADR_BODY)

    status = bridge.client.get("/memory/status", params={"project": "demo"}).json()

    types = {doc["type"] for doc in status["documents"]}
    assert types == set(DOCS)
    for doc in status["documents"]:
        assert doc["id"] == f"demo:{doc['type']}"
        assert doc["project"] == "demo"
        assert doc["createdAt"] and doc["updatedAt"]

    assert len(status["decisions"]) == 1
    assert status["decisions"][0]["id"] == "ADR-001"
    assert status["decisions"][0]["title"] == ADR_BODY["title"]


def test_sqlite_index_updates_timestamp_on_append(bridge: Bridge) -> None:
    init_memory(bridge)
    before = bridge.client.get("/memory/status", params={"project": "demo"}).json()
    tasks_before = next(doc for doc in before["documents"] if doc["type"] == "tasks.md")

    bridge.submit_and_approve(
        "/memory/append", {"project": "demo", "document": "tasks.md", "content": "new task"}
    )

    after = bridge.client.get("/memory/status", params={"project": "demo"}).json()
    tasks_after = next(doc for doc in after["documents"] if doc["type"] == "tasks.md")

    assert tasks_after["createdAt"] == tasks_before["createdAt"]
    assert tasks_after["updatedAt"] >= tasks_before["updatedAt"]


def test_index_is_per_project(bridge: Bridge) -> None:
    init_memory(bridge, "alpha")
    init_memory(bridge, "beta")

    assert (bridge.memory_dir("alpha") / "memory.db").is_file()
    assert (bridge.memory_dir("beta") / "memory.db").is_file()

    alpha = bridge.client.get("/memory/status", params={"project": "alpha"}).json()
    assert all(doc["project"] == "alpha" for doc in alpha["documents"])
