"""Phase 27 · Engineering Intelligence Validation API.

All GET endpoints are project-scoped and read-only. The three persistent POST
endpoints (evaluation record, benchmark run, knowledge improvement proposal)
only enqueue an ApprovalStore request; nothing is written before human
approval. There is intentionally no POST /intelligence/execute,
/apply, or /auto-fix.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.intelligence.common import ensure_project
from app.intelligence.validation import (
    AccuracySystem,
    DecisionOutcomeIntelligence,
    KnowledgeImprovementEngine,
    RecommendationEffectivenessEngine,
    ValidationStore,
    builtin_datasets,
    find_builtin_dataset,
)
from app.intelligence.validation.models import EvaluationKind, EvaluationRecord, EvaluationResult
from app.models.request import (
    IntelligenceBenchmarkRunRequest,
    IntelligenceEvaluationRecordRequest,
    IntelligenceKnowledgeImprovementRequest,
)
from app.quality.gate13 import QualityGate13Evaluator
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.validator import ResourceNotFound, ValidationFailed


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _store(settings: Settings) -> ValidationStore:
    return ValidationStore(settings.intelligence_db_path)


def _evaluation_kind(value: str) -> str:
    kind = str(value).lower().strip()
    if kind not in {item.value for item in EvaluationKind}:
        raise ValidationFailed(f"Unknown evaluation kind: {value}")
    return kind


def _evaluation_result(value: str) -> str:
    result = str(value).lower().strip()
    if result not in {item.value for item in EvaluationResult}:
        raise ValidationFailed(f"Unknown evaluation result: {value}")
    return result


def register_intelligence_validation_routes(app: Any) -> None:
    @app.post("/intelligence/evaluation", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase27"])
    def intelligence_evaluation_record(
        body: IntelligenceEvaluationRecordRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        # Build and validate the record up front; it is persisted only after
        # the queued request is approved.
        record = EvaluationRecord(
            evaluation_id="",
            project_id=body.project_id,
            prediction_id=body.prediction_id,
            evaluation_kind=_evaluation_kind(body.evaluation_kind),
            input_context=body.input_context,
            prediction_result=body.prediction_result,
            expected_outcome=body.expected_outcome,
            actual_outcome=body.actual_outcome,
            evaluation_result=_evaluation_result(body.evaluation_result),
            confidence=body.confidence,
            agent_id=body.agent_id or "",
            model_id=body.model_id or "",
            decision_id=body.decision_id,
            recommendation_id=body.recommendation_id,
            evidence=body.evidence,
        )
        return _register_pending(
            action="intelligence_evaluation_record",
            project=body.project_id,
            path="intelligence/evaluation",
            payload={"evaluation": record.as_dict()},
            reason=body.reason,
            preview_factory=lambda: f"RECORD {record.evaluation_kind} evaluation for prediction {record.prediction_id}; result={record.evaluation_result} confidence={record.confidence}; measurement only",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/evaluation/{evaluation_id}", tags=["intelligence-phase27"])
    def intelligence_evaluation_detail(
        evaluation_id: str,
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        record = _store(settings).get_evaluation(evaluation_id, ensure_project(project))
        if record is None:
            raise ResourceNotFound(f"Evaluation '{evaluation_id}' was not found for this project")
        audit.record(action="intelligence_evaluation_read", path=f"{project}:evaluation/{evaluation_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return record.as_dict()

    @app.get("/intelligence/accuracy", tags=["intelligence-phase27"])
    def intelligence_accuracy(
        project: str = Query(..., min_length=1, max_length=100),
        agent_id: str | None = Query(default=None, max_length=200),
        model_id: str | None = Query(default=None, max_length=200),
        kind: str | None = Query(default=None, max_length=40),
        since: str | None = Query(default=None, max_length=40),
        until: str | None = Query(default=None, max_length=40),
        limit: int = Query(default=5000, ge=1, le=10000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = _store(settings).evaluations(project, kind=kind, agent_id=agent_id, model_id=model_id, limit=limit)
        report = AccuracySystem().report(project, records, agent_id=agent_id, model_id=model_id, kind=kind, since=since, until=until)
        audit.record(action="intelligence_accuracy_read", path=f"{project}:accuracy", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"counted={report.counted} accuracy={report.accuracy}")
        return report.as_dict()

    @app.get("/intelligence/evaluations/phase27", tags=["intelligence-phase27"])
    def intelligence_evaluations_phase27(
        project: str = Query(..., min_length=1, max_length=100),
        kind: str | None = Query(default=None, max_length=40),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = _store(settings).evaluations(project, kind=kind, limit=limit)
        audit.record(action="intelligence_evaluations_read", path=f"{project}:evaluations/phase27", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} evaluation(s)")
        return {"project": project, "evaluations": [item.as_dict() for item in records], "readOnly": True}

    @app.get("/intelligence/effectiveness", tags=["intelligence-phase27"])
    def intelligence_effectiveness(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = _store(settings).effectiveness(project, limit=limit)
        summary = RecommendationEffectivenessEngine.summary(project, records)
        audit.record(action="intelligence_effectiveness_read", path=f"{project}:effectiveness", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} record(s)")
        return {"project": project, "effectiveness": [item.as_dict() for item in records], "summary": summary, "readOnly": True}

    @app.get("/intelligence/decision-outcomes", tags=["intelligence-phase27"])
    def intelligence_decision_outcomes(
        project: str = Query(..., min_length=1, max_length=100),
        decision_type: str | None = Query(default=None, max_length=40),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = _store(settings).decision_outcomes(project, decision_type=decision_type, limit=limit)
        summary = DecisionOutcomeIntelligence.summary(project, records)
        audit.record(action="intelligence_decision_outcomes_read", path=f"{project}:decision-outcomes", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} record(s)")
        return {"project": project, "decisionOutcomes": [item.as_dict() for item in records], "summary": summary.as_dict(), "readOnly": True}

    @app.post("/intelligence/benchmark/run", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase27"])
    def intelligence_benchmark_run(
        body: IntelligenceBenchmarkRunRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        dataset = find_builtin_dataset(body.dataset_id, body.project_id)
        if dataset is None:
            raise ValidationFailed(f"Unknown benchmark dataset: {body.dataset_id}")
        return _register_pending(
            action="intelligence_benchmark_run",
            project=body.project_id,
            path="intelligence/benchmark",
            payload=body.model_dump(exclude={"reason"}),
            reason=body.reason,
            preview_factory=lambda: f"RUN deterministic benchmark {dataset.name} ({len(dataset.cases)} cases) for model {body.model_id}; results are measurement only",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/benchmarks", tags=["intelligence-phase27"])
    def intelligence_benchmarks(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        runs = _store(settings).benchmarks(project, limit=limit)
        audit.record(action="intelligence_benchmarks_read", path=f"{project}:benchmarks", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(runs)} run(s)")
        return {"project": project, "benchmarks": [item.as_dict() for item in runs], "datasets": [item.as_dict() for item in builtin_datasets(project)], "readOnly": True}

    @app.get("/intelligence/benchmark/{benchmark_id}", tags=["intelligence-phase27"])
    def intelligence_benchmark_detail(
        benchmark_id: str,
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        run = _store(settings).get_benchmark(benchmark_id, ensure_project(project))
        if run is None:
            raise ResourceNotFound(f"Benchmark '{benchmark_id}' was not found for this project")
        audit.record(action="intelligence_benchmark_read", path=f"{project}:benchmark/{benchmark_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"score={run.score}")
        return run.as_dict()

    @app.post("/intelligence/knowledge/improvements/propose", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase27"])
    def intelligence_knowledge_improvements(
        body: IntelligenceKnowledgeImprovementRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        proposal = KnowledgeImprovementEngine().build_proposal(
            project_id=body.project_id,
            evaluation_id=body.evaluation_id,
            prediction_id=body.prediction_id,
            category=body.category,
            content=body.content,
            source=body.source,
            evidence=body.evidence,
            confidence=body.confidence,
            reason=body.reason,
        )
        return _register_pending(
            action="intelligence_knowledge_improvement",
            project=body.project_id,
            path="intelligence/knowledge/improvements",
            payload=proposal.payload(),
            reason=body.reason,
            preview_factory=proposal.preview,
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/knowledge/improvements", tags=["intelligence-phase27"])
    def intelligence_knowledge_improvements_list(
        project: str = Query(..., min_length=1, max_length=100),
        status: str | None = Query(default=None, max_length=32),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = KnowledgeImprovementEngine.list_improvements(_store(settings).improvements(project, limit=limit), project, status=status, limit=limit)
        # Merge pending/rejected proposals from the ApprovalStore so the
        # dashboard shows the full human-in-the-loop picture.
        proposals: list[dict[str, Any]] = []
        for request in approvals.list_all():
            if request.action != "intelligence_knowledge_improvement" or request.project != project:
                continue
            # Executed requests are already represented by the validated record
            # stored after approval; including them would double count.
            if request.status.value == "executed":
                continue
            payload = request.payload
            proposals.append({
                "improvement_id": request.request_id,
                "improvementId": request.request_id,
                "project_id": project, "projectId": project,
                "evaluation_id": payload.get("evaluation_id", ""), "evaluationId": payload.get("evaluation_id", ""),
                "prediction_id": payload.get("prediction_id", ""), "predictionId": payload.get("prediction_id", ""),
                "category": payload.get("category", ""), "content": payload.get("content", ""),
                "source": payload.get("source", ""), "evidence": payload.get("evidence", []),
                "confidence": payload.get("confidence", 0.0),
                "status": request.status.value, "created_at": request.created_at, "createdAt": request.created_at,
                "approval_request_id": request.request_id, "approvalRequestId": request.request_id,
                "readOnly": True,
            })
        merged = records + proposals
        merged.sort(key=lambda item: str(item.get("created_at", item.get("createdAt", ""))), reverse=True)
        if status:
            merged = [item for item in merged if item.get("status") == status]
        audit.record(action="intelligence_knowledge_improvements_read", path=f"{project}:knowledge/improvements", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(merged)} record(s)")
        return {"project": project, "improvements": merged[: max(1, min(int(limit), 2000))], "readOnly": True}

    @app.get("/intelligence/validation", tags=["intelligence-phase27"])
    def intelligence_validation_snapshot(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=1000, ge=1, le=5000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        from app.intelligence.phase27 import build_phase27_snapshot

        project = ensure_project(project)
        snapshot = build_phase27_snapshot(settings, project, limit=limit)
        audit.record(action="intelligence_validation_read", path=f"{project}:validation", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(snapshot.evaluations)} evaluation(s)")
        return snapshot.as_dict()

    @app.get("/quality/v13/{project}", tags=["quality"])
    def quality_gate_v13(project: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        project = ensure_project(project)
        store = _store(settings)
        evaluations = store.evaluations(project, limit=2000)
        effectiveness = store.effectiveness(project, limit=2000)
        benchmarks = store.benchmarks(project, limit=200)
        improvements = store.improvements(project, limit=1000)
        accuracy = AccuracySystem().report(project, evaluations)
        report = QualityGate13Evaluator().evaluate(
            prediction_traceable=all(item.prediction_id for item in evaluations),
            prediction_count=len({item.prediction_id for item in evaluations}),
            evaluation_traceable=all(item.prediction_id and item.evaluation_result for item in evaluations),
            evaluation_count=len(evaluations),
            outcome_traceable=all(item.expected_outcome and item.actual_outcome for item in evaluations),
            outcome_count=len(evaluations),
            accuracy_computable=accuracy.counted > 0,
            accuracy_count=accuracy.counted,
            recommendation_effectiveness_computable=len(effectiveness) > 0,
            effectiveness_count=len(effectiveness),
            benchmark_runnable=len(builtin_datasets(project)) > 0,
            benchmark_count=len(benchmarks),
            knowledge_improvement_audited=True,
            improvement_count=len(improvements),
            no_auto_knowledge_write=True,
            no_permission_bypass=True,
        )
        audit.record(action="quality_gate_v13_read", path=f"quality/v13/{project}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"status={report['status']}")
        return {"project": project, **report}
