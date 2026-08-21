"""Phase 24 organization engineering strategy API routes.

Read-only endpoints (impact, risk, strategies, strategy detail, decisions,
simulations, recommendations, org context) plus approval-gated writes
(strategy create / evaluate, strategy decision create / transition, org
memory append). No route here can execute actions or modify source code.

Note: POST /organization/decision/create is already owned by Phase 22
(record-only org architecture decisions). To keep Phase 22 behavior intact,
Phase 24 decision writes use /organization/strategy/decision/*.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.models.request import (
    OrganizationStrategyCreateRequest,
    OrganizationStrategyDecisionCreateRequest,
    OrganizationStrategyDecisionTransitionRequest,
    OrganizationStrategyEvaluateRequest,
    OrganizationStrategyMemoryAppendRequest,
)
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store

from .manager import OrganizationStrategyManager


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _manager(settings: Settings) -> OrganizationStrategyManager:
    return OrganizationStrategyManager(settings, get_audit_logger())


def register_organization_strategy_routes(app: Any) -> None:
    """Attach all Phase 24 organization strategy routes to the FastAPI app."""

    @app.get("/organization/impact/{node_id}", tags=["organization-strategy"])
    def organization_impact(
        node_id: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = _manager(settings).impact(node_id)
        audit.record(
            action="organization_impact_read", path=f"organization/impact/{node_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"impactScore={report['impact_score']} projects={len(report['affected_projects'])}",
        )
        return report

    @app.get("/organization/risk/{node_id}", tags=["organization-strategy"])
    def organization_risk(
        node_id: str,
        severity: str = Query(default="medium", max_length=16),
        likelihood: str = Query(default="medium", max_length=16),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = _manager(settings).risk(node_id, severity=severity, likelihood=likelihood)
        audit.record(
            action="organization_risk_read", path=f"organization/risk/{node_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"impact={report['impact']} affected={len(report['affected_nodes'])}",
        )
        return report

    @app.get("/organization/strategies/{project}", tags=["organization-strategy"])
    def organization_strategies(
        project: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        manager = _manager(settings)
        persisted = manager.strategies(project)
        # Candidate generation is deterministic and read-only; generated
        # candidates are included alongside persisted strategies.
        generated = [
            strategy.as_dict()
            for strategy in manager.generate_candidates()
            if not project or project in strategy.affected_projects
        ]
        seen = {strategy["strategy_id"] for strategy in persisted}
        merged = persisted + [strategy for strategy in generated if strategy["strategy_id"] not in seen]
        audit.record(
            action="organization_strategies_read", path=f"organization/strategies/{project}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(merged)} strategy candidate(s)",
        )
        return {"project": project, "strategies": merged, "readOnly": True}

    @app.get("/organization/strategy/{strategy_id}", tags=["organization-strategy"])
    def organization_strategy_detail(
        strategy_id: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        strategy = _manager(settings).strategy(strategy_id)
        audit.record(
            action="organization_strategy_read", path=f"organization/strategy/{strategy_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"type={strategy['strategy_type']} status={strategy['status']}",
        )
        return strategy

    @app.get("/organization/decision/{decision_id}", tags=["organization-strategy"])
    def organization_decision_detail(
        decision_id: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        decision = _manager(settings).decision(decision_id)
        audit.record(
            action="organization_decision_read", path=f"organization/decision/{decision_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"status={decision['status']}",
        )
        return decision

    @app.get("/organization/simulation/{simulation_id}", tags=["organization-strategy"])
    def organization_simulation_detail(
        simulation_id: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        simulation = _manager(settings).simulation(simulation_id)
        audit.record(
            action="organization_simulation_read", path=f"organization/simulation/{simulation_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"strategy={simulation['strategy_id']}",
        )
        return simulation

    @app.get("/organization/recommendations", tags=["organization-strategy"])
    def organization_recommendations(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        manager = _manager(settings)
        recommendations = manager.build_recommendations()
        for recommendation in recommendations:
            manager.storage.save_recommendation(recommendation)
        audit.record(
            action="organization_recommendations_read", path="organization/recommendations",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(recommendations)} recommendation(s)",
        )
        return {"recommendations": [item.as_dict() for item in recommendations], "readOnly": True}

    @app.get("/organization/context", tags=["organization-strategy"])
    def organization_context(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        context = _manager(settings).org_context()
        audit.record(
            action="organization_context_read", path="organization/context",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(context['active_strategies'])} strategy(ies), {len(context['pending_decisions'])} pending decision(s)",
        )
        return context

    # ------------------------------------------------------------------ #
    # Approval-gated writes
    # ------------------------------------------------------------------ #

    @app.post("/organization/strategy/create", status_code=status.HTTP_202_ACCEPTED, tags=["organization-strategy"])
    def organization_strategy_create(
        body: OrganizationStrategyCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_strategy_create", project="organization", path="organization/strategies",
            payload={
                "strategy_type": body.strategy_type, "title": body.title, "problem": body.problem,
                "affected_projects": body.affected_projects, "affected_teams": body.affected_teams,
                "benefits": body.benefits, "risks": body.risks,
                "estimated_effort": body.estimated_effort, "confidence": body.confidence,
                "priority": body.priority, "alternatives": body.alternatives, "evidence": body.evidence,
            },
            reason=body.reason,
            preview_factory=lambda: f"CREATE strategy proposal '{body.title}' ({body.strategy_type}); no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/organization/strategy/evaluate", status_code=status.HTTP_202_ACCEPTED, tags=["organization-strategy"])
    def organization_strategy_evaluate(
        body: OrganizationStrategyEvaluateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_strategy_evaluate", project="organization", path="organization/strategies",
            payload={"strategy_ids": body.strategy_ids},
            reason=body.reason,
            preview_factory=lambda: f"EVALUATE {len(body.strategy_ids)} strategy candidate(s) and simulate them; no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/organization/strategy/decision/create", status_code=status.HTTP_202_ACCEPTED, tags=["organization-strategy"])
    def organization_strategy_decision_create(
        body: OrganizationStrategyDecisionCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_strategy_decision_create", project="organization", path="organization/decisions",
            payload={
                "organization_id": body.organization_id, "title": body.title, "strategy_id": body.strategy_id,
                "source_graph_nodes": body.source_graph_nodes, "alternatives": body.alternatives,
                "confidence": body.confidence, "impact_report": body.impact_report, "risk_report": body.risk_report,
            },
            reason=body.reason,
            preview_factory=lambda: f"CREATE organization decision '{body.title}' selecting strategy {body.strategy_id}; no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/organization/strategy/decision/transition", status_code=status.HTTP_202_ACCEPTED, tags=["organization-strategy"])
    def organization_strategy_decision_transition(
        body: OrganizationStrategyDecisionTransitionRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_strategy_decision_transition", project="organization", path="organization/decisions",
            payload={"decision_id": body.decision_id, "status": body.status},
            reason=body.reason,
            preview_factory=lambda: f"TRANSITION decision {body.decision_id} -> {body.status.upper()}; no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/organization/memory/append", status_code=status.HTTP_202_ACCEPTED, tags=["organization-strategy"])
    def organization_memory_append(
        body: OrganizationStrategyMemoryAppendRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        manager = _manager(settings)
        preview = manager.memory.preview(body.organization, body.category, body.content)
        return _register_pending(
            action="organization_memory_append", project=body.organization, path="memory/organization",
            payload={"organization": body.organization, "category": body.category, "content": body.content},
            reason=body.reason, preview_factory=lambda: preview,
            settings=settings, audit=audit, approvals=approvals,
        )
