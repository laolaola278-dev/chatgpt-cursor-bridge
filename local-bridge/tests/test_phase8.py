"""Phase 8 persistent approval, context intelligence and session tests."""

from __future__ import annotations

import pytest

from app.audit.logger import AuditLogger
from app.context.intelligence import ContextIndex
from app.security.permissions import ApprovalStore, ApprovalStatus
from app.security.validator import ApprovalError
from tests.conftest import Bridge


def test_approval_recovery_requires_explicit_reconfirmation(tmp_path) -> None:
    db = tmp_path / "approvals.db"
    first = ApprovalStore(db, ttl_seconds=3600)
    request = first.create(
        action="file_write", project="demo", path="README.md", payload={"content": "x"},
        reason="change", preview="preview",
    )
    second = ApprovalStore(db, ttl_seconds=3600)
    audit = AuditLogger(tmp_path / "audit.jsonl")
    recovered = second.recover_pending(audit)
    assert [item.request_id for item in recovered] == [request.request_id]
    assert second.get(request.request_id).status is ApprovalStatus.RECOVERED
    with pytest.raises(ApprovalError):
        second.mark_approved(request.request_id)
    reconfirmed = second.reconfirm(request.request_id, audit)
    assert reconfirmed.status is ApprovalStatus.RECONFIRMED
    assert second.mark_approved(request.request_id).status is ApprovalStatus.APPROVED
    events = audit.read_entries()
    assert {entry["action"] for entry in events} >= {"approval_recovered", "approval_reconfirmed"}


def test_expired_approval_cannot_be_recovered(tmp_path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    store = ApprovalStore(tmp_path / "approvals.db", ttl_seconds=-1)
    request = store.create(
        action="file_write", project="demo", path="README.md", payload={"content": "x"},
        reason="change", preview="preview",
    )
    assert store.expire_due(audit)[0].request_id == request.request_id
    assert store.get(request.request_id).status is ApprovalStatus.EXPIRED
    assert store.recover_pending(audit) == []
    assert any(entry["action"] == "approval_expired" for entry in audit.read_entries())


def test_reject_endpoint_persists_rejected_state(bridge: Bridge) -> None:
    pending = bridge.client.post(
        "/file/write",
        json={"project": "demo", "path": "README.md", "content": "new", "reason": "change"},
    )
    assert pending.status_code == 202
    rejected = bridge.client.post(
        "/permission/reject",
        json={"request_id": pending.json()["requestId"], "reason": "not needed"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert not bridge.client.get("/permission/pending").json()["pending"]


def test_context_index_filters_project_keyword_and_dates(tmp_path) -> None:
    index = ContextIndex(tmp_path / "context_index.db")
    index.replace_project("alpha", [{
        "id": "decision:1", "kind": "decision", "title": "SQLite choice",
        "content": "Use a durable index", "updatedAt": "2026-08-01T00:00:00+00:00",
    }])
    index.replace_project("beta", [{
        "id": "task:1", "kind": "task", "title": "SQLite task",
        "content": "Unrelated project", "updatedAt": "2026-08-02T00:00:00+00:00",
    }])
    results = index.search("sqlite", project="alpha", date_from="2026-08-01")
    assert len(results) == 1
    assert results[0].project == "alpha"
    assert results[0].kind == "decision"
    assert index.path.exists()


def test_context_search_api_is_read_only(bridge: Bridge) -> None:
    first = bridge.client.get("/context/project", params={"project": "demo"})
    assert first.status_code == 200
    response = bridge.client.get("/context/search", params={"q": "demo", "project": "demo"})
    assert response.status_code == 200
    assert "results" in response.json()
    assert bridge.client.post("/context/search", json={}).status_code == 405


def test_session_lifecycle_is_persistent_and_approval_gated(bridge: Bridge) -> None:
    pending = bridge.client.post("/session/create", json={"project": "demo"})
    assert pending.status_code == 202
    session_result = bridge.approve(pending.json()["requestId"])
    assert session_result.status_code == 200
    session = session_result.json()["result"]
    assert session["status"] == "CREATE"
    session_id = session["id"]

    transition = bridge.client.post(
        f"/session/{session_id}/transition",
        json={"status": "ACTIVE", "reason": "start runtime"},
    )
    assert transition.status_code == 202
    assert bridge.client.get(f"/session/{session_id}").json()["status"] == "CREATE"
    active = bridge.approve(transition.json()["requestId"])
    assert active.status_code == 200
    assert active.json()["result"]["status"] == "ACTIVE"

    paused = bridge.client.post(
        f"/session/{session_id}/transition", json={"status": "PAUSED"}
    )
    assert paused.status_code == 202
    assert bridge.approve(paused.json()["requestId"]).json()["result"]["status"] == "PAUSED"

    completed = bridge.client.post(
        f"/session/{session_id}/transition", json={"status": "COMPLETED"}
    )
    assert completed.status_code == 202
    assert bridge.approve(completed.json()["requestId"]).json()["result"]["status"] == "COMPLETED"
    assert bridge.client.get(f"/session/{session_id}").json()["status"] == "COMPLETED"


def test_session_cannot_transition_after_completion(bridge: Bridge) -> None:
    pending = bridge.client.post("/session/create", json={"project": "demo"})
    session = bridge.approve(pending.json()["requestId"]).json()["result"]
    transition = bridge.client.post(
        f"/session/{session['id']}/transition", json={"status": "COMPLETED"}
    )
    bridge.approve(transition.json()["requestId"])
    invalid = bridge.client.post(
        f"/session/{session['id']}/transition", json={"status": "ACTIVE"}
    )
    assert invalid.status_code == 202
    assert bridge.approve(invalid.json()["requestId"]).status_code == 400
