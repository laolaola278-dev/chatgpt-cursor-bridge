from __future__ import annotations

from pathlib import Path

import pytest

from app.code_intelligence import CodeIndex, CodeScanner
from app.config import get_settings
from app.intelligence import IntelligenceManager, IntelligenceStorage
from app.intelligence.analyzer import EngineeringAnalyzer
from app.intelligence.decision import DecisionManager
from app.intelligence.models import (
    DecisionStatus,
    Insight,
    InsightType,
    Proposal,
    ProposalStatus,
    RiskFactors,
    Severity,
)
from app.intelligence.recommendation import RecommendationEngine
from app.intelligence.risk import IntelligenceRiskEngine
from app.memory.intelligence import ProjectIntelligenceMemory
from app.quality.gate5 import QualityGate5Evaluator
from app.security.permissions import ApprovalStatus, ApprovalStore
from app.security.validator import ValidationFailed


def indexed(bridge):
    settings = get_settings()
    index = CodeIndex(settings.code_index_db_path, CodeScanner(settings))
    index.index_project("demo")
    return settings, index


def sample_insight(project: str = "demo", kind: InsightType = InsightType.ARCHITECTURE_RISK) -> Insight:
    return Insight("ins_1", project, kind, Severity.MEDIUM, "Coupling", "src/main.py", ["5 dependents"], "Extract a boundary", "2026-01-01T00:00:00+00:00")


def test_phase13_package_exports_domain_types():
    assert IntelligenceStorage is not None and IntelligenceManager is not None


def test_risk_low_refactor_is_explainable():
    result = IntelligenceRiskEngine().score(RiskFactors(impact_scope=1, changed_files=1))
    assert result["score"] == 7
    assert result["risk"] == "low"
    assert result["factors"]["rollbackAvailable"] is True


@pytest.mark.parametrize("scope", range(0, 11))
def test_risk_scope_is_bounded(scope):
    result = IntelligenceRiskEngine().score_factors(impact_scope=scope)
    assert 0 <= result["score"] <= 100


@pytest.mark.parametrize("files", range(0, 8))
def test_risk_changed_files_increase_or_hold(files):
    result = IntelligenceRiskEngine().score_factors(changed_files=files)
    assert 0 <= result["score"] <= 100


@pytest.mark.parametrize("coverage", [None, 0, 10, 25, 50, 60, 70, 85, 100])
def test_risk_coverage_is_safe(coverage):
    result = IntelligenceRiskEngine().score_factors(test_coverage=coverage)
    assert 0 <= result["score"] <= 100
    assert result["factors"]["testCoverage"] == coverage


@pytest.mark.parametrize("sensitive", [False, True])
def test_risk_security_factor_is_explicit(sensitive):
    result = IntelligenceRiskEngine().score_factors(security_sensitive=sensitive)
    assert result["factors"]["securitySensitive"] is sensitive
    if sensitive:
        assert result["score"] >= 15


@pytest.mark.parametrize("rollback", [False, True])
def test_risk_rollback_factor_is_explicit(rollback):
    result = IntelligenceRiskEngine().score_factors(rollback_available=rollback)
    assert result["factors"]["rollbackAvailable"] is rollback
    if not rollback:
        assert result["score"] >= 15


@pytest.mark.parametrize("kind", list(InsightType))
def test_recommendation_maps_every_insight_type(kind):
    insight = sample_insight(kind=kind)
    proposal = RecommendationEngine().from_insight(insight, dependency_count=3, changed_files=2, test_coverage=40)
    assert proposal.project == "demo"
    assert proposal.insight_id == insight.id
    assert proposal.target["file"] == insight.location
    assert proposal.risk in {"low", "medium", "high"}
    assert 0 <= proposal.risk_score <= 100

@pytest.mark.parametrize("status", list(ProposalStatus))
def test_proposal_enum_is_persistable(status):
    assert ProposalStatus(status.value).value == status.value


def test_analyzer_is_read_only_and_returns_maintenance_signal(bridge):
    settings, index = indexed(bridge)
    before = (bridge.demo / "src/main.py").read_bytes()
    insights = EngineeringAnalyzer(index).analyze("demo")
    assert insights and all(item.project == "demo" for item in insights)
    assert (bridge.demo / "src/main.py").read_bytes() == before
    assert not (settings.memory_root / "project" / "intelligence").exists()


@pytest.mark.parametrize("coverage", [0, 20, 40, 59])
def test_analyzer_emits_test_gap(bridge, coverage):
    _, index = indexed(bridge)
    insights = EngineeringAnalyzer(index).analyze("demo", test_coverage=coverage)
    assert any(item.insight_type is InsightType.TEST_GAP for item in insights)


@pytest.mark.parametrize("changed", [[], ["auth.py"], ["security/token.py"], ["permissions.py", "auth.py"]])
def test_analyzer_security_signal_is_explicit(bridge, changed):
    _, index = indexed(bridge)
    insights = EngineeringAnalyzer(index).analyze("demo", changed_files=changed)
    if changed:
        assert any(item.insight_type is InsightType.SECURITY_RISK for item in insights)


def test_analyzer_security_flag_without_files(bridge):
    _, index = indexed(bridge)
    insights = EngineeringAnalyzer(index).analyze("demo", security_sensitive=True)
    assert any(item.insight_type is InsightType.SECURITY_RISK for item in insights)


@pytest.mark.parametrize("limit", [1, 2, 5, 10, 100])
def test_storage_insight_persistence_and_filter(bridge, limit):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    item = sample_insight()
    storage.save_insights([item])
    assert storage.get_insight(item.id).as_dict()["type"] == "architecture_risk"
    assert len(storage.list_insights("demo", limit=limit)) <= limit
    assert storage.list_insights("other") == []


def test_storage_proposal_persistence(bridge):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight()
    proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight])
    storage.save_proposals([proposal])
    restored = storage.get_proposal(proposal.id)
    assert restored is not None and restored.as_dict()["status"] == "DRAFT"


@pytest.mark.parametrize("status", [None, "DRAFT", "REVIEWING", "APPROVED"])
def test_storage_proposal_status_filter(bridge, status):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight()
    proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight])
    storage.save_proposals([proposal])
    rows = storage.list_proposals("demo", status=status)
    assert all(item.project == "demo" for item in rows)
    if status:
        assert all(item.status.value == status for item in rows)


def test_manager_analysis_persists_insights_and_proposals(bridge):
    settings, index = indexed(bridge)
    result = IntelligenceManager(IntelligenceStorage(settings.intelligence_db_path), index).analyze("demo", test_coverage=20)
    assert result["readOnlyAnalysis"] is True
    assert result["insights"] and result["proposals"]
    storage = IntelligenceStorage(settings.intelligence_db_path)
    assert storage.list_insights("demo") and storage.list_proposals("demo")


def test_manager_analysis_does_not_write_memory(bridge):
    settings, index = indexed(bridge)
    IntelligenceManager(IntelligenceStorage(settings.intelligence_db_path), index).analyze("demo")
    assert ProjectIntelligenceMemory(settings).history("demo") == []


@pytest.mark.parametrize("target", ["REVIEWING", "REJECTED", "ARCHIVED"])
def test_decision_lifecycle_from_draft(bridge, target):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight()
    proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    manager = DecisionManager(storage)
    decision = manager.create(project="demo", proposal_id=proposal.id, title="Extract service", context="Coupling is growing", options=[{"name": "keep current", "risk": "high"}, {"name": "extract module", "risk": "medium"}], recommendation="extract module")
    updated = manager.transition(decision.id, target)
    assert updated.status.value == target
    assert len(updated.history) == 2


def test_decision_review_then_approve_then_implement(bridge):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    manager = DecisionManager(storage)
    decision = manager.create(project="demo", proposal_id=proposal.id, title="Extract service", context="Context", options=[{"name": "keep", "risk": "high"}, {"name": "extract", "risk": "medium"}], recommendation="extract")
    manager.transition(decision.id, "REVIEWING")
    manager.transition(decision.id, "APPROVED")
    updated = manager.transition(decision.id, "IMPLEMENTED")
    assert updated.status is DecisionStatus.IMPLEMENTED


@pytest.mark.parametrize("target", ["APPROVED", "IMPLEMENTED", "UNKNOWN", "DRAFT"])
def test_decision_illegal_transition_rejected(bridge, target):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    manager = DecisionManager(storage)
    decision = manager.create(project="demo", proposal_id=proposal.id, title="Title", context="Context", options=[{"name": "a", "risk": "low"}, {"name": "b", "risk": "medium"}], recommendation="a")
    if target == "APPROVED":
        with pytest.raises(ValidationFailed): manager.transition(decision.id, target)
    elif target in {"UNKNOWN", "DRAFT"}:
        with pytest.raises(ValidationFailed): manager.transition(decision.id, target)
    else:
        manager.transition(decision.id, "REVIEWING")
        with pytest.raises(ValidationFailed): manager.transition(decision.id, target)


@pytest.mark.parametrize("bad_options", [[], [{"name": "only", "risk": "low"}], [{"name": "", "risk": "low"}], [{"name": "a", "risk": ""}]])
def test_decision_options_require_human_readable_choices(bridge, bad_options):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    with pytest.raises(ValidationFailed):
        DecisionManager(storage).create(project="demo", proposal_id=proposal.id, title="Title", context="Context", options=bad_options, recommendation="a")


def test_decision_recommendation_must_be_an_option(bridge):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    with pytest.raises(ValidationFailed):
        DecisionManager(storage).create(project="demo", proposal_id=proposal.id, title="Title", context="Context", options=[{"name": "a", "risk": "low"}, {"name": "b", "risk": "medium"}], recommendation="c")


def test_decision_project_must_match_proposal(bridge):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    with pytest.raises(ValidationFailed):
        DecisionManager(storage).create(project="other", proposal_id=proposal.id, title="Title", context="Context", options=[{"name": "a", "risk": "low"}, {"name": "b", "risk": "medium"}], recommendation="a")


def test_decision_memory_content_is_markdown(bridge):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    decision = DecisionManager(storage).create(project="demo", proposal_id=proposal.id, title="Title", context="Context", options=[{"name": "a", "risk": "low"}, {"name": "b", "risk": "medium"}], recommendation="a")
    content = DecisionManager.memory_content(decision)
    assert content.startswith("## Title") and "Recommendation: a" in content


@pytest.mark.parametrize("architecture", [0, 25, 50, 100])
def test_quality_gate5_scores_are_bounded(architecture):
    report = QualityGate5Evaluator().evaluate(architecture_score=architecture, maintainability_score=70, risk_score=20, decision_confidence=80, technical_debt=30, technical_debt_items=12)
    assert 0 <= report["quality"] <= 100 and report["readOnly"] is True
    assert report["technicalDebt"]["items"] == 12


@pytest.mark.parametrize("risk", [0, 20, 35, 70, 100])
def test_quality_gate5_risk_bands(risk):
    report = QualityGate5Evaluator().evaluate(risk_score=risk)
    assert report["risk"] in {"low", "medium", "high"}
    assert report["riskScore"] == risk


@pytest.mark.parametrize("debt", [0, 10, 35, 70, 100])
def test_quality_gate5_technical_debt_is_visible(debt):
    report = QualityGate5Evaluator().evaluate(technical_debt=debt, technical_debt_items=debt // 5)
    assert report["technicalDebt"]["score"] == debt


def test_intelligence_memory_preview_is_read_only(bridge):
    settings, _ = indexed(bridge)
    memory = ProjectIntelligenceMemory(settings)
    preview = memory.preview("demo", "architecture", "Coupling needs review")
    assert "proposal" in preview and memory.history("demo") == []


@pytest.mark.parametrize("category,filename", [("architecture", "architecture-insights.md"), ("decisions", "engineering-decisions.md"), ("risk", "risk-history.md")])
def test_intelligence_memory_append_targets_dedicated_document(bridge, category, filename):
    settings, _ = indexed(bridge)
    result = ProjectIntelligenceMemory(settings).append_after_approval("demo", category, "approved record")
    assert result["document"] == filename
    assert (settings.memory_root / "project" / "intelligence" / "demo" / filename).exists()


@pytest.mark.parametrize("category", ["unknown", "permissions", "code"])
def test_intelligence_memory_rejects_unknown_category(bridge, category):
    settings, _ = indexed(bridge)
    with pytest.raises(ValidationFailed):
        ProjectIntelligenceMemory(settings).preview("demo", category, "no")


def test_approval_store_never_auto_approves_recovered_intelligence_memory(tmp_path):
    store = ApprovalStore(tmp_path / "approvals.db")
    request = store.create(action="intelligence_memory_append", project="demo", path="memory/project/intelligence/risk-history.md", payload={"category": "risk", "content": "review"}, reason="review", preview="proposal")
    recovered = store.recover_pending()
    assert recovered[0].status is ApprovalStatus.RECOVERED
    with pytest.raises(Exception):
        store.mark_approved(request.request_id)
    store.reconfirm(request.request_id)
    assert store.mark_approved(request.request_id).status is ApprovalStatus.APPROVED


def test_analyze_endpoint_is_pending_until_approval(bridge):
    indexed(bridge)
    pending = bridge.client.post("/intelligence/analyze", json={"project": "demo", "test_coverage": 20})
    assert pending.status_code == 202
    assert bridge.client.get("/intelligence/insights", params={"project": "demo"}).json()["insights"] == []
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    assert bridge.client.get("/intelligence/proposals", params={"project": "demo"}).json()["proposals"]


def test_decision_create_requires_approval_and_only_queues_memory_after_approval(bridge):
    indexed(bridge)
    analyze = bridge.client.post("/intelligence/analyze", json={"project": "demo", "test_coverage": 20})
    bridge.approve(analyze.json()["requestId"])
    proposal = bridge.client.get("/intelligence/proposals", params={"project": "demo"}).json()["proposals"][0]
    body = {"project": "demo", "proposal_id": proposal["id"], "title": "Extract boundary", "context": "High coupling", "options": [{"name": "keep", "risk": "high"}, {"name": "extract", "risk": "medium"}], "recommendation": "extract"}
    pending = bridge.client.post("/intelligence/decision/create", json=body)
    assert pending.status_code == 202
    assert bridge.client.get("/intelligence/decisions", params={"project": "demo"}).json()["decisions"] == []
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    decisions = bridge.client.get("/intelligence/decisions", params={"project": "demo"}).json()["decisions"]
    assert decisions and decisions[0]["status"] == "DRAFT"
    memory_pending = executed.json()["result"]["memoryProposal"]
    assert memory_pending["action"] == "intelligence_memory_append"
    assert bridge.client.get("/memory/project/history", params={"project": "demo"}).json()["history"] == []


def test_decision_memory_requires_second_approval(bridge):
    indexed(bridge)
    analyze = bridge.client.post("/intelligence/analyze", json={"project": "demo", "test_coverage": 20})
    bridge.approve(analyze.json()["requestId"])
    proposal = bridge.client.get("/intelligence/proposals", params={"project": "demo"}).json()["proposals"][0]
    pending = bridge.client.post("/intelligence/decision/create", json={"project": "demo", "proposal_id": proposal["id"], "title": "Title", "context": "Context", "options": [{"name": "a", "risk": "low"}, {"name": "b", "risk": "medium"}], "recommendation": "a"})
    result = bridge.approve(pending.json()["requestId"])
    memory_request = result.json()["result"]["memoryProposal"]["requestId"]
    assert bridge.approve(memory_request).status_code == 200
    history = bridge.client.get("/memory/project/history", params={"project": "demo"}).json()["history"]
    assert any(item.get("document") == "engineering-decisions.md" for item in history)


@pytest.mark.parametrize("endpoint", ["/intelligence/insights", "/intelligence/proposals", "/intelligence/decisions", "/quality/v5/wf_1"])
def test_intelligence_read_apis_are_read_only(bridge, endpoint):
    params = {"project": "demo"} if endpoint != "/quality/v5/wf_1" else {}
    response = bridge.client.get(endpoint, params=params)
    assert response.status_code == 200 and response.json()["readOnly"] is True


def test_intelligence_quality_api_has_phase5_fields(bridge):
    response = bridge.client.get("/quality/v5/wf_1", params={"risk_score": 75, "technical_debt": 40, "technical_debt_items": 12})
    payload = response.json()
    assert payload["risk"] == "high"
    assert payload["technicalDebt"] == {"score": 40, "items": 12}


@pytest.mark.parametrize("path", ["/intelligence/insights", "/intelligence/proposals", "/intelligence/decisions", "/memory/project/history"])
def test_empty_intelligence_reads_are_stable(bridge, path):
    payload = bridge.client.get(path, params={"project": "demo"}).json()
    assert payload["project"] == "demo"
    assert payload.get("readOnly") is True


def test_analyzer_does_not_invoke_shell_or_external_model(bridge, monkeypatch):
    settings, index = indexed(bridge)
    called = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: called.append(args))
    EngineeringAnalyzer(index).analyze("demo", security_sensitive=True)
    assert called == []


def test_storage_reopens_after_process_boundary(bridge):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); storage.save_insights([insight])
    reopened = IntelligenceStorage(Path(settings.intelligence_db_path))
    assert reopened.get_insight("ins_1") is not None


def test_decision_storage_reopens_after_process_boundary(bridge):
    settings, _ = indexed(bridge)
    storage = IntelligenceStorage(settings.intelligence_db_path)
    insight = sample_insight(); proposal = RecommendationEngine().from_insight(insight)
    storage.save_insights([insight]); storage.save_proposals([proposal])
    decision = DecisionManager(storage).create(project="demo", proposal_id=proposal.id, title="Title", context="Context", options=[{"name": "a", "risk": "low"}, {"name": "b", "risk": "medium"}], recommendation="a")
    assert IntelligenceStorage(settings.intelligence_db_path).get_decision(decision.id) is not None
