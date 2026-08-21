"""Phase 21 governance API routes.

Read-only governance endpoints (health, drift, debt, policies, timeline) plus
approval-gated writes (debt create/transition, policy evaluate, timeline
memory append) and Quality Gate 9.0. No route here can execute actions or
modify source code; every write is routed through the ApprovalStore.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.code_intelligence import CodeIndex
from app.config import Settings, get_settings
from app.engineering_graph import EngineeringGraphStorage
from app.execution import ExecutionManager, ExecutionStorage
from app.execution_loop import ExecutionLoopStorage
from app.failure_intelligence import FailureIntelligenceAnalyzer
from app.governance import (
    ArchitectureDriftDetector,
    DebtManager,
    EngineeringHealthManager,
    GovernanceStorage,
    PolicyEngine,
)
from app.intelligence import IntelligenceStorage
from app.memory.governance import GovernanceMemory
from app.metrics import MetricsManager
from app.models.request import (
    GovernanceDebtCreateRequest,
    GovernanceDebtTransitionRequest,
    GovernancePolicyEvaluateRequest,
    GovernanceTimelineAppendRequest,
)
from app.quality.gate9 import QualityGate9Evaluator
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.validator import ResourceNotFound
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


def _governance_storage(settings: Settings) -> GovernanceStorage:
    return GovernanceStorage(settings.governance_db_path)


def register_governance_routes(app: Any) -> None:
    """Attach all Phase 21 governance routes to the FastAPI app."""

    @app.get("/governance/health/{project}", tags=["governance"])
    def governance_health(
        project: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> dict[str, Any]:
        storage = _governance_storage(settings)
        loops = [loop.as_dict() for loop in ExecutionLoopStorage(settings.execution_loop_db_path).list_loops(project=project)]
        execution = ExecutionManager(
            ExecutionStorage(settings.execution_db_path), settings,
            approvals=approvals, workflow_manager=workflow_manager,
        )
        results = [result.as_dict() for result in execution.list_results(project=project)]
        failures = [pattern.as_dict() for pattern in FailureIntelligenceAnalyzer().analyze(project, loops=loops, results=results)]
        agent_records = [record.as_dict() if hasattr(record, "as_dict") else record for record in MetricsManager(settings.agent_root, audit).list()]
        history = storage.list_health(project, limit=1)
        report = EngineeringHealthManager().evaluate(
            project, loops=loops, results=results,
            failures=failures, agent_metrics=agent_records, history=history,
        )
        storage.record_health(project, report.as_dict())
        audit.record(
            action="governance_health_read", path=f"governance/health/{project}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"score={report.health_score} risk={report.risk_level}",
        )
        return report.as_dict()

    @app.get("/governance/drift/{project}", tags=["governance"])
    def governance_drift(
        project: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        storage = _governance_storage(settings)
        graph = EngineeringGraphStorage(
            settings.workspace_root.parent / "engineering_graph" / "engineering_graph.db"
        ).get_graph(project).as_dict()
        code_index = CodeIndex(settings.code_index_db_path)
        code_files = code_index.files(project)
        dependencies = code_index.dependencies(project)
        decisions = [decision.as_dict() for decision in IntelligenceStorage(settings.intelligence_db_path).list_decisions(project)]
        deprecated = [
            str(node.get("label", ""))
            for node in graph.get("nodes", [])
            if str(node.get("metadata", {}).get("deprecated", "")).lower() == "true"
            or str(node.get("metadata", {}).get("status", "")).lower() == "deprecated"
        ]
        report = ArchitectureDriftDetector().detect(
            project, graph=graph, code_files=code_files,
            dependencies=dependencies, decisions=decisions,
            deprecated_components=deprecated,
        )
        storage.record_drift(project, report.as_dict())
        audit.record(
            action="governance_drift_read", path=f"governance/drift/{project}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"drift={report.drift_score} issues={len(report.issues)}",
        )
        return report.as_dict()

    @app.get("/governance/debt/{project}", tags=["governance"])
    def governance_debt(
        project: str,
        debt_status: str | None = Query(default=None, alias="status", max_length=32),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        items = DebtManager(_governance_storage(settings)).list(project, status=debt_status)
        audit.record(
            action="governance_debt_read", path=f"governance/debt/{project}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(items)} item(s)",
        )
        return {"project": project, "debt": [item.as_dict() for item in items], "readOnly": True}

    @app.post("/governance/debt/create", status_code=status.HTTP_202_ACCEPTED, tags=["governance"])
    def governance_debt_create(
        body: GovernanceDebtCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="governance_debt_create", project=body.project, path=f"governance/debt/{body.project}",
            payload={
                "category": body.category, "severity": body.severity, "source": body.source,
                "affected_components": body.affected_components,
                "estimated_cost": body.estimated_cost, "risk": body.risk,
            },
            reason=body.reason,
            preview_factory=lambda: f"CREATE record-only debt item ({body.category}/{body.severity}); no code or memory write",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/governance/debt/{debt_id}/transition", status_code=status.HTTP_202_ACCEPTED, tags=["governance"])
    def governance_debt_transition(
        debt_id: str,
        body: GovernanceDebtTransitionRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        item = DebtManager(_governance_storage(settings)).get(debt_id)
        if item is None:
            raise ResourceNotFound(f"Debt item '{debt_id}' was not found")
        return _register_pending(
            action="governance_debt_transition", project=item.project, path=f"governance/debt/{debt_id}",
            payload={"debt_id": debt_id, "status": body.status}, reason=body.reason,
            preview_factory=lambda: f"UPDATE debt metadata {debt_id}: {item.status.value} -> {body.status.upper()} (metadata only)",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/governance/policies", tags=["governance"])
    def governance_policies(
        project: str | None = Query(default=None, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        engine = PolicyEngine()
        events = _governance_storage(settings).list_policy_events(project)
        audit.record(
            action="governance_policies_read", path="governance/policies",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(events)} event(s)",
        )
        return {"policies": engine.names(), "events": events, "readOnly": True}

    @app.post("/governance/policy/evaluate", status_code=status.HTTP_202_ACCEPTED, tags=["governance"])
    def governance_policy_evaluate(
        body: GovernancePolicyEvaluateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="governance_policy_evaluate", project=body.project, path="governance/policies",
            payload={"signal": body.signal}, reason=body.reason,
            preview_factory=lambda: f"EVALUATE {len(PolicyEngine().names())} policies against read-only governance signals; no execution impact",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/governance/timeline", tags=["governance"])
    def governance_timeline(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        storage = _governance_storage(settings)
        memory = GovernanceMemory(settings).history(project)
        audit.record(
            action="governance_timeline_read", path=f"governance/timeline/{project}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(memory)} memory document(s)",
        )
        return {
            "project": project,
            "healthSnapshots": storage.list_health(project, limit=5),
            "driftSnapshots": storage.list_drift(project, limit=5),
            "memory": memory,
            "readOnly": True,
        }

    @app.post("/governance/timeline/append", status_code=status.HTTP_202_ACCEPTED, tags=["governance"])
    def governance_timeline_append(
        body: GovernanceTimelineAppendRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        memory = GovernanceMemory(settings)
        return _register_pending(
            action="governance_memory_append", project=body.project, path=f"memory/governance/{body.category}",
            payload={"category": body.category, "content": body.content}, reason=body.reason,
            preview_factory=lambda: memory.preview(body.project, body.category, body.content),
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/quality/v9/{workflow_id}", tags=["quality"])
    def quality_gate_v9(
        workflow_id: str,
        health_score: int = Query(default=100, ge=0, le=100),
        architecture_risk: str = Query(default="low", max_length=16),
        debt_score: int = Query(default=0, ge=0, le=100),
        policy_violations: int = Query(default=0, ge=0, le=100),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = QualityGate9Evaluator().evaluate(
            health_score=health_score, architecture_risk=architecture_risk,
            debt_score=debt_score, policy_violations=policy_violations,
        )
        audit.record(
            action="quality_gate_v9_read", path=f"quality/v9/{workflow_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"quality={report['quality']}",
        )
        return {"workflowId": workflow_id, **report}
