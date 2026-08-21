"""Phase 22 organization intelligence API routes.

Read-only organization endpoints (graph, incidents, decisions, patterns,
cross-project learning, aggregated health, dashboard, Quality Gate 10.0) plus
approval-gated writes (entity register, incident create, decision create,
pattern create). No route here can execute actions or modify source code.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.execution import ExecutionManager, ExecutionStorage
from app.execution_loop import ExecutionLoopStorage
from app.failure_intelligence import FailureIntelligenceAnalyzer
from app.governance import EngineeringHealthManager
from app.governance.storage import GovernanceStorage
from app.metrics import MetricsManager
from app.models.request import (
    OrganizationDecisionCreateRequest,
    OrganizationEntityCreateRequest,
    OrganizationIncidentCreateRequest,
    OrganizationLearningScanRequest,
    OrganizationPatternCreateRequest,
)
from app.organization.graph import OrganizationGraphManager
from app.organization.health import OrganizationHealthAggregator
from app.organization.learning import CrossProjectLearner
from app.organization.models import PatternCategory
from app.organization.patterns import EngineeringPatternLibrary
from app.organization.storage import OrganizationStorage
from app.quality.gate10 import QualityGate10Evaluator
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.workflow.manager import WorkflowManager
from app.workflow.storage import WorkflowStorage


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def workflow_storage_dependency(
    settings: Settings = Depends(settings_dependency),
) -> WorkflowStorage:
    from app.main import _get_workflow_storage_cached

    return _get_workflow_storage_cached(str(settings.workflow_root))


def workflow_manager_dependency(
    settings: Settings = Depends(settings_dependency),
    storage: WorkflowStorage = Depends(workflow_storage_dependency),
    approvals: ApprovalStore = Depends(approvals_dependency),
    audit: AuditLogger = Depends(audit_dependency),
) -> WorkflowManager:
    return WorkflowManager(settings=settings, storage=storage, approvals=approvals, audit=audit)


def _org_storage(settings: Settings) -> OrganizationStorage:
    return OrganizationStorage(settings.organization_db_path)


def _compute_project_health(
    settings: Settings,
    audit: AuditLogger,
    approvals: ApprovalStore,
    workflow_manager: WorkflowManager,
    org_storage: OrganizationStorage,
    project: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Derive a per-project EngineeringHealthReport using the same signals as
    the governance layer, then snapshot it into the org store.

    Returns (report_dict, failure_patterns).
    """
    loops = [loop.as_dict() for loop in ExecutionLoopStorage(settings.execution_loop_db_path).list_loops(project=project)]
    execution = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager)
    results = [result.as_dict() for result in execution.list_results(project=project)]
    failures = [pattern.as_dict() for pattern in FailureIntelligenceAnalyzer().analyze(project, loops=loops, results=results)]
    agent_records = [record.as_dict() for record in MetricsManager(settings.agent_root, audit).list()]
    history = org_storage.list_health(project, limit=1)
    report = EngineeringHealthManager().evaluate(
        project, loops=loops, results=results, failures=failures,
        agent_metrics=agent_records, history=history,
    )
    org_storage.record_health(project, report.as_dict())
    return report.as_dict(), failures


def register_organization_routes(app: Any) -> None:
    """Attach all Phase 22 organization routes to the FastAPI app."""

    @app.get("/organization/graph", tags=["organization"])
    def organization_graph(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        graph = OrganizationGraphManager(_org_storage(settings)).get_graph()
        audit.record(
            action="organization_graph_read", path="organization/graph",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(graph.projects)} project(s), {len(graph.teams)} team(s)",
        )
        return graph.as_dict()

    @app.post("/organization/graph/entity", status_code=status.HTTP_202_ACCEPTED, tags=["organization"])
    def organization_entity_create(
        body: OrganizationEntityCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        preview = f"REGISTER {body.type.upper()} entity '{body.name}'"
        if body.parent_id:
            parent = _org_storage(settings).get_entity(body.parent_id)
            if parent is None:
                from app.security.validator import ResourceNotFound

                raise ResourceNotFound(f"Parent entity '{body.parent_id}' was not found")
        return _register_pending(
            action="organization_entity_register", project="organization", path="organization/graph",
            payload={"type": body.type, "name": body.name, "parent_id": body.parent_id, "metadata": body.metadata},
            reason=body.reason, preview_factory=lambda: preview,
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/organization/incidents", tags=["organization"])
    def organization_incidents(
        project: str | None = Query(default=None, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        incidents = [incident.as_dict() for incident in _org_storage(settings).list_incidents(project)]
        audit.record(
            action="organization_incidents_read", path=project or "*",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(incidents)} incident(s)",
        )
        return {"incidents": incidents, "readOnly": True}

    @app.post("/organization/incident/create", status_code=status.HTTP_202_ACCEPTED, tags=["organization"])
    def organization_incident_create(
        body: OrganizationIncidentCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_incident_create", project=body.project, path="organization/incidents",
            payload={"project": body.project, "title": body.title, "summary": body.summary,
                     "severity": body.severity, "service": body.service, "signature": body.signature},
            reason=body.reason,
            preview_factory=lambda: f"CREATE record-only incident '{body.title}' ({body.severity}); no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/organization/decisions", tags=["organization"])
    def organization_decisions(
        project: str | None = Query(default=None, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        decisions = [decision.as_dict() for decision in _org_storage(settings).list_decisions(project)]
        audit.record(
            action="organization_decisions_read", path=project or "*",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(decisions)} decision(s)",
        )
        return {"decisions": decisions, "readOnly": True}

    @app.post("/organization/decision/create", status_code=status.HTTP_202_ACCEPTED, tags=["organization"])
    def organization_decision_create(
        body: OrganizationDecisionCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_decision_create", project=body.project, path="organization/decisions",
            payload={"project": body.project, "title": body.title, "context": body.context,
                     "decision": body.decision, "consequence": body.consequence},
            reason=body.reason,
            preview_factory=lambda: f"CREATE record-only org architecture decision '{body.title}'; no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/organization/patterns", tags=["organization"])
    def organization_patterns(
        category: str | None = Query(default=None, max_length=32),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        patterns = [pattern.as_dict() for pattern in EngineeringPatternLibrary(_org_storage(settings)).list(category)]
        audit.record(
            action="organization_patterns_read", path=category or "*",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(patterns)} pattern(s)",
        )
        return {"patterns": patterns, "readOnly": True}

    @app.get("/organization/patterns/search", tags=["organization"])
    def organization_patterns_search(
        q: str = Query(..., min_length=1, max_length=200),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        patterns = [pattern.as_dict() for pattern in EngineeringPatternLibrary(_org_storage(settings)).search(q)]
        audit.record(
            action="organization_patterns_search_read", path="organization/patterns/search",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(patterns)} result(s)",
        )
        return {"query": q, "patterns": patterns, "readOnly": True}

    @app.post("/organization/pattern/create", status_code=status.HTTP_202_ACCEPTED, tags=["organization"])
    def organization_pattern_create(
        body: OrganizationPatternCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_pattern_create", project=body.project, path="organization/patterns",
            payload={"category": body.category, "name": body.name, "summary": body.summary,
                     "project": body.project, "tags": body.tags},
            reason=body.reason,
            preview_factory=lambda: f"RECORD enterprise pattern '{body.name}' ({body.category}); no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/organization/learning/similar", tags=["organization"])
    def organization_learning_similar(
        project: str = Query(..., min_length=1, max_length=100),
        signature: str | None = Query(default=None, max_length=1000),
        category: str | None = Query(default=None, max_length=32),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> dict[str, Any]:
        storage = _org_storage(settings)
        library = [pattern.as_dict() for pattern in storage.list_failure_patterns()]
        patterns: list[dict[str, Any]] = []
        if signature:
            patterns.append({"project": project, "category": category or "", "signature": signature})
        else:
            loops = [loop.as_dict() for loop in ExecutionLoopStorage(settings.execution_loop_db_path).list_loops(project=project)]
            results = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager).list_results(project=project)
            patterns = [pattern.as_dict() for pattern in FailureIntelligenceAnalyzer().analyze(project, loops=loops, results=[r.as_dict() for r in results])]
        matches = CrossProjectLearner().analyze(project, patterns, library)
        audit.record(
            action="organization_learning_read", path=f"organization/learning/{project}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(matches)} similar failure match(es)",
        )
        return {"project": project, "matches": [match.as_dict() for match in matches], "readOnly": True}

    @app.post("/organization/learning/scan", status_code=status.HTTP_202_ACCEPTED, tags=["organization"])
    def organization_learning_scan(
        body: OrganizationLearningScanRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_learning_scan", project=body.project, path="organization/learning",
            payload={"project": body.project}, reason=body.reason,
            preview_factory=lambda: f"SCAN failure patterns for project '{body.project}' and compare against the org library; no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/organization/health", tags=["organization"])
    def organization_health(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> dict[str, Any]:
        from app.workspace.manager import WorkspaceManager

        storage = _org_storage(settings)
        governance = GovernanceStorage(settings.governance_db_path)
        projects = [entry["name"] for entry in WorkspaceManager(settings).list_projects()]
        computed = [_compute_project_health(settings, audit, approvals, workflow_manager, storage, project) for project in projects]
        project_healths = [report for report, _failures in computed]
        failures = [pattern for _report, pattern_list in computed for pattern in pattern_list]
        debt_summaries = [
            {
                "project": project,
                "openDebt": sum(1 for item in governance.list_debt(project) if item.status.value == "OPEN"),
                "estimatedCost": sum(int(item.estimated_cost) for item in governance.list_debt(project)),
            }
            for project in projects
        ]
        history = {project: storage.list_health(project, limit=2) for project in projects}
        incidents = [incident.as_dict() for incident in storage.list_incidents()]
        patterns = [pattern.as_dict() for pattern in storage.list_patterns()]
        agent_metrics = [record.as_dict() for record in MetricsManager(settings.agent_root, audit).list()]
        report = OrganizationHealthAggregator().evaluate(
            "organization", project_healths,
            debt_summaries=debt_summaries, agent_metrics=agent_metrics,
            incidents=incidents, patterns=patterns, history=history,
        )
        audit.record(
            action="organization_health_read", path="organization/health",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"score={report.org_health_score} projects={report.project_count}",
        )
        return report.as_dict()

    @app.get("/organization/dashboard", tags=["organization"])
    def organization_dashboard(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        storage = _org_storage(settings)
        graph = OrganizationGraphManager(storage).get_graph()
        audit.record(
            action="organization_dashboard_read", path="organization/dashboard",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
        )
        return {
            "graph": graph.as_dict(),
            "patterns": [pattern.as_dict() for pattern in storage.list_patterns()],
            "incidents": [incident.as_dict() for incident in storage.list_incidents()],
            "decisions": [decision.as_dict() for decision in storage.list_decisions()],
            "categories": sorted({category.value for category in PatternCategory}),
            "readOnly": True,
        }

    @app.get("/quality/v10/{org}", tags=["quality"])
    def quality_gate_v10(
        org: str,
        org_health_score: int = Query(default=100, ge=0, le=100),
        project_count: int = Query(default=1, ge=0, le=1000),
        open_incidents: int = Query(default=0, ge=0, le=1000),
        critical_projects: int = Query(default=0, ge=0, le=1000),
        strategy_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
        architecture_risk: int | None = Query(default=None, ge=0, le=100),
        technical_debt: int | None = Query(default=None, ge=0, le=100),
        cross_project_impact: int | None = Query(default=None, ge=0, le=100),
        risk_propagation: int | None = Query(default=None, ge=0, le=100),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = QualityGate10Evaluator().evaluate(
            org=org, org_health_score=org_health_score, project_count=project_count,
            open_incidents=open_incidents, critical_projects=critical_projects,
            strategy_confidence=strategy_confidence, architecture_risk=architecture_risk,
            technical_debt=technical_debt, cross_project_impact=cross_project_impact,
            risk_propagation=risk_propagation,
        )
        audit.record(
            action="quality_gate_v10_read", path=f"quality/v10/{org}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"quality={report['quality']}",
        )
        return report
