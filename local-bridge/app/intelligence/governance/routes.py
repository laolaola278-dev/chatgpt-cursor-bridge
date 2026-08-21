"""Phase 28 · Engineering Intelligence Governance API.

All GET endpoints are project-scoped and read-only. The two persistent POST
endpoints (governance evaluate, governance review) only enqueue an
ApprovalStore request; nothing is written before human approval. There is
intentionally no POST /intelligence/governance/execute, /apply, /auto-fix,
or /auto-approve, and no endpoint can mutate a governance policy.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.intelligence.common import ensure_project
from app.intelligence.governance import (
    GovernanceGraphBuilder,
    GovernanceStore,
    GovernanceTrendAnalyzer,
    IntelligenceRiskAnalyzer,
    list_policies,
)
from app.intelligence.governance.models import (
    GovernanceKind,
    GovernanceResult,
    RISK_LEVELS,
    RiskLevel,
    ReviewStatus,
)
from app.intelligence.governance.rules import GovernanceRuleEngine
from app.intelligence.validation import ValidationStore
from app.models.request import IntelligenceGovernanceEvaluateRequest, IntelligenceGovernanceReviewRequest
from app.quality.gate14 import QualityGate14Evaluator
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.validator import ResourceNotFound, ValidationFailed


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _governance_store(settings: Settings) -> GovernanceStore:
    return GovernanceStore(settings.intelligence_db_path)


def _validation_store(settings: Settings) -> ValidationStore:
    return ValidationStore(settings.intelligence_db_path)


def _kind(value: str) -> str:
    kind = str(value).lower().strip()
    if kind not in {item.value for item in GovernanceKind}:
        raise ValidationFailed(f"Unknown governance source kind: {value}")
    return kind


def _risk(value: str) -> str:
    risk = str(value).upper().strip()
    if risk not in RISK_LEVELS:
        raise ValidationFailed(f"Unknown risk level: {value}")
    return risk


def _derive_metrics(settings: Settings, project: str, model_id: str) -> dict[str, Any]:
    """Derive accuracy / failure / rejection / reliability from stored records.

    The governance evaluation never trusts caller-supplied rates; metrics are
    recomputed deterministically from the historical stores.
    """
    validation = _validation_store(settings)
    evaluations = validation.evaluations(project, model_id=model_id or None, limit=5000)
    counted = [item for item in evaluations if item.counted]
    accuracy = round(sum(1 for item in counted if item.correct) / len(counted), 3) if counted else None
    failure_rate = round(1 - accuracy, 3) if accuracy is not None else None
    effectiveness = validation.effectiveness(project, limit=5000)
    rejection_rate = (
        round(sum(1 for item in effectiveness if item.user_decision == "rejected") / len(effectiveness), 3)
        if effectiveness
        else None
    )
    benchmarks = validation.benchmarks(project, model_id=model_id or None, limit=200)
    model_reliability = max((item.score for item in benchmarks), default=None)
    regression_rate = failure_rate  # measured regression equals the failure share of counted outcomes
    return {
        "accuracy": accuracy,
        "failure_rate": failure_rate,
        "rejection_rate": rejection_rate,
        "model_reliability": model_reliability,
        "regression_rate": regression_rate,
    }


def register_intelligence_governance_routes(app: Any) -> None:
    @app.post("/intelligence/governance/evaluate", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase28"])
    def intelligence_governance_evaluate(
        body: IntelligenceGovernanceEvaluateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        project = ensure_project(body.project_id)
        _kind(body.source_kind)
        _risk(body.risk_level)
        metrics = _derive_metrics(settings, project, body.model_id)
        payload = body.model_dump(exclude={"reason"})
        payload["metrics"] = metrics

        def preview() -> str:
            result = GovernanceRuleEngine().evaluate(
                project=project,
                source_kind=body.source_kind,
                source_id=body.source_id,
                confidence=body.confidence,
                risk_level=body.risk_level,
                risk_score=body.risk_score,
                accuracy=metrics["accuracy"],
                failure_rate=metrics["failure_rate"],
                regression_rate=metrics["regression_rate"],
                rejection_rate=metrics["rejection_rate"],
                model_reliability=metrics["model_reliability"],
                context=body.context,
            )
            return f"EVALUATE governance for {body.source_kind} {body.source_id}: result={result.governance_result} risk={body.risk_level}; measurement + review proposal only"

        return _register_pending(
            action="intelligence_governance_evaluate",
            project=project,
            path="intelligence/governance/evaluate",
            payload=payload,
            reason=body.reason,
            preview_factory=preview,
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/governance/risk", tags=["intelligence-phase28"])
    def intelligence_governance_risk(
        project: str = Query(..., min_length=1, max_length=100),
        risk_level: str | None = Query(default=None, max_length=16),
        source_kind: str | None = Query(default=None, max_length=32),
        agent_id: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        findings = _governance_store(settings).risks(
            project, risk_level=risk_level, source_kind=source_kind, agent_id=agent_id, limit=limit
        )
        audit.record(action="intelligence_governance_risk_read", path=f"{project}:governance/risk", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(findings)} finding(s)")
        return {"project": project, "risks": [item.as_dict() for item in findings], "readOnly": True}

    @app.get("/intelligence/governance/trends", tags=["intelligence-phase28"])
    def intelligence_governance_trends(
        project: str = Query(..., min_length=1, max_length=100),
        period: str = Query(default="weekly", max_length=16),
        agent_id: str | None = Query(default=None, max_length=200),
        model_id: str | None = Query(default=None, max_length=200),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        analyzer = GovernanceTrendAnalyzer(_validation_store(settings))
        records = _governance_store(settings).records(project, agent_id=agent_id, model_id=model_id, limit=2000)
        trends = analyzer.overall(project, period=period, agent_id=agent_id, model_id=model_id, governance_records=records)
        signals = analyzer.detected(trends)
        audit.record(action="intelligence_governance_trends_read", path=f"{project}:governance/trends", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(trends)} trend(s)")
        return {"project": project, "trends": [item.as_dict() for item in trends], "signals": signals, "readOnly": True}

    @app.get("/intelligence/governance/policies", tags=["intelligence-phase28"])
    def intelligence_governance_policies(
        project: str = Query(..., min_length=1, max_length=100),
        scope: str | None = Query(default=None, max_length=32),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        policies = list_policies(scope=scope)
        audit.record(action="intelligence_governance_policies_read", path=f"{project}:governance/policies", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(policies)} policy(ies)")
        return {"project": project, "policies": [item.as_dict() for item in policies], "readOnly": True}

    @app.get("/intelligence/governance/violations", tags=["intelligence-phase28"])
    def intelligence_governance_violations(
        project: str = Query(..., min_length=1, max_length=100),
        severity: str | None = Query(default=None, max_length=16),
        policy_id: str | None = Query(default=None, max_length=100),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        violations = _governance_store(settings).violations(project, severity=severity, policy_id=policy_id, limit=limit)
        audit.record(action="intelligence_governance_violations_read", path=f"{project}:governance/violations", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(violations)} violation(s)")
        return {"project": project, "violations": [item.as_dict() for item in violations], "readOnly": True}

    @app.get("/intelligence/governance/reviews", tags=["intelligence-phase28"])
    def intelligence_governance_reviews(
        project: str = Query(..., min_length=1, max_length=100),
        status: str | None = Query(default=None, max_length=32),
        risk_level: str | None = Query(default=None, max_length=16),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        proposals = _governance_store(settings).proposals(project, status=status, risk_level=risk_level, limit=limit)
        audit.record(action="intelligence_governance_reviews_read", path=f"{project}:governance/reviews", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(proposals)} proposal(s)")
        return {"project": project, "reviews": [item.as_dict() for item in proposals], "readOnly": True}

    @app.post("/intelligence/governance/review", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase28"])
    def intelligence_governance_review(
        body: IntelligenceGovernanceReviewRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        project = ensure_project(body.project_id)
        decision = str(body.decision).lower().strip()
        if decision not in (ReviewStatus.APPROVED.value, ReviewStatus.REJECTED.value):
            raise ValidationFailed(f"Unknown review decision: {body.decision}")

        def preview() -> str:
            return f"RECORD human review for governance proposal {body.proposal_id}: decision={decision}; governance memory append only"

        return _register_pending(
            action="intelligence_governance_review",
            project=project,
            path="intelligence/governance/review",
            payload=body.model_dump(exclude={"reason"}),
            reason=body.reason,
            preview_factory=preview,
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/governance/quality-gate", tags=["intelligence-phase28"])
    def intelligence_governance_quality_gate(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        from app.intelligence.phase28 import build_phase28_snapshot

        project = ensure_project(project)
        snapshot = build_phase28_snapshot(settings, project)
        audit.record(action="intelligence_governance_quality_gate_read", path=f"{project}:governance/quality-gate", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"status={snapshot.quality14['status']}")
        return {"project": project, **snapshot.quality14}

    @app.get("/intelligence/governance/graph", tags=["intelligence-phase28"])
    def intelligence_governance_graph(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=1000, ge=1, le=5000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        validation = _validation_store(settings)
        governance = _governance_store(settings)
        graph = GovernanceGraphBuilder().build(
            project=project,
            evaluations=validation.evaluations(project, limit=limit),
            effectiveness=validation.effectiveness(project, limit=limit),
            decision_outcomes=validation.decision_outcomes(project, limit=limit),
            risks=governance.risks(project, limit=limit),
            governance_records=governance.records(project, limit=limit),
        )
        audit.record(action="intelligence_governance_graph_read", path=f"{project}:governance/graph", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{graph['nodeCount']} node(s)")
        return graph

    @app.get("/intelligence/governance", tags=["intelligence-phase28"])
    def intelligence_governance_snapshot(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=1000, ge=1, le=5000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        from app.intelligence.phase28 import build_phase28_snapshot

        project = ensure_project(project)
        snapshot = build_phase28_snapshot(settings, project, limit=limit)
        audit.record(action="intelligence_governance_read", path=f"{project}:governance", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(snapshot.records)} record(s)")
        return snapshot.as_dict()

    @app.get("/intelligence/governance/{governance_id}", tags=["intelligence-phase28"])
    def intelligence_governance_detail(
        governance_id: str,
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        record = _governance_store(settings).get_record(governance_id, ensure_project(project))
        if record is None:
            raise ResourceNotFound(f"Governance record '{governance_id}' was not found for this project")
        audit.record(action="intelligence_governance_detail_read", path=f"{project}:governance/{governance_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return record.as_dict()

    @app.get("/quality/v14/{project}", tags=["quality"])
    def quality_gate_v14(
        project: str,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        from app.intelligence.phase28 import build_phase28_snapshot

        project = ensure_project(project)
        snapshot = build_phase28_snapshot(settings, project)
        audit.record(action="quality_gate_v14_read", path=f"quality/v14/{project}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"status={snapshot.quality14['status']}")
        return {"project": project, **snapshot.quality14}
