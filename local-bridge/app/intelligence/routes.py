"""Phase 25 Engineering Intelligence Evolution API.

GET endpoints are project-scoped and read-only. The few endpoints that create
persistent observations, derived records, outcomes, evidence, or knowledge
proposals only enqueue an ApprovalStore request; no route executes or edits
source code directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.intelligence.common import ensure_project
from app.intelligence.evidence import EvidenceStore
from app.intelligence.observation import ObservationStore
from app.intelligence.outcome import OutcomeStore
from app.intelligence.pattern_intelligence import PatternIntelligence, PatternStore
from app.intelligence.recommendation import IntelligenceRecommendationEngine
from app.intelligence.risk_prediction import PredictionEngine, PredictionStore
from app.intelligence.phase26 import build_phase26_snapshot
from app.intelligence.trends import EngineeringTrendEngine
from app.intelligence.recommendation import RecommendationRanker, RecommendationRanking
from app.memory.intelligence import IntelligenceMemory
from app.models.request import (
    IntelligenceEvidenceBundleRequest,
    IntelligenceKnowledgeProposalRequest,
    IntelligenceObservationRecordRequest,
    IntelligenceOutcomeRecordRequest,
    IntelligencePatternAnalyzeRequest,
    IntelligencePredictionAnalyzeRequest,
)
from app.quality.gate11 import QualityGate11Evaluator
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.validator import ResourceNotFound


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _stores(settings: Settings, audit: AuditLogger | None = None) -> tuple[ObservationStore, PatternStore, PredictionStore, OutcomeStore, EvidenceStore]:
    path = settings.intelligence_db_path
    return ObservationStore(path, audit), PatternStore(path), PredictionStore(path), OutcomeStore(path), EvidenceStore(path)


def _observations(settings: Settings, project: str, limit: int) -> list[Any]:
    return _stores(settings)[0].list(project, limit=limit)


def _patterns(settings: Settings, project: str, limit: int) -> list[Any]:
    observations = _observations(settings, project, limit)
    stored = _stores(settings)[1].list(project, limit=limit)
    return stored or PatternIntelligence().detect(project, observations)


def _predictions(settings: Settings, project: str, limit: int) -> list[Any]:
    observations = _observations(settings, project, limit)
    stored = _stores(settings)[2].list(project, limit=limit)
    return stored or PredictionEngine().predict(project, _patterns(settings, project, limit), observations)


def _recommendations(settings: Settings, project: str, limit: int) -> list[Any]:
    return IntelligenceRecommendationEngine().generate(_predictions(settings, project, limit))[:limit]


def register_intelligence_evolution_routes(app: Any) -> None:
    @app.get("/intelligence/observations", tags=["intelligence-phase25"])
    def intelligence_observations(
        project: str = Query(..., alias="project", min_length=1, max_length=100),
        observation_type: str | None = Query(default=None, alias="type", max_length=40),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = ObservationStore(settings.intelligence_db_path).list(project, type=observation_type, limit=limit)
        audit.record(action="intelligence_observations_read", path=f"{project}:observations", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} observation(s)")
        return {"project": project, "observations": [item.as_dict() for item in records], "readOnly": True}

    @app.post("/intelligence/observations/record", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase25"])
    def intelligence_observation_record(
        body: IntelligenceObservationRecordRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending
        from app.intelligence.observation import Observation

        observation = Observation.build(project_id=body.project_id, type=body.type, source=body.source, summary=body.summary, metadata=body.metadata, risk_level=body.risk_level)
        return _register_pending(
            action="intelligence_observation_record", project=body.project_id, path="intelligence/observations",
            payload={"observation": observation.as_dict()}, reason=body.reason,
            preview_factory=lambda: f"RECORD observation {observation.type.value} for project {observation.project_id}; source and metadata are secret-scrubbed",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/intelligence/patterns/analyze", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase25"])
    def intelligence_patterns_analyze(
        body: IntelligencePatternAnalyzeRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending
        return _register_pending(
            action="intelligence_pattern_analyze", project=body.project_id, path="intelligence/patterns",
            payload={"limit": body.limit}, reason=body.reason,
            preview_factory=lambda: f"ANALYZE up to {body.limit} observations for patterns; no source or memory write",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/patterns", tags=["intelligence-phase25"])
    def intelligence_patterns(
        project: str = Query(..., min_length=1, max_length=100),
        pattern_type: str | None = Query(default=None, alias="type", max_length=50),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = _patterns(settings, project, limit)
        if pattern_type:
            records = [item for item in records if item.pattern_type.value == pattern_type]
        audit.record(action="intelligence_patterns_read", path=f"{project}:patterns", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} pattern(s)")
        return {"project": project, "patterns": [item.as_dict() for item in records[:limit]], "readOnly": True}

    @app.post("/intelligence/predictions/analyze", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase25"])
    def intelligence_predictions_analyze(
        body: IntelligencePredictionAnalyzeRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending
        return _register_pending(
            action="intelligence_prediction_analyze", project=body.project_id, path="intelligence/predictions",
            payload={"limit": body.limit}, reason=body.reason,
            preview_factory=lambda: f"PREDICT bounded engineering risks from project evidence; no action is triggered",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/predictions", tags=["intelligence-phase25"])
    def intelligence_predictions(
        project: str = Query(..., min_length=1, max_length=100),
        prediction_type: str | None = Query(default=None, alias="type", max_length=50),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = _predictions(settings, project, limit)
        if prediction_type:
            records = [item for item in records if item.prediction_type.value == prediction_type]
        audit.record(action="intelligence_predictions_read", path=f"{project}:predictions", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} prediction(s)")
        return {"project": project, "predictions": [item.as_dict() for item in records[:limit]], "readOnly": True}

    @app.get("/intelligence/recommendations", tags=["intelligence-phase25"])
    def intelligence_recommendations(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = _recommendations(settings, project, limit)
        ranking = RecommendationRanker().rank(records) if records else RecommendationRanking(project_id=project, reason="No recommendations have evidence to rank")
        audit.record(action="intelligence_recommendations_read", path=f"{project}:recommendations", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} recommendation(s)")
        return {"project": project, "recommendations": [item.as_dict() for item in records], "ranking": ranking.as_dict(), "readOnly": True}

    @app.get("/intelligence/decisions", tags=["intelligence-phase25"])
    def intelligence_evolution_decisions(
        project: str = Query(..., min_length=1, max_length=100),
        decision_status: str | None = Query(default=None, alias="status", max_length=20),
        limit: int = Query(default=100, ge=1, le=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        from app.intelligence.storage import IntelligenceStorage

        project = ensure_project(project)
        records = IntelligenceStorage(settings.intelligence_db_path).list_decisions(project, decision_status, limit)
        audit.record(action="intelligence_decisions_read", path=f"{project}:decisions", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} decision(s)")
        return {"project": project, "decisions": [item.as_dict() for item in records], "readOnly": True}

    @app.get("/intelligence/outcomes", tags=["intelligence-phase25"])
    def intelligence_outcomes(
        project: str = Query(..., min_length=1, max_length=100),
        outcome_status: str | None = Query(default=None, alias="status", max_length=32),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = OutcomeStore(settings.intelligence_db_path).list(project, status=outcome_status, limit=limit)
        audit.record(action="intelligence_outcomes_read", path=f"{project}:outcomes", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} outcome(s)")
        return {"project": project, "outcomes": [item.as_dict() for item in records], "readOnly": True}

    @app.post("/intelligence/outcomes/record", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase25"])
    def intelligence_outcome_record(
        body: IntelligenceOutcomeRecordRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending
        # Validate status and required fields before queueing, without writing.
        from app.intelligence.outcome import OutcomeStatus
        try:
            OutcomeStatus(body.status.upper())
        except ValueError as exc:
            from app.security.validator import ValidationFailed
            raise ValidationFailed("Unknown strategy outcome status") from exc
        return _register_pending(
            action="intelligence_outcome_record", project=body.project_id, path="intelligence/outcomes",
            payload=body.model_dump(exclude={"reason"}), reason=body.reason,
            preview_factory=lambda: f"RECORD {body.status.upper()} outcome for strategy {body.strategy_id}; no strategy execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/knowledge", tags=["intelligence-phase25"])
    def intelligence_knowledge(
        project: str = Query(..., min_length=1, max_length=100),
        category: str | None = Query(default=None, max_length=32),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        records = IntelligenceMemory(settings).list(project, category=category, limit=limit)
        audit.record(action="intelligence_knowledge_read", path=f"{project}:knowledge", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} knowledge record(s)")
        return {"project": project, "knowledge": records, "readOnly": True}

    @app.post("/intelligence/knowledge/propose", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase25"])
    def intelligence_knowledge_propose(
        body: IntelligenceKnowledgeProposalRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending
        memory = IntelligenceMemory(settings)
        return _register_pending(
            action="intelligence_knowledge_append", project=body.project_id, path=f"memory/intelligence/{body.category}",
            payload=body.model_dump(exclude={"reason"}), reason=body.reason,
            preview_factory=lambda: memory.preview(body.project_id, body.category, body.content, source=body.source, evidence=body.evidence, confidence=body.confidence),
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/intelligence/evidence/bundle", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence-phase25"])
    def intelligence_evidence_bundle(
        body: IntelligenceEvidenceBundleRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending
        return _register_pending(
            action="intelligence_evidence_bundle", project=body.project_id, path="intelligence/evidence", payload=body.model_dump(exclude={"reason"}), reason=body.reason,
            preview_factory=lambda: f"CREATE evidence bundle with {len(body.observation_ids)} observation(s), {len(body.pattern_ids)} pattern(s), {len(body.prediction_ids)} prediction(s); no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/evidence", tags=["intelligence-phase25"])
    def intelligence_evidence(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        bundles = EvidenceStore(settings.intelligence_db_path).list(project, limit)
        graph = build_phase26_snapshot(settings, project, limit=limit).graph
        audit.record(action="intelligence_evidence_read", path=f"{project}:evidence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(bundles)} bundle(s)")
        return {"project": project, "evidence": [bundle.as_dict() for bundle in bundles], "graph": graph.as_dict(), "readOnly": True}

    @app.get("/intelligence/evidence/graph", tags=["intelligence-phase26"])
    def intelligence_evidence_graph_phase26(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=1000, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        snapshot = build_phase26_snapshot(settings, project, limit=limit)
        audit.record(action="intelligence_evidence_graph_read", path=f"{project}:evidence/graph", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(snapshot.graph.nodes)} node(s), {len(snapshot.graph.edges)} edge(s)")
        return snapshot.graph.as_dict()

    @app.get("/intelligence/evidence/{bundle_id}", tags=["intelligence-phase25"])
    def intelligence_evidence_detail(bundle_id: str, project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        bundle = EvidenceStore(settings.intelligence_db_path).get(bundle_id, ensure_project(project))
        if bundle is None: raise ResourceNotFound(f"Evidence bundle '{bundle_id}' was not found for this project")
        audit.record(action="intelligence_evidence_read", path=f"{project}:evidence/{bundle_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return bundle.as_dict()

    @app.get("/intelligence/decisions/{decision_id}/evidence", tags=["intelligence-phase25"])
    def intelligence_decision_evidence(decision_id: str, project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        bundle = EvidenceStore(settings.intelligence_db_path).get_for_decision(decision_id, ensure_project(project))
        audit.record(action="intelligence_decision_evidence_read", path=f"{project}:decision/{decision_id}/evidence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return {"project": ensure_project(project), "decisionId": decision_id, "evidence": bundle.as_dict() if bundle else None, "readOnly": True}

    @app.get("/intelligence/quality", tags=["intelligence-phase25"])
    def intelligence_quality(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        observations = _observations(settings, project, 1000)
        patterns = _patterns(settings, project, 1000)
        predictions = _predictions(settings, project, 1000)
        recommendations = _recommendations(settings, project, 1000)
        outcomes = OutcomeStore(settings.intelligence_db_path).list(project, limit=1000)
        knowledge = IntelligenceMemory(settings).list(project, limit=1000)
        decisions = __import__("app.intelligence", fromlist=["IntelligenceStorage"]).IntelligenceStorage(settings.intelligence_db_path).list_decisions(project=project)
        bundles = EvidenceStore(settings.intelligence_db_path).list(project, 1000)
        decision_evidence = not decisions or all(any(bundle.decision_id == decision.id for bundle in bundles) for decision in decisions)
        report = QualityGate11Evaluator().evaluate(
            observation_integrity=all(item.project_id == project for item in observations), observation_count=len(observations),
            pattern_evidence=all(bool(item.evidence) for item in patterns), pattern_count=len(patterns),
            prediction_confidence=(sum(item.confidence for item in predictions) / len(predictions)) if predictions else 0.0, prediction_count=len(predictions),
            recommendation_traceability=all(bool(item.evidence) for item in recommendations), recommendation_count=len(recommendations),
            decision_evidence=decision_evidence, decision_count=len(decisions),
            outcome_completeness=all(item.expected_outcome and item.actual_outcome for item in outcomes), outcome_count=len(outcomes),
            knowledge_provenance=all(item.get("source") and item.get("evidence") is not None and "confidence" in item for item in knowledge), knowledge_count=len(knowledge),
        )
        audit.record(action="intelligence_quality_read", path=f"{project}:quality", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"status={report['status']}")
        return {"project": project, **report}

    @app.get("/quality/v11/{project}", tags=["quality"])
    def quality_gate_v11(project: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        # Keep the canonical intelligence quality endpoint as the single
        # implementation, while preserving the versioned quality convention.
        project = ensure_project(project)
        observations = _observations(settings, project, 1000); patterns = _patterns(settings, project, 1000); predictions = _predictions(settings, project, 1000); recommendations = _recommendations(settings, project, 1000)
        report = QualityGate11Evaluator().evaluate(observation_count=len(observations), pattern_count=len(patterns), pattern_evidence=all(bool(item.evidence) for item in patterns), prediction_count=len(predictions), prediction_confidence=(sum(item.confidence for item in predictions) / len(predictions)) if predictions else 0.0, recommendation_count=len(recommendations), recommendation_traceability=all(bool(item.evidence) for item in recommendations))
        audit.record(action="quality_gate_v11_read", path=f"quality/v11/{project}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"status={report['status']}")
        return {"project": project, **report}

    # ------------------------------------------------------------------
    # Phase 26 · Engineering Intelligence 2.0 (all reads, no mutation)
    # ------------------------------------------------------------------

    @app.get("/intelligence/trends", tags=["intelligence-phase26"])
    def intelligence_trends(
        project: str = Query(..., min_length=1, max_length=100),
        metric: str | None = Query(default=None, max_length=80),
        period: str = Query(default="daily", max_length=20),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        snapshot = build_phase26_snapshot(settings, project, limit=limit)
        records = EngineeringTrendEngine().analyze(project, snapshot.observations, metric=metric, period=period)
        if not records and period.lower() in {"daily", "day"}:
            records = [item for item in snapshot.trends if metric is None or item.metric == metric]
        audit.record(action="intelligence_trends_read", path=f"{project}:trends", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} trend(s)")
        return {"project": project, "trends": [item.as_dict() for item in records[:limit]], "period": period, "readOnly": True}

    @app.get("/intelligence/correlations", tags=["intelligence-phase26"])
    def intelligence_correlations(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        snapshot = build_phase26_snapshot(settings, project, limit=limit)
        audit.record(action="intelligence_correlations_read", path=f"{project}:correlations", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(snapshot.correlations)} correlation(s)")
        return {"project": project, "correlations": [item.as_dict() for item in snapshot.correlations[:limit]], "causationClaims": [], "readOnly": True}

    @app.get("/intelligence/impact", tags=["intelligence-phase26"])
    def intelligence_impact(
        project: str = Query(..., min_length=1, max_length=100),
        changed_file: list[str] | None = Query(default=None),
        changed_symbol: list[str] | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        snapshot = build_phase26_snapshot(settings, project, limit=limit, changed_files=changed_file or [], changed_symbols=changed_symbol or [])
        audit.record(action="intelligence_impact_read", path=f"{project}:impact", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(snapshot.impact)} impact prediction(s)")
        return {"project": project, "impact": [item.as_dict() for item in snapshot.impact[:limit]], "predictions": [item.as_dict() for item in snapshot.impact[:limit]], "readOnly": True}

    @app.get("/intelligence/dependencies", tags=["intelligence-phase26"])
    def intelligence_dependencies(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        snapshot = build_phase26_snapshot(settings, project, limit=limit)
        audit.record(action="intelligence_dependencies_read", path=f"{project}:dependencies", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(snapshot.dependencies)} dependency risk(s)")
        return {"project": project, "dependencies": [item.as_dict() for item in snapshot.dependencies[:limit]], "risks": [item.as_dict() for item in snapshot.dependencies[:limit]], "readOnly": True}

    @app.get("/intelligence/evaluations", tags=["intelligence-phase26"])
    def intelligence_evaluations(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        snapshot = build_phase26_snapshot(settings, project, limit=limit)
        audit.record(action="intelligence_evaluations_read", path=f"{project}:evaluations", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(snapshot.evaluations)} evaluation(s)")
        return {"project": project, "evaluations": snapshot.evaluations[:limit], "metrics": snapshot.evaluation_metrics.as_dict(), "readOnly": True}

    @app.get("/intelligence/recommendations/ranking", tags=["intelligence-phase26"])
    def intelligence_recommendation_ranking(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        project = ensure_project(project)
        snapshot = build_phase26_snapshot(settings, project, limit=limit)
        ranking = RecommendationRanker().rank(snapshot.recommendations[:limit]) if snapshot.recommendations else snapshot.ranking
        audit.record(action="intelligence_recommendation_ranking_read", path=f"{project}:recommendations/ranking", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(ranking.ranked)} ranked recommendation(s)")
        return {"project": project, **ranking.as_dict()}

