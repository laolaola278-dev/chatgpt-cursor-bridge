"""Phase 21 - Engineering Governance Layer tests.

Covers the Engineering Health Monitor, Architecture Drift Detection, Technical
Debt lifecycle, Engineering Policy Engine, Governance Timeline memory, Quality
Gate 9.0 and the API surface. Every governance write must flow through the
ApprovalStore; no governance endpoint may execute, modify source or bypass
human approval.
"""

from __future__ import annotations

import hashlib
import inspect

import pytest

from app.governance import (
    ArchitectureDriftDetector,
    DebtManager,
    EngineeringHealthManager,
    GovernanceStorage,
    PolicyEngine,
)
from app.governance.models import DebtStatus
from app.governance.health import EngineeringHealthManager as HealthManagerClass
from app.governance.debt.manager import DebtManager as DebtManagerClass
from app.governance.architecture.detector import ArchitectureDriftDetector as DriftDetectorClass
from app.governance.policy.engine import PolicyEngine as PolicyEngineClass
from app.governance.storage import GovernanceStorage as GovernanceStorageClass
from app.quality.gate9 import QualityGate9Evaluator
from app.security.permissions import PermissionLevel, level_for_action
from app.security.validator import ValidationFailed


# ---------------------------------------------------------------------------
# 1. Engineering Health Monitor
# ---------------------------------------------------------------------------


def test_health_manager_returns_stable_report_for_empty_project():
    report = EngineeringHealthManager().evaluate("demo")
    assert report.project == "demo"
    assert 0 <= report.health_score <= 100
    assert report.health_score >= 80
    assert report.risk_level == "low"
    assert report.warnings == []
    assert any(rec.code == "maintain_health" for rec in report.recommendations)
    assert report.as_dict()["readOnly"] is True


def test_health_manager_flags_failure_frequency():
    loops = [{"id": "loop_1", "status": "FAILED"}, {"id": "loop_2", "status": "COMPLETED"}]
    failures = [{"id": "f1"}, {"id": "f2"}, {"id": "f3"}]
    report = EngineeringHealthManager().evaluate(
        "demo", loops=loops, results=[], failures=failures
    )
    codes = {warning.code for warning in report.warnings}
    assert "failure_frequency_high" in codes
    assert report.risk_level in {"low", "medium", "high"}


def test_health_manager_flags_rollback_frequency():
    loops = [
        {"id": "loop_1", "status": "ROLLED_BACK"},
        {"id": "loop_2", "status": "ROLLED_BACK"},
        {"id": "loop_3", "status": "COMPLETED"},
    ]
    report = EngineeringHealthManager().evaluate("demo", loops=loops)
    codes = {warning.code for warning in report.warnings}
    assert "rollback_frequency_high" in codes


def test_health_manager_flags_test_stability():
    results = [
        {"id": "r1", "verification": {"status": "PASS"}, "qualityScore": 100, "riskScore": "low"},
        {"id": "r2", "verification": {"status": "FAIL"}, "qualityScore": 0, "riskScore": "low"},
        {"id": "r3", "verification": {"status": "FAIL"}, "qualityScore": 0, "riskScore": "low"},
    ]
    report = EngineeringHealthManager().evaluate("demo", results=results)
    codes = {warning.code for warning in report.warnings}
    assert "test_stability_low" in codes


def test_health_manager_never_touches_source(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    EngineeringHealthManager().evaluate("demo")
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_health_api_read_only(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    response = bridge.client.get("/governance/health/demo")
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "demo"
    assert isinstance(body["healthScore"], int)
    assert 0 <= body["healthScore"] <= 100
    assert body["riskLevel"] in {"low", "medium", "high"}
    assert body["readOnly"] is True
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_health_api_records_snapshot(bridge):
    bridge.client.get("/governance/health/demo")
    storage = GovernanceStorage(bridge.projects_root.parent / "governance" / "governance.db")
    snapshots = storage.list_health("demo")
    assert len(snapshots) == 1
    assert snapshots[0]["healthScore"] is not None


# ---------------------------------------------------------------------------
# 2. Architecture Drift Detection
# ---------------------------------------------------------------------------


def test_drift_detects_unrecorded_dependency():
    report = ArchitectureDriftDetector().detect(
        "demo",
        graph={},
        code_files=[],
        dependencies=[{"source": "app/main.py", "target": "app/unknown.py"}],
    )
    types = {issue.issue_type for issue in report.issues}
    assert "unrecorded_dependency" in types
    assert report.drift_score > 0
    assert report.risk_level in {"low", "medium", "high"}


def test_drift_detects_module_boundary_change():
    report = ArchitectureDriftDetector().detect(
        "demo",
        graph={"nodes": [], "edges": []},
        code_files=[{"path": "new_module/x.py"}],
    )
    types = {issue.issue_type for issue in report.issues}
    assert "module_boundary_change" in types


def test_drift_detects_circular_dependency():
    report = ArchitectureDriftDetector().detect(
        "demo",
        dependencies=[
            {"source": "app/a.py", "target": "app/b.py"},
            {"source": "app/b.py", "target": "app/a.py"},
        ],
    )
    types = {issue.issue_type for issue in report.issues}
    assert "circular_dependency" in types
    assert any(issue.severity == "high" for issue in report.issues)


def test_drift_detects_deprecated_component_usage():
    report = ArchitectureDriftDetector().detect(
        "demo",
        dependencies=[{"source": "app/main.py", "target": "legacy_util"}],
        deprecated_components=["legacy_util"],
    )
    types = {issue.issue_type for issue in report.issues}
    assert "deprecated_component_usage" in types


def test_drift_detects_design_decision_drift():
    report = ArchitectureDriftDetector().detect(
        "demo",
        graph={"nodes": [], "edges": []},
        decisions=[{"id": "ADR-001", "title": "Adopt FastAPI", "status": "APPROVED"}],
    )
    types = {issue.issue_type for issue in report.issues}
    assert "design_decision_drift" in types


def test_drift_api_read_only(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    response = bridge.client.get("/governance/drift/demo")
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "demo"
    assert isinstance(body["driftScore"], int)
    assert "issues" in body
    assert body["readOnly"] is True
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_drift_api_records_snapshot(bridge):
    bridge.client.get("/governance/drift/demo")
    storage = GovernanceStorage(bridge.projects_root.parent / "governance" / "governance.db")
    assert len(storage.list_drift("demo")) == 1


# ---------------------------------------------------------------------------
# 3. Technical Debt Management
# ---------------------------------------------------------------------------


def _debt_manager(tmp_path) -> DebtManager:
    return DebtManager(GovernanceStorage(tmp_path / "governance.db"))


def test_debt_lifecycle_strict_forward_chain(tmp_path):
    manager = _debt_manager(tmp_path)
    item = manager.create(
        "demo", category="code", severity="medium", source="legacy module",
        affected_components=["app/legacy.py"], estimated_cost=8, risk="medium",
    )
    assert item.status == DebtStatus.OPEN
    expected = [DebtStatus.ANALYZING, DebtStatus.PROPOSED, DebtStatus.APPROVED, DebtStatus.RESOLVED, DebtStatus.VERIFIED]
    for target in expected:
        item = manager.transition(item.id, target.value)
        assert item.status == target
    with pytest.raises(ValidationFailed):
        manager.transition(item.id, DebtStatus.OPEN.value)


def test_debt_rejects_illegal_jump(tmp_path):
    manager = _debt_manager(tmp_path)
    item = manager.create("demo", category="test", severity="low", source="x")
    with pytest.raises(ValidationFailed):
        manager.transition(item.id, DebtStatus.APPROVED.value)


def test_debt_rejects_unknown_category(tmp_path):
    manager = _debt_manager(tmp_path)
    with pytest.raises(ValidationFailed):
        manager.create("demo", category="hack", severity="low", source="x")


def test_debt_items_are_read_only_metadata(tmp_path):
    manager = _debt_manager(tmp_path)
    item = manager.create("demo", category="code", severity="high", source="x", estimated_cost=42, risk="high")
    payload = item.as_dict()
    assert payload["status"] == "OPEN"
    assert payload["estimatedCost"] == 42
    assert payload["readOnly"] is True


def test_debt_create_requires_approval(bridge):
    pending = bridge.client.post(
        "/governance/debt/create",
        json={"project": "demo", "category": "code", "severity": "medium", "source": "test debt", "reason": "record"},
    )
    assert pending.status_code == 202
    body = pending.json()
    assert body["action"] == "governance_debt_create"
    assert body["permissionLevel"] == "LEVEL_1"
    assert body["status"] == "pending"
    # Nothing executes before explicit approval.
    listed = bridge.client.get("/governance/debt/demo").json()
    assert listed["debt"] == []


def test_debt_approval_executes_and_lists(bridge):
    pending = bridge.client.post(
        "/governance/debt/create",
        json={"project": "demo", "category": "code", "severity": "medium", "source": "test debt", "reason": "record"},
    )
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    listed = bridge.client.get("/governance/debt/demo").json()
    assert len(listed["debt"]) == 1
    assert listed["debt"][0]["category"] == "code"
    assert listed["debt"][0]["status"] == "OPEN"
    assert listed["readOnly"] is True


def test_debt_transition_requires_approval(bridge):
    pending = bridge.client.post(
        "/governance/debt/create",
        json={"project": "demo", "category": "code", "severity": "low", "source": "x", "reason": "record"},
    )
    debt_id = bridge.approve(pending.json()["requestId"]).json()["result"]["id"]
    transition = bridge.client.post(
        f"/governance/debt/{debt_id}/transition",
        json={"status": "ANALYZING", "reason": "investigating"},
    )
    assert transition.status_code == 202
    assert transition.json()["action"] == "governance_debt_transition"
    # Not applied until approved.
    listed = bridge.client.get("/governance/debt/demo").json()
    assert listed["debt"][0]["status"] == "OPEN"
    assert bridge.approve(transition.json()["requestId"]).status_code == 200
    listed = bridge.client.get("/governance/debt/demo").json()
    assert listed["debt"][0]["status"] == "ANALYZING"


# ---------------------------------------------------------------------------
# 4. Engineering Policy Engine
# ---------------------------------------------------------------------------


def test_policy_high_risk_requires_review():
    evaluations = PolicyEngine().evaluate({"risk": "high"})
    result = {evaluation.policy: evaluation.result for evaluation in evaluations}
    assert result["high_risk_change_requires_review"] == "approval_required"


def test_policy_test_coverage_drop_warning():
    evaluations = PolicyEngine().evaluate({"test_coverage": 40})
    result = {evaluation.policy: evaluation.result for evaluation in evaluations}
    assert result["test_coverage_drop_warning"] == "warning"


def test_policy_architecture_drift_approval_required():
    evaluations = PolicyEngine().evaluate({"drift_score": 80, "drift_threshold": 50})
    result = {evaluation.policy: evaluation.result for evaluation in evaluations}
    assert result["architecture_drift_approval_required"] == "approval_required"


def test_policy_rollback_frequency_investigation():
    evaluations = PolicyEngine().evaluate({"rollback_rate": 0.5})
    result = {evaluation.policy: evaluation.result for evaluation in evaluations}
    assert result["rollback_frequency_investigation"] == "warning"


def test_policy_debt_growth_warning():
    evaluations = PolicyEngine().evaluate({"open_debt": 12, "debt_threshold": 10})
    result = {evaluation.policy: evaluation.result for evaluation in evaluations}
    assert result["debt_growth_warning"] == "warning"


def test_policy_only_warns_or_approves_never_executes():
    signals = [
        {"risk": "low"},
        {"risk": "high"},
        {"test_coverage": 90},
        {"test_coverage": 10},
        {"drift_score": 100, "drift_threshold": 50},
        {"rollback_rate": 0.5},
        {"open_debt": 25},
        {},
    ]
    for signal in signals:
        for evaluation in PolicyEngine().evaluate(signal):
            assert evaluation.result in {"pass", "warning", "approval_required"}
            assert evaluation.severity in {"low", "medium", "high"}


def test_policy_rejects_unexpected_signal_keys():
    with pytest.raises(ValidationFailed):
        PolicyEngine().evaluate({"risk": "low", "unknown_signal": 1})


def test_policy_evaluate_requires_approval(bridge):
    pending = bridge.client.post(
        "/governance/policy/evaluate",
        json={"project": "demo", "signal": {"risk": "high"}, "reason": "check policy"},
    )
    assert pending.status_code == 202
    assert pending.json()["action"] == "governance_policy_evaluate"
    assert pending.json()["permissionLevel"] == "LEVEL_1"
    # No policy events until approved.
    events = bridge.client.get("/governance/policies?project=demo").json()["events"]
    assert events == []


def test_policy_approval_records_events(bridge):
    pending = bridge.client.post(
        "/governance/policy/evaluate",
        json={"project": "demo", "signal": {"risk": "high"}, "reason": "check policy"},
    )
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    body = bridge.client.get("/governance/policies?project=demo").json()
    assert "high_risk_change_requires_review" in body["policies"]
    assert len(body["events"]) >= 1
    assert body["readOnly"] is True


# ---------------------------------------------------------------------------
# 5. Governance Timeline memory
# ---------------------------------------------------------------------------


def test_timeline_api_read_only(bridge):
    response = bridge.client.get("/governance/timeline", params={"project": "demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "demo"
    assert body["healthSnapshots"] == []
    assert body["driftSnapshots"] == []
    assert body["memory"] == []
    assert body["readOnly"] is True


def test_timeline_append_requires_approval_then_appends(bridge):
    pending = bridge.client.post(
        "/governance/timeline/append",
        json={"project": "demo", "category": "health", "content": "Health score stable at 90", "reason": "record"},
    )
    assert pending.status_code == 202
    assert pending.json()["action"] == "governance_memory_append"
    # No memory write before approval.
    assert bridge.client.get("/governance/timeline", params={"project": "demo"}).json()["memory"] == []
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    memory = bridge.client.get("/governance/timeline", params={"project": "demo"}).json()["memory"]
    assert len(memory) == 1
    assert memory[0]["category"] == "health"
    assert memory[0]["document"] == "health-reports.md"


def test_timeline_append_rejects_unknown_category(bridge):
    pending = bridge.client.post(
        "/governance/timeline/append",
        json={"project": "demo", "category": "hack", "content": "x", "reason": "record"},
    )
    assert pending.status_code == 400


# ---------------------------------------------------------------------------
# 6. Quality Gate 9.0
# ---------------------------------------------------------------------------


def test_gate9_clean_project_scores_full():
    report = QualityGate9Evaluator().evaluate()
    assert report["healthScore"] == 100
    assert report["architectureRisk"] == "low"
    assert report["debtScore"] == 0
    assert report["policyViolations"] == 0
    assert report["blockingIssues"] == []
    assert report["quality"] == 100
    assert report["readOnly"] is True


def test_gate9_blocks_critical_health():
    report = QualityGate9Evaluator().evaluate(health_score=40)
    assert "health_critical" in report["blockingIssues"]
    assert report["quality"] < 100


def test_gate9_blocks_high_architecture_risk():
    report = QualityGate9Evaluator().evaluate(architecture_risk="high")
    assert "architecture_risk_high" in report["blockingIssues"]


def test_gate9_blocks_high_debt_and_policy_violations():
    report = QualityGate9Evaluator().evaluate(debt_score=70, policy_violations=3)
    assert "debt_score_high" in report["blockingIssues"]
    assert "policy_violations" in report["blockingIssues"]


def test_gate9_api_read_only(bridge):
    response = bridge.client.get("/quality/v9/wf_demo")
    assert response.status_code == 200
    body = response.json()
    assert body["workflowId"] == "wf_demo"
    assert body["healthScore"] == 100
    assert body["blockingIssues"] == []
    assert body["readOnly"] is True


# ---------------------------------------------------------------------------
# 7. Security regression
# ---------------------------------------------------------------------------


def test_governance_get_endpoints_never_modify_source(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    for path in (
        "/governance/health/demo",
        "/governance/drift/demo",
        "/governance/debt/demo",
        "/governance/policies?project=demo",
        "/governance/timeline?project=demo",
        "/quality/v9/wf_demo",
    ):
        assert bridge.client.get(path).status_code == 200
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_governance_posts_never_auto_execute(bridge):
    pending = bridge.client.post(
        "/governance/debt/create",
        json={"project": "demo", "category": "code", "severity": "medium", "source": "x", "reason": "record"},
    )
    assert pending.status_code == 202
    assert pending.json()["status"] == "pending"
    assert bridge.client.get("/governance/debt/demo").json()["debt"] == []
    assert bridge.client.get("/permission/pending").json()["pending"]


def test_governance_actions_are_level_one():
    for action in (
        "governance_debt_create",
        "governance_debt_transition",
        "governance_policy_evaluate",
        "governance_memory_append",
    ):
        assert level_for_action(action) == PermissionLevel.LEVEL_1


def test_governance_writes_are_audited(bridge):
    pending = bridge.client.post(
        "/governance/debt/create",
        json={"project": "demo", "category": "code", "severity": "low", "source": "x", "reason": "record"},
    )
    bridge.approve(pending.json()["requestId"])
    actions = {entry["action"] for entry in bridge.audit_entries()}
    assert "governance_debt_create" in actions
    assert any(entry["action"] == "governance_debt_create" and entry["approved"] for entry in bridge.audit_entries())


def test_governance_modules_have_no_execution_entrypoint():
    for cls in (HealthManagerClass, DebtManagerClass, DriftDetectorClass, PolicyEngineClass, GovernanceStorageClass):
        source = inspect.getsource(cls)
        assert "subprocess" not in source
        assert "shell" not in source.lower()
        assert "mark_approved" not in source
    # The policy engine can only emit evaluations, never gate execution.
    source = inspect.getsource(PolicyEngineClass)
    assert "approve" not in source.lower()
    assert "block(" not in source.lower()
