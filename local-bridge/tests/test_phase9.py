"""Phase 9 model routing, multi-agent runtime and quality gate tests."""

from __future__ import annotations

import pytest

from app.agent import AgentManager, AgentStorage, AgentStatus
from app.audit.logger import AuditLogger
from app.model_router import ModelRouter, TaskType
from app.security.validator import ApprovalError
from app.workflow.quality_gate import build_quality_gate


def test_model_router_classifies_and_selects_by_capability() -> None:
    router = ModelRouter()
    route = router.route("review the architecture risk and quality audit")
    assert route.classification.task_type is TaskType.REVIEW
    from app.model_router import ModelCapability
    assert ModelCapability.REVIEW in route.model.capabilities
    assert route.model.id == "local/reviewer-v1"


def test_agent_lifecycle_is_scoped_and_messages_are_audited(tmp_path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    manager = AgentManager(storage=AgentStorage(tmp_path / "agents"), audit=audit)
    planner = manager.create(
        project="demo",
        session_id="ses_1234567890abcdef",
        role="PLANNER",
        memory_scope="demo/project.md",
    )
    reviewer = manager.create(
        project="demo",
        session_id="ses_1234567890abcdef",
        role="REVIEWER",
        memory_scope="demo/review",
    )
    assert planner.status is AgentStatus.CREATED
    assert manager.transition(planner.id, "ACTIVE").status is AgentStatus.ACTIVE
    message = manager.send_message(
        from_agent=planner.id,
        to_agent=reviewer.id,
        task="Review the proposed architecture",
        context_reference="context/demo/current.json",
    )
    assert message.from_agent == planner.id
    assert manager.messages("demo")[0]["toAgent"] == reviewer.id
    assert {entry["action"] for entry in audit.read_entries()} >= {
        "agent_created",
        "agent_transition",
        "agent_message",
    }


def test_agent_role_cannot_expand_permissions(tmp_path) -> None:
    manager = AgentManager(
        storage=AgentStorage(tmp_path / "agents"),
        audit=AuditLogger(tmp_path / "audit.jsonl"),
    )
    with pytest.raises(ApprovalError):
        manager.create(
            project="demo",
            session_id="ses_1234567890abcdef",
            role="CODER",
            memory_scope="demo",
            permissions=["shell_command"],
        )


def test_quality_gate_requires_review_test_and_risk() -> None:
    gate = build_quality_gate(
        review_status="approved",
        test_passed=True,
        risk_level="medium",
        risk_assessment="No high-risk changes detected.",
        reviewer_agent_id="ag_reviewer123456",
        tester_agent_id="ag_tester123456",
    )
    assert gate["readyForHumanApproval"] is True
    assert gate["testPassed"] is True
    with pytest.raises(Exception):
        build_quality_gate(
            review_status="approved",
            test_passed=False,
            risk_level="low",
            risk_assessment="missing test result",
            reviewer_agent_id="ag_reviewer123456",
            tester_agent_id="ag_tester123456",
        )


def test_agent_creation_endpoint_remains_approval_gated(bridge) -> None:
    session_pending = bridge.client.post(
        "/session/create",
        json={"project": "demo", "reason": "Create runtime session"},
    )
    assert session_pending.status_code == 202
    session_result = bridge.approve(session_pending.json()["requestId"])
    assert session_result.status_code == 200
    session_id = session_result.json()["result"]["id"]

    pending = bridge.client.post(
        "/agent/create",
        json={
            "project": "demo",
            "session_id": session_id,
            "role": "CODER",
            "memory_scope": "demo/src",
            "reason": "Prepare implementation agent",
        },
    )
    assert pending.status_code == 202
    assert bridge.client.get("/agent/status?project=demo").json()["agents"] == []

    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    assert executed.json()["result"]["role"] == "CODER"
    status = bridge.client.get("/agent/status?project=demo").json()
    assert len(status["agents"]) == 1
    assert status["agents"][0]["modelId"] == "local/coder-v1"
    assert any(entry["action"] == "agent_created" for entry in bridge.audit_entries())
