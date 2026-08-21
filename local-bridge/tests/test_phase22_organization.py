"""Phase 22 - Organization Engineering Intelligence tests.

Covers the Organization Knowledge Graph, Cross Project Learning, Engineering
Pattern Library, Organization Health aggregation, Quality Gate 10.0 and the
API surface. Every organization write must flow through the ApprovalStore; no
organization endpoint may execute, modify source or bypass human approval.
"""

from __future__ import annotations

import hashlib
import inspect

import pytest

from app.organization import (
    CrossProjectLearner,
    EngineeringPatternLibrary,
    OrganizationGraphManager,
    OrganizationHealthAggregator,
    OrganizationStorage,
)
from app.organization.models import OrgFailurePattern, PatternCategory
from app.quality.gate10 import QualityGate10Evaluator
from app.security.permissions import PermissionLevel, level_for_action
from app.security.validator import ValidationFailed


def _storage(tmp_path) -> OrganizationStorage:
    return OrganizationStorage(tmp_path / "organization.db")


# ---------------------------------------------------------------------------
# 1. Organization Knowledge Graph
# ---------------------------------------------------------------------------


def test_org_graph_register_company_team_project(tmp_path):
    storage = _storage(tmp_path)
    manager = OrganizationGraphManager(storage)
    company = manager.register("COMPANY", "Acme Inc")
    team = manager.register("TEAM", "Platform", parent_id=company.id)
    project = manager.register("PROJECT", "checkout", parent_id=team.id)
    assert company.parent_id is None
    assert team.parent_id == company.id
    assert project.parent_id == team.id

    graph = manager.get_graph()
    assert graph.company["name"] == "Acme Inc"
    assert [item["name"] for item in graph.teams] == ["Platform"]
    assert [item["name"] for item in graph.projects] == ["checkout"]
    assert graph.as_dict()["readOnly"] is True


def test_org_graph_requires_parent_for_non_company(tmp_path):
    manager = OrganizationGraphManager(_storage(tmp_path))
    with pytest.raises(ValidationFailed):
        manager.register("TEAM", "Orphan")


def test_org_graph_rejects_unknown_parent(tmp_path):
    manager = OrganizationGraphManager(_storage(tmp_path))
    with pytest.raises(ValidationFailed):
        manager.register("TEAM", "Platform", parent_id="missing")


def test_org_graph_rejects_unknown_type(tmp_path):
    manager = OrganizationGraphManager(_storage(tmp_path))
    with pytest.raises(ValidationFailed):
        manager.register("HACK", "x")


def test_org_graph_subtree(tmp_path):
    storage = _storage(tmp_path)
    manager = OrganizationGraphManager(storage)
    company = manager.register("COMPANY", "Acme")
    team = manager.register("TEAM", "Platform", parent_id=company.id)
    project = manager.register("PROJECT", "checkout", parent_id=team.id)
    subtree = manager.get_subtree(company.id)
    names = {item["name"] for item in subtree}
    assert names == {"Platform", "checkout"}
    assert len(subtree) == 2


# ---------------------------------------------------------------------------
# 2. Cross Project Learning
# ---------------------------------------------------------------------------


def test_learning_detects_exact_similar_failure():
    library = [
        {"project": "project-a", "category": "cache", "signature": "Redis cache invalidation failure"},
    ]
    matches = CrossProjectLearner().analyze(
        "project-b",
        [{"project": "project-b", "category": "cache", "signature": "Redis cache invalidation failure"}],
        library,
    )
    assert len(matches) == 1
    match = matches[0]
    assert match.source_project == "project-a"
    assert match.target_project == "project-b"
    assert match.match_score == 1.0
    assert match.message == "Similar failure detected from project-a"


def test_learning_detects_partial_similar_failure():
    library = [
        {"project": "project-a", "category": "cache", "signature": "Redis cache invalidation failure"},
    ]
    matches = CrossProjectLearner().analyze(
        "project-b",
        [{"project": "project-b", "category": "cache", "signature": "Redis cache invalidation stale keys"}],
        library,
    )
    assert len(matches) == 1
    assert 0.5 <= matches[0].match_score < 1.0


def test_learning_ignores_different_category():
    library = [{"project": "project-a", "category": "cache", "signature": "Redis cache invalidation failure"}]
    matches = CrossProjectLearner().analyze(
        "project-b",
        [{"project": "project-b", "category": "database", "signature": "Redis cache invalidation failure"}],
        library,
    )
    assert matches == []


def test_learning_excludes_same_project():
    library = [{"project": "project-a", "category": "cache", "signature": "Redis cache invalidation failure"}]
    matches = CrossProjectLearner().analyze(
        "project-a",
        [{"project": "project-a", "category": "cache", "signature": "Redis cache invalidation failure"}],
        library,
    )
    assert matches == []


# ---------------------------------------------------------------------------
# 3. Engineering Pattern Library
# ---------------------------------------------------------------------------


def test_pattern_library_record_and_list(tmp_path):
    library = EngineeringPatternLibrary(_storage(tmp_path))
    pattern = library.record(
        "successful_refactor", "Extract gateway behind interface",
        "Splitting the checkout gateway into an interface removed 40% of coupling.",
        "checkout", tags=["refactor", "gateway"],
    )
    assert pattern.category == PatternCategory.SUCCESSFUL_REFACTOR
    assert pattern.as_dict()["readOnly"] is True
    listed = library.list()
    assert len(listed) == 1
    assert library.list("successful_refactor")[0].id == pattern.id
    assert library.list("bad_migration") == []


def test_pattern_library_rejects_unknown_category(tmp_path):
    library = EngineeringPatternLibrary(_storage(tmp_path))
    with pytest.raises(ValidationFailed):
        library.record("hack", "x", "y", "demo")


def test_pattern_library_search(tmp_path):
    library = EngineeringPatternLibrary(_storage(tmp_path))
    library.record("deployment_failure", "Rollback on canary 503", "Canary deploy hit 503; rolled back.", "checkout", tags=["canary"])
    results = library.search("canary")
    assert len(results) == 1
    assert results[0].name == "Rollback on canary 503"
    assert library.search("nothing-matches") == []


def test_pattern_library_suggest(tmp_path):
    library = EngineeringPatternLibrary(_storage(tmp_path))
    library.record("deployment_failure", "Canary rollback", "Canary deploy failed and rolled back.", "checkout")
    suggestions = library.suggest("payments", ["canary", "rollback"])
    assert suggestions and suggestions[0]["category"] == "deployment_failure"


# ---------------------------------------------------------------------------
# 4. Organization Health aggregation
# ---------------------------------------------------------------------------


def test_org_health_aggregates_projects():
    report = OrganizationHealthAggregator().evaluate(
        "org",
        [
            {"project": "alpha", "healthScore": 90, "riskLevel": "low"},
            {"project": "beta", "healthScore": 70, "riskLevel": "medium"},
            {"project": "gamma", "healthScore": 50, "riskLevel": "high"},
        ],
        debt_summaries=[
            {"project": "beta", "openDebt": 8, "estimatedCost": 40},
            {"project": "gamma", "openDebt": 20, "estimatedCost": 120},
            {"project": "alpha", "openDebt": 2, "estimatedCost": 6},
        ],
    )
    assert report.project_count == 3
    assert report.org_health_score == 70  # (90 + 70 + 50) / 3
    assert report.health_by_project[0]["project"] == "alpha"
    # Debt ranking: gamma (20), beta (8), alpha (2) descending.
    assert [item["project"] for item in report.debt_ranking] == ["gamma", "beta", "alpha"]
    # Warnings for the low project only (below 60) plus medium for beta.
    codes = {warning["code"] for warning in report.warnings}
    assert "project_health_low" in codes
    assert "project_health_declining" in codes
    assert report.as_dict()["readOnly"] is True


def test_org_health_empty_org_scores_full():
    report = OrganizationHealthAggregator().evaluate("org", [])
    assert report.org_health_score == 100
    assert report.project_count == 0
    assert any(warning["code"] == "no_project_telemetry" for warning in report.warnings)


def test_org_health_agent_effectiveness():
    report = OrganizationHealthAggregator().evaluate(
        "org",
        [{"project": "alpha", "healthScore": 90, "riskLevel": "low"}],
        agent_metrics=[
            {"agentId": "a1", "tasksCompleted": 8, "failedTasks": 2, "averageQuality": 90},
            {"agentId": "a2", "tasksCompleted": 10, "failedTasks": 0, "averageQuality": 80},
        ],
    )
    assert report.agent_effectiveness
    effectiveness = report.agent_effectiveness[0]
    assert effectiveness["agentCount"] == 2
    assert 0 <= effectiveness["effectivenessScore"] <= 100


def test_org_health_risk_trends():
    report = OrganizationHealthAggregator().evaluate(
        "org",
        [{"project": "alpha", "healthScore": 60, "riskLevel": "medium"}],
        history={"alpha": [{"healthScore": 60}, {"healthScore": 80}]},
    )
    assert report.risk_trends[0]["direction"] == "declining"
    assert report.risk_trends[0]["delta"] == -20


# ---------------------------------------------------------------------------
# 5. Quality Gate 10.0
# ---------------------------------------------------------------------------


def test_gate10_clean_organization_scores_full():
    report = QualityGate10Evaluator().evaluate(org="acme", org_health_score=92, project_count=5)
    assert report["organization"] == "acme"
    assert report["orgHealthScore"] == 92
    assert report["blockingIssues"] == []
    assert report["quality"] <= 92
    assert report["readOnly"] is True


def test_gate10_perfect_org_scores_full():
    report = QualityGate10Evaluator().evaluate(org="acme", org_health_score=100)
    assert report["quality"] == 100
    assert report["blockingIssues"] == []


def test_gate10_blocks_critical_org_health():
    report = QualityGate10Evaluator().evaluate(org_health_score=40)
    assert "organization_health_critical" in report["blockingIssues"]
    assert report["quality"] < 40


def test_gate10_blocks_incidents_and_critical_projects():
    report = QualityGate10Evaluator().evaluate(org_health_score=80, open_incidents=4, critical_projects=3)
    assert "open_incidents" in report["blockingIssues"]
    assert "critical_projects" in report["blockingIssues"]


def test_gate10_api_read_only(bridge):
    response = bridge.client.get("/quality/v10/acme")
    assert response.status_code == 200
    body = response.json()
    assert body["organization"] == "acme"
    assert body["blockingIssues"] == []
    assert body["readOnly"] is True


# ---------------------------------------------------------------------------
# 6. API integration
# ---------------------------------------------------------------------------


def test_org_graph_api_read_only(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    response = bridge.client.get("/organization/graph")
    assert response.status_code == 200
    body = response.json()
    assert body["company"] is None
    assert body["projects"] == []
    assert body["readOnly"] is True
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_org_entity_register_requires_approval_and_executes(bridge):
    pending = bridge.client.post(
        "/organization/graph/entity",
        json={"type": "COMPANY", "name": "Acme Inc", "reason": "register"},
    )
    assert pending.status_code == 202
    assert pending.json()["action"] == "organization_entity_register"
    assert pending.json()["permissionLevel"] == "LEVEL_1"
    # Nothing in the graph before approval.
    assert bridge.client.get("/organization/graph").json()["company"] is None
    executed = bridge.approve(pending.json()["requestId"]).json()["result"]
    assert executed["type"] == "COMPANY"
    assert bridge.client.get("/organization/graph").json()["company"]["name"] == "Acme Inc"


def test_org_entity_register_rejects_missing_parent(bridge):
    pending = bridge.client.post(
        "/organization/graph/entity",
        json={"type": "TEAM", "name": "Platform", "parent_id": "missing", "reason": "register"},
    )
    assert pending.status_code == 404


def test_org_incident_create_requires_approval_and_lists(bridge):
    pending = bridge.client.post(
        "/organization/incident/create",
        json={"project": "demo", "title": "Redis cache failure", "summary": "stale keys after rotation", "severity": "high", "reason": "record"},
    )
    assert pending.status_code == 202
    assert bridge.client.get("/organization/incidents").json()["incidents"] == []
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    incidents = bridge.client.get("/organization/incidents").json()["incidents"]
    assert len(incidents) == 1
    assert incidents[0]["title"] == "Redis cache failure"
    assert incidents[0]["severity"] == "high"
    assert incidents[0]["readOnly"] is True


def test_org_decision_create_requires_approval_and_lists(bridge):
    pending = bridge.client.post(
        "/organization/decision/create",
        json={"project": "demo", "title": "Use Redis Cluster", "context": "scale", "decision": "adopt cluster", "consequence": "ops cost", "reason": "record"},
    )
    assert pending.status_code == 202
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    decisions = bridge.client.get("/organization/decisions?project=demo").json()["decisions"]
    assert len(decisions) == 1
    assert decisions[0]["title"] == "Use Redis Cluster"


def test_org_pattern_create_requires_approval_and_lists(bridge):
    pending = bridge.client.post(
        "/organization/pattern/create",
        json={"category": "successful_refactor", "name": "Gateway interface", "summary": "decoupled checkout", "project": "demo", "tags": ["refactor"], "reason": "record"},
    )
    assert pending.status_code == 202
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    patterns = bridge.client.get("/organization/patterns").json()["patterns"]
    assert len(patterns) == 1
    assert patterns[0]["category"] == "successful_refactor"
    # Search endpoint finds it.
    results = bridge.client.get("/organization/patterns/search", params={"q": "checkout"}).json()["patterns"]
    assert len(results) == 1


def test_cross_project_learning_scan_and_similar(bridge):
    # Project A records a failure signature via the approval-gated scan... with
    # no execution records, the analyzer produces no patterns, so seed the
    # library directly through storage for the API-level match test.
    from app.organization.storage import OrganizationStorage as OrgStorage

    storage = OrgStorage(bridge.projects_root.parent / "organization" / "organization.db")
    storage.save_failure_pattern(OrgFailurePattern(project="project-a", category="cache", signature="Redis cache invalidation failure", occurrences=3, severity="high"))

    similar = bridge.client.get(
        "/organization/learning/similar",
        params={"project": "project-b", "category": "cache", "signature": "Redis cache invalidation failure"},
    )
    assert similar.status_code == 200
    body = similar.json()
    assert body["readOnly"] is True
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["sourceProject"] == "project-a"
    assert match["targetProject"] == "project-b"
    assert "Similar failure detected from project-a" in match["message"]


def test_org_learning_scan_requires_approval(bridge):
    pending = bridge.client.post("/organization/learning/scan", json={"project": "demo", "reason": "scan"})
    assert pending.status_code == 202
    assert pending.json()["action"] == "organization_learning_scan"
    assert pending.json()["permissionLevel"] == "LEVEL_1"


def test_org_health_api_read_only(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    response = bridge.client.get("/organization/health")
    assert response.status_code == 200
    body = response.json()
    assert body["org"] == "organization"
    assert body["projectCount"] == 1  # demo project in the workspace
    assert isinstance(body["orgHealthScore"], int)
    assert 0 <= body["orgHealthScore"] <= 100
    assert body["readOnly"] is True
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_org_dashboard_api_read_only(bridge):
    response = bridge.client.get("/organization/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["readOnly"] is True
    assert "successful_refactor" in body["categories"]
    assert body["graph"]["company"] is None


# ---------------------------------------------------------------------------
# 7. Security regression
# ---------------------------------------------------------------------------


def test_org_get_endpoints_never_modify_source(bridge):
    before = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    for path in (
        "/organization/graph",
        "/organization/incidents",
        "/organization/decisions",
        "/organization/patterns",
        "/organization/health",
        "/organization/dashboard",
        "/quality/v10/acme",
    ):
        assert bridge.client.get(path).status_code == 200
    after = hashlib.sha256(bridge.demo.joinpath("src/main.py").read_bytes()).hexdigest()
    assert before == after


def test_org_posts_never_auto_execute(bridge):
    for endpoint, payload in (
        ("/organization/graph/entity", {"type": "COMPANY", "name": "Acme", "reason": "r"}),
        ("/organization/incident/create", {"project": "demo", "title": "t", "summary": "s", "reason": "r"}),
        ("/organization/decision/create", {"project": "demo", "title": "t", "context": "c", "decision": "d", "consequence": "c", "reason": "r"}),
        ("/organization/pattern/create", {"category": "successful_refactor", "name": "n", "summary": "s", "project": "demo", "reason": "r"}),
        ("/organization/learning/scan", {"project": "demo", "reason": "r"}),
    ):
        pending = bridge.client.post(endpoint, json=payload)
        assert pending.status_code == 202
        assert pending.json()["status"] == "pending"
    assert bridge.client.get("/organization/graph").json()["company"] is None
    assert bridge.client.get("/organization/incidents").json()["incidents"] == []
    assert bridge.client.get("/organization/patterns").json()["patterns"] == []


def test_org_actions_are_level_one():
    for action in (
        "organization_entity_register",
        "organization_incident_create",
        "organization_decision_create",
        "organization_pattern_create",
        "organization_learning_scan",
    ):
        assert level_for_action(action) == PermissionLevel.LEVEL_1


def test_org_writes_are_audited(bridge):
    pending = bridge.client.post(
        "/organization/pattern/create",
        json={"category": "architecture_success", "name": "n", "summary": "s", "project": "demo", "reason": "r"},
    )
    bridge.approve(pending.json()["requestId"])
    entries = bridge.audit_entries()
    assert any(entry["action"] == "organization_pattern_create" and entry["approved"] for entry in entries)


def test_org_modules_have_no_execution_entrypoint():
    from app.organization.graph import OrganizationGraphManager as GraphClass
    from app.organization.health import OrganizationHealthAggregator as HealthClass
    from app.organization.learning import CrossProjectLearner as LearnerClass
    from app.organization.patterns import EngineeringPatternLibrary as LibraryClass
    from app.organization.storage import OrganizationStorage as StorageClass

    for cls in (GraphClass, HealthClass, LearnerClass, LibraryClass, StorageClass):
        source = inspect.getsource(cls)
        assert "subprocess" not in source
        assert "shell" not in source.lower()
        assert "mark_approved" not in source
        assert "approvals.create" not in source
