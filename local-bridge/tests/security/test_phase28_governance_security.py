"""Phase 28 · Security boundary regression tests.

The governance layer must strictly observe, analyze, evaluate, measure,
classify, recommend, and propose - and must never execute, approve itself,
modify source/dependencies, mutate policy/knowledge/memory automatically, or
call external providers. All persistent writes are approval gated.
"""

from __future__ import annotations

import subprocess  # noqa: F401  (imported to assert the layer never uses it)

import pytest

from app.intelligence.governance import (
    GovernanceRuleEngine,
    GovernanceStore,
    IntelligenceRiskAnalyzer,
    list_policies,
)
from app.security.permissions import ACTION_LEVELS, PermissionLevel
from app.security.validator import ValidationFailed

from phase28_helpers import evaluation, record, validation_store


class TestNoExecution:
    def test_no_execute_endpoint(self, bridge) -> None:
        assert bridge.client.post("/intelligence/governance/execute", json={}).status_code in (404, 405)
        assert bridge.client.post("/intelligence/governance/apply", json={}).status_code in (404, 405)
        assert bridge.client.post("/intelligence/governance/auto-fix", json={}).status_code in (404, 405)
        assert bridge.client.post("/intelligence/governance/auto-approve", json={}).status_code in (404, 405)

    def test_no_auto_learn_endpoint(self, bridge) -> None:
        assert bridge.client.post("/intelligence/governance/auto-learn", json={}).status_code in (404, 405)
        assert bridge.client.post("/intelligence/governance/auto-govern", json={}).status_code in (404, 405)

    def test_no_shell_executor_in_governance(self) -> None:
        # The governance package must never import subprocess.
        import app.intelligence.governance as gov

        assert "subprocess" not in dir(gov)


class TestApprovalBoundary:
    def test_governance_actions_are_level_1(self) -> None:
        assert ACTION_LEVELS["intelligence_governance_evaluate"] is PermissionLevel.LEVEL_1
        assert ACTION_LEVELS["intelligence_governance_review"] is PermissionLevel.LEVEL_1

    def test_evaluate_post_never_writes_without_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "confidence": 0.2, "risk_level": "HIGH", "risk_score": 70,
            },
        )
        assert pending.status_code == 202
        assert bridge.client.get("/intelligence/governance?project=demo").json()["records"] == []

    def test_evaluate_approval_writes_record(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "confidence": 0.2, "risk_level": "HIGH", "risk_score": 70,
            },
        )
        executed = bridge.approve(pending.json()["requestId"])
        assert executed.status_code == 200
        data = bridge.client.get("/intelligence/governance?project=demo").json()
        assert len(data["records"]) == 1
        assert data["records"][0]["sourceId"] == "pred-1"

    def test_review_post_never_writes_without_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "demo", "proposal_id": "review_1", "decision": "approved"},
        )
        assert pending.status_code == 202
        assert bridge.client.get("/intelligence/governance?project=demo").json()["memory"] == []

    def test_review_rejects_unknown_proposal_after_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "demo", "proposal_id": "review_missing", "decision": "approved"},
        )
        executed = bridge.approve(pending.json()["requestId"])
        assert executed.status_code == 400

    def test_review_approval_updates_proposal(self, bridge) -> None:
        # Seed a proposal through the evaluate flow.
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "confidence": 0.2, "risk_level": "CRITICAL", "risk_score": 90,
            },
        )
        bridge.approve(pending.json()["requestId"])
        data = bridge.client.get("/intelligence/governance?project=demo").json()
        proposal_id = data["reviews"][0]["proposalId"]
        review_pending = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "demo", "proposal_id": proposal_id, "decision": "approved", "reviewer_note": "ok"},
        )
        bridge.approve(review_pending.json()["requestId"])
        data = bridge.client.get("/intelligence/governance?project=demo").json()
        assert data["reviews"][0]["status"] == "approved"
        assert data["reviews"][0]["reviewerNote"] == "ok"

    def test_review_decision_must_be_approved_or_rejected(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "demo", "proposal_id": "review_1", "decision": "auto-approve"},
        )
        assert response.status_code in (400, 422)


class TestProjectIsolation:
    def test_records_isolated_across_projects(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1"},
        )
        bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/intelligence/governance?project=demo").json()["records"]) == 1
        assert bridge.client.get("/intelligence/governance?project=other").json()["records"] == []

    def test_risks_isolated_across_projects(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1", "confidence": 0.2},
        )
        bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/intelligence/governance/risk?project=demo").json()["risks"]) == 1
        assert bridge.client.get("/intelligence/governance/risk?project=other").json()["risks"] == []

    def test_violations_isolated_across_projects(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1", "confidence": 0.2},
        )
        bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/intelligence/governance/violations?project=demo").json()["violations"]) >= 1
        assert bridge.client.get("/intelligence/governance/violations?project=other").json()["violations"] == []

    def test_detail_requires_matching_project(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1"},
        )
        bridge.approve(pending.json()["requestId"])
        governance_id = bridge.client.get("/intelligence/governance?project=demo").json()["records"][0]["governanceId"]
        assert bridge.client.get(f"/intelligence/governance/{governance_id}?project=demo").status_code == 200
        assert bridge.client.get(f"/intelligence/governance/{governance_id}?project=other").status_code == 404


class TestAgentIsolation:
    def test_risk_filter_by_agent(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1", "agent_id": "agent-a"},
        )
        bridge.approve(pending.json()["requestId"])
        risks = bridge.client.get("/intelligence/governance/risk?project=demo&agent_id=agent-a").json()["risks"]
        assert len(risks) == 1
        assert risks[0]["agentId"] == "agent-a"
        assert bridge.client.get("/intelligence/governance/risk?project=demo&agent_id=agent-b").json()["risks"] == []


class TestSecretLeakage:
    def test_governance_never_returns_secrets(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "context": "uses api key sk-live-abcdef123456 and password hunter2",
            },
        )
        bridge.approve(pending.json()["requestId"])
        body = bridge.client.get("/intelligence/governance?project=demo").text
        assert "sk-live-abcdef123456" not in body
        assert "hunter2" not in body

    def test_evidence_scrubbed_at_model_level(self) -> None:
        item = record(evidence=["ok", "sk-live-abcdef123456"])
        assert "sk-live" not in " ".join(item.evidence)
        assert "ok" in item.evidence

    def test_reason_scrubbed(self) -> None:
        item = record(reason="leaked bearer abcdef123456")
        assert "bearer" not in item.reason.lower() or "abcdef123456" not in item.reason

    def test_risk_finding_scrubs_context(self) -> None:
        analysis = IntelligenceRiskAnalyzer().analyze(
            project="demo", source_kind="prediction", source_id="p1",
            context="token sk-live-abcdef123456",
        )
        assert "sk-live-abcdef123456" not in analysis.finding.reason


class TestPolicyImmutability:
    def test_policies_readonly_from_intelligence(self, bridge) -> None:
        assert bridge.client.post("/intelligence/governance/policies", json={}).status_code in (404, 405)
        assert bridge.client.put("/intelligence/governance/policies/p1", json={}).status_code in (404, 405)
        assert bridge.client.delete("/intelligence/governance/policies/p1").status_code in (404, 405)

    def test_policy_registry_has_no_mutation_methods(self) -> None:
        assert list_policies() is not None
        from app.intelligence.governance import find_policy

        assert find_policy("p_accuracy_threshold") is not None

    def test_no_policy_mutation_api_in_main(self) -> None:
        # Governance endpoints never expose a policy write action.
        assert "governance_policy_mutate" not in ACTION_LEVELS

    def test_policy_severity_never_auto_approves(self) -> None:
        result = GovernanceRuleEngine().evaluate(
            project="demo", source_kind="prediction", source_id="p1",
            confidence=0.2, risk_level="CRITICAL",
        )
        assert "approved" not in result.governance_result.lower()


class TestAutoMutationProtection:
    def test_governance_cannot_write_memory(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/governance/memory",
            json={"project_id": "demo", "category": "finding", "content": "x"},
        )
        assert response.status_code in (404, 405)

    def test_governance_cannot_write_knowledge(self, bridge) -> None:
        assert bridge.client.post("/intelligence/governance/knowledge", json={}).status_code in (404, 405)

    def test_governance_cannot_patch_source(self, bridge) -> None:
        assert bridge.client.post("/intelligence/governance/patch", json={}).status_code in (404, 405)

    def test_governance_cannot_commit_git(self, bridge) -> None:
        assert bridge.client.post("/intelligence/governance/git-commit", json={}).status_code in (404, 405)

    def test_governance_cannot_change_dependencies(self, bridge) -> None:
        assert bridge.client.post("/intelligence/governance/dependencies/upgrade", json={}).status_code in (404, 405)

    def test_no_auto_governance_memory_write(self, bridge) -> None:
        # Evaluating never writes governance memory on its own.
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1"},
        )
        bridge.approve(pending.json()["requestId"])
        assert bridge.client.get("/intelligence/governance?project=demo").json()["memory"] == []

    def test_governance_store_never_mutates_validation_store(self, tmp_path) -> None:
        validation = validation_store(tmp_path / "i.db")
        validation.save_evaluation(evaluation())
        gov = GovernanceStore(tmp_path / "g.db")
        gov.save_record(record())
        # The governance store never touches the validation store's data.
        assert len(validation.evaluations("demo")) == 1
        assert len(gov.records("demo")) == 1


class TestReadOnlyEndpoints:
    def test_risk_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance/risk?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True

    def test_trends_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance/trends?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True

    def test_policies_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance/policies?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True
        assert len(response.json()["policies"]) >= 8

    def test_violations_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance/violations?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True

    def test_reviews_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance/reviews?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True

    def test_quality_gate_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance/quality-gate?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True
        assert response.json()["gate"] == "14.0"

    def test_graph_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance/graph?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True

    def test_snapshot_endpoint_readonly(self, bridge) -> None:
        response = bridge.client.get("/intelligence/governance?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True

    def test_quality_v14_endpoint(self, bridge) -> None:
        response = bridge.client.get("/quality/v14/demo")
        assert response.status_code == 200
        assert response.json()["gate"] == "14.0"


class TestQualityGateProtection:
    def test_blocked_gate_requires_review(self) -> None:
        from app.quality.gate14 import QualityGate14Evaluator

        report = QualityGate14Evaluator().evaluate(max_risk_level="CRITICAL", max_risk_score=95)
        assert report["status"] == "BLOCKED"

    def test_gate_never_writes(self, bridge) -> None:
        before = bridge.client.get("/intelligence/governance?project=demo").json()
        bridge.client.get("/intelligence/governance/quality-gate?project=demo")
        after = bridge.client.get("/intelligence/governance?project=demo").json()
        assert before == after


class TestValidationBoundary:
    def test_evaluate_rejects_bad_source_kind(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "auto_execute", "source_id": "p1"},
        )
        assert response.status_code in (400, 422)

    def test_evaluate_rejects_bad_risk_level(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "p1", "risk_level": "EXTREME"},
        )
        assert response.status_code in (400, 422)

    def test_evaluate_rejects_path_traversal_project(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "../../etc", "source_kind": "prediction", "source_id": "p1"},
        )
        assert response.status_code in (400, 403, 422)

    def test_review_rejects_unknown_decision(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "demo", "proposal_id": "review_1", "decision": "execute"},
        )
        assert response.status_code in (400, 422)


class TestAudit:
    def test_evaluate_audited(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1"},
        )
        bridge.approve(pending.json()["requestId"])
        entries = bridge.audit_entries()
        assert any(entry.get("action") == "intelligence_governance_evaluate" for entry in entries)

    def test_review_audited(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1", "confidence": 0.1},
        )
        bridge.approve(pending.json()["requestId"])
        proposal_id = bridge.client.get("/intelligence/governance?project=demo").json()["reviews"][0]["proposalId"]
        review_pending = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "demo", "proposal_id": proposal_id, "decision": "rejected"},
        )
        bridge.approve(review_pending.json()["requestId"])
        entries = bridge.audit_entries()
        assert any(entry.get("action") == "intelligence_governance_review" for entry in entries)

    def test_records_carry_audit_request_id(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1"},
        )
        bridge.approve(pending.json()["requestId"])
        record = bridge.client.get("/intelligence/governance?project=demo").json()["records"][0]
        assert record["auditRequestId"]


class TestDeterminism:
    def test_rule_engine_deterministic(self) -> None:
        kwargs = dict(project="demo", source_kind="prediction", source_id="p1", confidence=0.2, risk_level="HIGH")
        assert GovernanceRuleEngine().evaluate(**kwargs).as_dict() == GovernanceRuleEngine().evaluate(**kwargs).as_dict()

    def test_risk_analyzer_deterministic(self) -> None:
        kwargs = dict(project="demo", source_kind="prediction", source_id="p1", confidence=0.2, evaluation_result="incorrect")
        first = IntelligenceRiskAnalyzer().analyze(**kwargs).finding.as_dict()
        second = IntelligenceRiskAnalyzer().analyze(**kwargs).finding.as_dict()
        for key in ("createdAt", "created_at", "riskId", "risk_id"):
            first.pop(key, None)
            second.pop(key, None)
        assert first == second


class TestNoExternalCalls:
    def test_governance_has_no_provider_calls(self) -> None:
        import inspect

        import app.intelligence.governance.risk as risk_module
        import app.intelligence.governance.rules as rules_module

        source = inspect.getsource(risk_module) + inspect.getsource(rules_module)
        assert "requests." not in source
        assert "httpx" not in source
        assert "openai" not in source.lower()


class TestAdditionalBoundaries:
    def test_governance_actions_never_level_2(self) -> None:
        for action in ("intelligence_governance_evaluate", "intelligence_governance_review"):
            assert ACTION_LEVELS[action] is PermissionLevel.LEVEL_1

    def test_no_privilege_escalation(self) -> None:
        # The governance layer cannot change permission policy.
        assert "governance_promote" not in ACTION_LEVELS
        assert bridge_actions() == {"intelligence_governance_evaluate", "intelligence_governance_review"}

    def test_governance_routes_never_import_subprocess(self) -> None:
        import inspect

        import app.intelligence.governance.routes as routes_module

        assert "subprocess" not in inspect.getsource(routes_module)

    def test_snapshot_never_leaks_secret_after_evaluate(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "context": "api_key=AKIA1234567890ABCDEF secret_value",
            },
        )
        bridge.approve(pending.json()["requestId"])
        body = bridge.client.get("/intelligence/governance?project=demo").text
        assert "AKIA1234567890ABCDEF" not in body
        assert "secret_value" not in body

    def test_violations_never_leak_secret(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "confidence": 0.2, "context": "api key sk-live-abcdef123456",
            },
        )
        bridge.approve(pending.json()["requestId"])
        body = bridge.client.get("/intelligence/governance/violations?project=demo").text
        assert "sk-live-abcdef123456" not in body

    def test_reviews_never_leak_secret(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "confidence": 0.2, "risk_level": "CRITICAL", "risk_score": 90,
                "evidence": ["sk-live-abcdef123456"],
            },
        )
        bridge.approve(pending.json()["requestId"])
        body = bridge.client.get("/intelligence/governance/reviews?project=demo").text
        assert "sk-live-abcdef123456" not in body

    def test_snapshot_stable_across_reads(self, bridge) -> None:
        first = bridge.client.get("/intelligence/governance?project=demo").json()
        second = bridge.client.get("/intelligence/governance?project=demo").json()
        assert first == second

    def test_trends_stable_across_reads(self, bridge) -> None:
        first = bridge.client.get("/intelligence/governance/trends?project=demo").json()
        second = bridge.client.get("/intelligence/governance/trends?project=demo").json()
        assert first == second

    def test_policies_stable_across_reads(self, bridge) -> None:
        first = bridge.client.get("/intelligence/governance/policies?project=demo").json()
        second = bridge.client.get("/intelligence/governance/policies?project=demo").json()
        assert first == second

    def test_review_decision_rejects_auto_approve(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "demo", "proposal_id": "review_1", "decision": "auto-approve"},
        )
        assert response.status_code in (400, 422)

    def test_missing_project_rejected(self, bridge) -> None:
        assert bridge.client.get("/intelligence/governance/risk").status_code == 422
        assert bridge.client.get("/intelligence/governance/trends").status_code == 422
        assert bridge.client.get("/intelligence/governance/policies").status_code == 422

    def test_review_requires_proposal_in_same_project(self, bridge) -> None:
        # Seed a proposal in demo, then try to review it under another project.
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={
                "project_id": "demo", "source_kind": "prediction", "source_id": "pred-1",
                "confidence": 0.2, "risk_level": "CRITICAL", "risk_score": 90,
            },
        )
        bridge.approve(pending.json()["requestId"])
        proposal_id = bridge.client.get("/intelligence/governance?project=demo").json()["reviews"][0]["proposalId"]
        review_pending = bridge.client.post(
            "/intelligence/governance/review",
            json={"project_id": "other", "proposal_id": proposal_id, "decision": "approved"},
        )
        assert review_pending.status_code == 202
        executed = bridge.approve(review_pending.json()["requestId"])
        assert executed.status_code == 400

    def test_approval_required_before_any_write(self, bridge) -> None:
        store_keys = (
            "/intelligence/governance/risk?project=demo",
            "/intelligence/governance/violations?project=demo",
            "/intelligence/governance/reviews?project=demo",
        )
        before = [bridge.client.get(path).json() for path in store_keys]
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1", "confidence": 0.2},
        )
        assert pending.status_code == 202
        after = [bridge.client.get(path).json() for path in store_keys]
        assert before == after

    def test_quality_gate_v14_project_scope(self, bridge) -> None:
        assert bridge.client.get("/quality/v14/other").json()["project"] == "other"

    def test_governance_policies_never_mutated_by_evaluate(self, bridge) -> None:
        before = bridge.client.get("/intelligence/governance/policies?project=demo").json()
        pending = bridge.client.post(
            "/intelligence/governance/evaluate",
            json={"project_id": "demo", "source_kind": "prediction", "source_id": "pred-1", "confidence": 0.2},
        )
        bridge.approve(pending.json()["requestId"])
        after = bridge.client.get("/intelligence/governance/policies?project=demo").json()
        assert before == after


def bridge_actions() -> set[str]:
    return {
        action
        for action in ACTION_LEVELS
        if action.startswith("intelligence_governance")
    }
