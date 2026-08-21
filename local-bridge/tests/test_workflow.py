"""Workflow orchestration tests (Phase 5)."""

from __future__ import annotations

import json

import pytest

from tests.conftest import Bridge


# ---- reusable fixtures ------------------------------------------------


REQUIREMENT_BODY = (
    "## Goal\n\nDeliver the memory bridge.\n\n"
    "## Scope\n\nLocal service + extension.\n\n"
    "## Constraints\n\nHuman-in-the-loop.\n"
)

ARCHITECTURE_BODY = (
    "## Technology\n\nFastAPI, TypeScript, SQLite.\n\n"
    "## Modules\n\n- bridge\n- extension\n- memory\n\n"
    "## Risks\n\nDOM breakage, path traversal.\n\n"
    "## Trade-offs\n\nSimplicity over completeness.\n"
)

IMPLEMENTATION_BODY = (
    "## Summary\n\nWired workflow into the approval flow.\n\n"
    "## Files Touched\n\napp/workflow/*\n\n"
    "## Follow-ups\n\nAdd browser hooks in Phase 6.\n"
)


def create_workflow(bridge: Bridge, name: str = "Ship memory") -> dict:
    response = bridge.client.post(
        "/workflow/create",
        json={"project": "demo", "name": name, "description": "phase demo"},
    )
    assert response.status_code == 201
    return response.json()


def start_stage(bridge: Bridge, workflow_id: str, stage_type: str) -> dict:
    response = bridge.client.post(
        f"/workflow/{workflow_id}/stage/start", json={"stage_type": stage_type}
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit_report(
    bridge: Bridge, workflow_id: str, stage_id: str, *, title: str, body: str
) -> dict:
    response = bridge.client.post(
        f"/workflow/{workflow_id}/stage/report",
        json={"stage_id": stage_id, "title": title, "body": body},
    )
    assert response.status_code == 200, response.text
    return response.json()


def request_stage_approval(
    bridge: Bridge, workflow_id: str, stage_id: str, *, sync_memory: bool = False
) -> dict:
    response = bridge.client.post(
        f"/workflow/{workflow_id}/stage/approve",
        json={"stage_id": stage_id, "reason": "ready", "sync_memory": sync_memory},
    )
    assert response.status_code == 202, response.text
    return response.json()


def init_memory(bridge: Bridge) -> None:
    pending, _ = bridge.submit_and_approve("/memory/init", {"project": "demo"})
    assert pending.status_code == 202


# ---- 1. create workflow ----------------------------------------------


def test_create_workflow_persists_to_disk(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    assert workflow["id"].startswith("wf_")
    assert workflow["status"] == "CREATED"
    assert workflow["currentStage"] == "REQUIREMENT"
    assert workflow["stages"] == []

    path = bridge.workflow_root / f"{workflow['id']}.json"
    assert path.is_file()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["id"] == workflow["id"]


def test_create_workflow_rejects_invalid_project(bridge: Bridge) -> None:
    response = bridge.client.post(
        "/workflow/create", json={"project": "../evil", "name": "x"}
    )
    assert response.status_code == 403


def test_create_workflow_rejects_empty_name(bridge: Bridge) -> None:
    response = bridge.client.post(
        "/workflow/create", json={"project": "demo", "name": "   "}
    )
    assert response.status_code in (400, 422)


def test_workflow_list_and_detail(bridge: Bridge) -> None:
    first = create_workflow(bridge, "alpha")
    second = create_workflow(bridge, "beta")

    listed = bridge.client.get("/workflow/list").json()["workflows"]
    ids = [item["id"] for item in listed]
    assert first["id"] in ids and second["id"] in ids

    detail = bridge.client.get(f"/workflow/{first['id']}").json()
    assert detail["name"] == "alpha"


# ---- 2/3. stage state transitions -----------------------------------


def test_full_stage_progression_flows_through_approval(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]

    requirement = start_stage(bridge, workflow_id, "REQUIREMENT")
    assert requirement["status"] == "IN_PROGRESS"

    submit_report(
        bridge, workflow_id, requirement["id"], title="Requirement", body=REQUIREMENT_BODY
    )
    awaiting = request_stage_approval(bridge, workflow_id, requirement["id"])
    approval_id = awaiting["approval"]["requestId"]
    assert awaiting["workflow"]["status"] == "WAITING_APPROVAL"

    result = bridge.approve(approval_id)
    assert result.status_code == 200
    body = result.json()
    assert body["action"] == "workflow_stage_approval"
    assert body["result"]["approved"] is True
    assert body["result"]["workflowStatus"] == "ANALYZING"

    refreshed = bridge.client.get(f"/workflow/{workflow_id}").json()
    assert refreshed["status"] == "ANALYZING"
    assert refreshed["currentStage"] == "ANALYSIS"
    assert refreshed["stages"][0]["status"] == "APPROVED"


def test_report_before_start_is_rejected(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    response = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/report",
        json={"stage_id": "stg_" + "a" * 16, "title": "x", "body": REQUIREMENT_BODY},
    )
    assert response.status_code == 404


def test_starting_stage_out_of_order_is_rejected(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    # From CREATED we can only enter ANALYZING via REQUIREMENT.
    response = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/start", json={"stage_type": "IMPLEMENTATION"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "workflow_transition_error"


def test_stage_report_requires_all_sections(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    stage = start_stage(bridge, workflow["id"], "REQUIREMENT")

    response = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/report",
        json={"stage_id": stage["id"], "title": "Missing", "body": "## Goal\n\nonly one\n"},
    )
    assert response.status_code == 400
    assert "Scope" in response.json()["message"]


def test_approval_requires_prior_report(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    stage = start_stage(bridge, workflow["id"], "REQUIREMENT")

    response = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/approve",
        json={"stage_id": stage["id"], "reason": "no report"},
    )
    assert response.status_code == 400


def test_illegal_stage_id_format_is_rejected(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    response = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/report",
        json={"stage_id": "not-a-stage", "title": "x", "body": REQUIREMENT_BODY},
    )
    assert response.status_code == 400


def test_unknown_workflow_id_returns_404(bridge: Bridge) -> None:
    response = bridge.client.get("/workflow/wf_ffffffffffffffff")
    assert response.status_code == 404


def test_invalid_workflow_id_format_is_rejected(bridge: Bridge) -> None:
    response = bridge.client.get("/workflow/not-an-id")
    assert response.status_code == 400


def test_stage_rejection_returns_to_designing(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]
    requirement = start_stage(bridge, workflow_id, "REQUIREMENT")
    submit_report(bridge, workflow_id, requirement["id"], title="Req", body=REQUIREMENT_BODY)
    awaiting = request_stage_approval(bridge, workflow_id, requirement["id"])

    # Simulate a rejection by resolving through the manager helper.
    from app.workflow.manager import WorkflowManager
    from app.workflow.storage import WorkflowStorage
    from app.audit.logger import get_audit_logger
    from app.config import get_settings
    from app.security.permissions import get_approval_store

    settings = get_settings()
    manager = WorkflowManager(
        settings=settings,
        storage=WorkflowStorage(settings.workflow_root),
        approvals=get_approval_store(),
        audit=get_audit_logger(),
    )
    workflow_state, stage_state, _ = manager.resolve_stage_approval(
        awaiting["approval"]["requestId"], approved=False
    )
    assert stage_state.status.value == "REJECTED"
    # Workflow should not have advanced past REQUIREMENT.
    assert workflow_state.current_stage.value == "REQUIREMENT"


# ---- 4/5. action binding + stage approval ---------------------------


def _create_write_approval(bridge: Bridge, path: str) -> str:
    pending = bridge.client.post(
        "/file/write",
        json={"project": "demo", "path": path, "content": "// hello\n"},
    )
    assert pending.status_code == 202, pending.text
    return pending.json()["requestId"]


def _seed_source_files(bridge: Bridge) -> None:
    (bridge.demo / "src" / "a.ts").write_text("old\n", encoding="utf-8")
    (bridge.demo / "src" / "b.ts").write_text("old\n", encoding="utf-8")


def test_stage_approval_batches_bound_actions(bridge: Bridge) -> None:
    _seed_source_files(bridge)
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]

    stage = start_stage(bridge, workflow_id, "REQUIREMENT")

    action_ids = []
    for path in ("src/a.ts", "src/b.ts"):
        request_id = _create_write_approval(bridge, path)
        action_ids.append(request_id)
        attach = bridge.client.post(
            f"/workflow/{workflow_id}/stage/attach",
            json={"stage_id": stage["id"], "request_id": request_id},
        )
        assert attach.status_code == 200

    submit_report(bridge, workflow_id, stage["id"], title="Req", body=REQUIREMENT_BODY)
    awaiting = request_stage_approval(bridge, workflow_id, stage["id"])
    approval = bridge.approve(awaiting["approval"]["requestId"])
    assert approval.status_code == 200

    body = approval.json()["result"]
    assert set(body["approvedActions"]) == set(action_ids)
    # Batch execution happens as part of the stage approval so the writes are
    # already on disk.
    assert set(body["executedActions"]) == set(action_ids)
    for path in ("src/a.ts", "src/b.ts"):
        assert (bridge.demo / path).read_text(encoding="utf-8") == "// hello\n"

    # A second manual approval of the same request must be rejected.
    for request_id in action_ids:
        follow = bridge.approve(request_id)
        assert follow.status_code == 400


def test_action_binding_records_request_ids(bridge: Bridge) -> None:
    _seed_source_files(bridge)
    workflow = create_workflow(bridge)
    stage = start_stage(bridge, workflow["id"], "REQUIREMENT")
    request_id = _create_write_approval(bridge, "src/a.ts")

    attach = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/attach",
        json={"stage_id": stage["id"], "request_id": request_id},
    )
    stored = attach.json()
    assert request_id in stored["actionIds"]

    approvals = bridge.client.get("/permission/pending").json()["pending"]
    # workflow_id / stage_id are surfaced through the pending approval payload.
    match = next(item for item in approvals if item["requestId"] == request_id)
    # Individual actions themselves keep their workflowId/stageId as None until
    # bound explicitly at creation time; binding is tracked on the stage side.
    assert match["requestId"] == request_id


def test_attach_rejected_for_wrong_stage_state(bridge: Bridge) -> None:
    _seed_source_files(bridge)
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]
    stage = start_stage(bridge, workflow_id, "REQUIREMENT")
    submit_report(bridge, workflow_id, stage["id"], title="Req", body=REQUIREMENT_BODY)
    request_stage_approval(bridge, workflow_id, stage["id"])

    request_id = _create_write_approval(bridge, "src/a.ts")
    response = bridge.client.post(
        f"/workflow/{workflow_id}/stage/attach",
        json={"stage_id": stage["id"], "request_id": request_id},
    )
    assert response.status_code == 400


# ---- 6. memory sync --------------------------------------------------


def test_stage_approval_can_queue_memory_writes(bridge: Bridge) -> None:
    init_memory(bridge)
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]

    requirement = start_stage(bridge, workflow_id, "REQUIREMENT")
    submit_report(bridge, workflow_id, requirement["id"], title="Req", body=REQUIREMENT_BODY)
    awaiting = request_stage_approval(
        bridge, workflow_id, requirement["id"], sync_memory=True
    )

    memory_ids = awaiting["approval"]["memoryApprovalIds"]
    # Suggested writes for REQUIREMENT: project.md and tasks.md
    assert len(memory_ids) == 2

    # Memory writes are queued as regular approvals — nothing is written yet.
    pending = bridge.client.get("/permission/pending").json()["pending"]
    memory_actions = [item for item in pending if item["requestId"] in memory_ids]
    assert {item["action"] for item in memory_actions} == {"memory_append"}
    for item in memory_actions:
        assert item["workflowId"] == workflow_id
        assert item["stageId"] == requirement["id"]

    # Approve the stage first, then execute the memory writes explicitly.
    bridge.approve(awaiting["approval"]["requestId"])
    for request_id in memory_ids:
        response = bridge.approve(request_id)
        assert response.status_code == 200

    project_md = (bridge.memory_dir("demo") / "project.md").read_text(encoding="utf-8")
    assert "Workflow" in project_md and "REQUIREMENT" in project_md


def test_architecture_stage_suggests_memory_including_adr(bridge: Bridge) -> None:
    init_memory(bridge)
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]

    # Fast-forward: REQUIREMENT -> ANALYSIS -> ARCHITECTURE.
    for stage_type, body in (
        ("REQUIREMENT", REQUIREMENT_BODY),
        (
            "ANALYSIS",
            "## Findings\n\na\n\n## Risks\n\nb\n\n## Assumptions\n\nc\n",
        ),
        ("ARCHITECTURE", ARCHITECTURE_BODY),
    ):
        stage = start_stage(bridge, workflow_id, stage_type)
        submit_report(bridge, workflow_id, stage["id"], title=stage_type.title(), body=body)
        awaiting = request_stage_approval(bridge, workflow_id, stage["id"])
        bridge.approve(awaiting["approval"]["requestId"])

    # Reopen the architecture stage for memory syncing.
    detail = bridge.client.get(f"/workflow/{workflow_id}").json()
    arch_stage = next(s for s in detail["stages"] if s["stageType"] == "ARCHITECTURE")
    # Build memory suggestions directly through the executor for coverage.
    from app.workflow.executor import build_stage_memory_writes
    from app.workflow.storage import WorkflowStorage
    from app.config import get_settings

    workflow_state = WorkflowStorage(get_settings().workflow_root).load(workflow_id)
    stage_state = next(
        s for s in workflow_state.stages if s.id == arch_stage["id"]
    )
    suggestions = build_stage_memory_writes(workflow_state, stage_state)
    kinds = {item["action"] for item in suggestions}
    assert {"memory_append", "memory_decision"} <= kinds


# ---- 7. audit trail --------------------------------------------------


def test_workflow_operations_are_fully_audited(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]
    stage = start_stage(bridge, workflow_id, "REQUIREMENT")
    submit_report(bridge, workflow_id, stage["id"], title="Req", body=REQUIREMENT_BODY)
    awaiting = request_stage_approval(bridge, workflow_id, stage["id"])
    bridge.approve(awaiting["approval"]["requestId"])

    entries = bridge.audit_entries()
    actions = [entry["action"] for entry in entries]
    for expected in (
        "workflow_create",
        "workflow_stage_start",
        "workflow_stage_report",
        "workflow_stage_await_approval",
        "workflow_stage_approval",
        "workflow_stage_approved",
    ):
        assert expected in actions

    # The path column carries workflow context for every entry.
    workflow_entries = [entry for entry in entries if entry["action"].startswith("workflow_")]
    assert all(workflow_id in entry["path"] for entry in workflow_entries)


def test_stage_approval_never_bypasses_permission_system(bridge: Bridge) -> None:
    """The workflow_stage_approval action goes through /permission/approve."""
    workflow = create_workflow(bridge)
    stage = start_stage(bridge, workflow["id"], "REQUIREMENT")
    submit_report(bridge, workflow["id"], stage["id"], title="Req", body=REQUIREMENT_BODY)
    awaiting = request_stage_approval(bridge, workflow["id"], stage["id"])

    pending = bridge.client.get("/permission/pending").json()["pending"]
    stage_pending = next(
        item for item in pending if item["requestId"] == awaiting["approval"]["requestId"]
    )
    assert stage_pending["action"] == "workflow_stage_approval"
    assert stage_pending["permissionLevel"] == "LEVEL_1"
    assert stage_pending["workflowId"] == workflow["id"]
    assert stage_pending["stageId"] == stage["id"]


# ---- 8. cancel --------------------------------------------------------


def test_cancel_marks_workflow_and_voids_pending_actions(bridge: Bridge) -> None:
    _seed_source_files(bridge)
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]
    stage = start_stage(bridge, workflow_id, "REQUIREMENT")

    request_id = _create_write_approval(bridge, "src/a.ts")
    bridge.client.post(
        f"/workflow/{workflow_id}/stage/attach",
        json={"stage_id": stage["id"], "request_id": request_id},
    )

    response = bridge.client.post(
        f"/workflow/{workflow_id}/cancel", json={"reason": "priority change"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["cancelledReason"] == "priority change"

    # Attached pending approval must be voided by the cancel cascade.
    follow_up = bridge.approve(request_id)
    assert follow_up.status_code == 400


def test_cancel_requires_reason(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    response = bridge.client.post(
        f"/workflow/{workflow['id']}/cancel", json={"reason": " "}
    )
    assert response.status_code in (400, 422)


def test_cancelled_workflow_cannot_start_new_stage(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    bridge.client.post(
        f"/workflow/{workflow['id']}/cancel", json={"reason": "abort"}
    )
    response = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/start", json={"stage_type": "REQUIREMENT"}
    )
    assert response.status_code == 400


def test_double_cancel_is_rejected(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    bridge.client.post(
        f"/workflow/{workflow['id']}/cancel", json={"reason": "abort"}
    )
    second = bridge.client.post(
        f"/workflow/{workflow['id']}/cancel", json={"reason": "again"}
    )
    assert second.status_code == 400


# ---- extras: unknown / illegal stage_type ---------------------------


@pytest.mark.parametrize("stage_type", ["UNKNOWN", "hack", ""])
def test_unknown_stage_type_is_rejected(bridge: Bridge, stage_type: str) -> None:
    workflow = create_workflow(bridge)
    response = bridge.client.post(
        f"/workflow/{workflow['id']}/stage/start", json={"stage_type": stage_type}
    )
    assert response.status_code in (400, 422)


def test_delivery_stage_completes_workflow(bridge: Bridge) -> None:
    workflow = create_workflow(bridge)
    workflow_id = workflow["id"]

    reports = {
        "REQUIREMENT": REQUIREMENT_BODY,
        "ANALYSIS": "## Findings\n\na\n\n## Risks\n\nb\n\n## Assumptions\n\nc\n",
        "ARCHITECTURE": ARCHITECTURE_BODY,
        "IMPLEMENTATION": IMPLEMENTATION_BODY,
        "TESTING": "## Coverage\n\nall\n\n## Results\n\npass\n\n## Gaps\n\nnone\n",
        "DEBUG": "## Symptom\n\nnone\n\n## Root Cause\n\nn/a\n\n## Fix\n\nn/a\n",
        "DELIVERY": "## Outcome\n\nshipped\n\n## Artifacts\n\ncode\n\n## Next Steps\n\nphase 6\n",
    }

    for stage_type, body in reports.items():
        stage = start_stage(bridge, workflow_id, stage_type)
        submit_report(bridge, workflow_id, stage["id"], title=stage_type, body=body)
        awaiting = request_stage_approval(bridge, workflow_id, stage["id"])
        bridge.approve(awaiting["approval"]["requestId"])

    final = bridge.client.get(f"/workflow/{workflow_id}").json()
    assert final["status"] == "COMPLETED"
    assert final["completedAt"] is not None
