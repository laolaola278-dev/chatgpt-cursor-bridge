"""Phase 30 · Context Intelligence API.

Every analysis endpoint is a read-only GET. The single POST
(``/context/dev/intelligence/patch-proposal``) only enqueues an ApprovalStore
request — the proposal record is persisted only after human approval, and no
source file is ever written by this phase.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.context.dev.intelligence.engine import ContextIntelligenceEngine
from app.models.request import ContextPatchProposalRequest
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.sandbox import SandboxViolation, validate_project_name
from app.security.validator import ResourceNotFound, ValidationFailed


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _engine(settings: Settings) -> ContextIntelligenceEngine:
    from app.context.dev.bundle import ContextBundleEngine

    return ContextIntelligenceEngine(settings, ContextBundleEngine(settings))


def _error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, SandboxViolation):
        return JSONResponse(status_code=403, content={"detail": str(exc), "code": "sandbox_violation"})
    if isinstance(exc, ResourceNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    if isinstance(exc, ValidationFailed):
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    if isinstance(exc, PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc), "code": "sensitive_path"})
    return JSONResponse(status_code=500, content={"detail": f"Context intelligence unavailable: {exc}"})


def register_context_intelligence_routes(app: Any) -> None:
    @app.get("/context/dev/intelligence/suggest", tags=["context-phase30"])
    def context_intelligence_suggest(
        project: str = Query(..., min_length=1, max_length=100),
        query: str = Query(default="", max_length=500),
        agent: str = Query(default="ASSISTANT", max_length=64),
        selected_path: str = Query(default="", max_length=500),
        selected_text: str = Query(default="", max_length=4000),
        error: str = Query(default="", max_length=4000),
        test_failure: str = Query(default="", max_length=4000),
        limit: int = Query(default=40, ge=1, le=200),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            result = _engine(settings).suggest(
                project,
                query=query,
                agent=agent,
                selected_path=selected_path,
                selected_text=selected_text,
                error=error,
                test_failure=test_failure,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_suggest", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(result.items)} candidate(s)")
        return result.as_dict()

    @app.get("/context/dev/intelligence/relationships", tags=["context-phase30"])
    def context_intelligence_relationships(
        project: str = Query(..., min_length=1, max_length=100),
        file: str | None = Query(default=None, max_length=500),
        symbol: str | None = Query(default=None, max_length=200),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            if not file and not symbol:
                raise ValidationFailed("Provide either 'file' or 'symbol'")
            result = _engine(settings).relationships(project, file=file, symbol=symbol)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_relationships", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"target={result.target}")
        return result.as_dict()

    @app.get("/context/dev/intelligence/error", tags=["context-phase30"])
    def context_intelligence_error(
        project: str = Query(..., min_length=1, max_length=100),
        error: str = Query(..., min_length=1, max_length=4000),
        stack_trace: str = Query(default="", max_length=12000),
        test_failure: str = Query(default="", max_length=4000),
        file: str | None = Query(default=None, max_length=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            result = _engine(settings).error_bundle(project, error=error, stack_trace=stack_trace, test_failure=test_failure, file=file)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_error", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"kind={result.kind}")
        return result.as_dict()

    @app.get("/context/dev/intelligence/test-failure", tags=["context-phase30"])
    def context_intelligence_test_failure(
        project: str = Query(..., min_length=1, max_length=100),
        test: str = Query(..., min_length=1, max_length=1000),
        failure: str = Query(default="", max_length=4000),
        expected: str = Query(default="", max_length=2000),
        actual: str = Query(default="", max_length=2000),
        traceback: str = Query(default="", max_length=12000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            result = _engine(settings).test_failure(project, test=test, failure=failure, expected=expected, actual=actual, traceback=traceback)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_test_failure", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"test={result.test[:80]}")
        return result.as_dict()

    @app.get("/context/dev/intelligence/git", tags=["context-phase30"])
    def context_intelligence_git(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            result = _engine(settings).git_intel(project)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_git", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{result.stats['files']} changed file(s)")
        return result.as_dict()

    @app.get("/context/dev/intelligence/review", tags=["context-phase30"])
    def context_intelligence_review(
        project: str = Query(..., min_length=1, max_length=100),
        file: str | None = Query(default=None, max_length=500),
        symbol: str | None = Query(default=None, max_length=200),
        selection: str = Query(default="", max_length=8000),
        diff: str = Query(default="", max_length=12000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            if not file and not symbol and not selection and not diff:
                raise ValidationFailed("Provide 'file', 'symbol', 'selection' or 'diff'")
            result = _engine(settings).review(project, file=file, symbol=symbol, selection=selection, diff=diff)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_review", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(result.findings)} finding(s)")
        return result.as_dict()

    @app.get("/context/dev/intelligence/injection", tags=["context-phase30"])
    def context_intelligence_injection(
        project: str = Query(..., min_length=1, max_length=100),
        text: str = Query(..., min_length=1, max_length=8000),
        source: str = Query(default="project_content", max_length=40),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            result = _engine(settings).injection(project, text=text, source=source)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_injection", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"verdict={result.verdict}")
        payload = result.as_dict()
        payload["project"] = project
        return payload

    @app.get("/context/dev/intelligence/budget", tags=["context-phase30"])
    def context_intelligence_budget(
        project: str = Query(..., min_length=1, max_length=100),
        query: str = Query(default="", max_length=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            result = _engine(settings).suggest(project, query=query, limit=200)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_budget", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="budget usage")
        return {
            "source": "context/dev/intelligence",
            "project": project,
            "budget": [usage.as_dict() for usage in result.budget],
            "dedup": result.dedup.as_dict(),
            "truncated": result.truncated,
            "globalLimit": 64 * 1024,
            "readOnly": True,
        }

    @app.get("/context/dev/intelligence/snapshot", tags=["context-phase30"])
    def context_intelligence_snapshot(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            snapshot = _engine(settings).snapshot(project)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_intelligence_snapshot", path=f"{project}:context/dev/intelligence", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="read-only snapshot")
        return snapshot.as_dict()

    @app.post("/context/dev/intelligence/patch-proposal", status_code=status.HTTP_202_ACCEPTED, tags=["context-phase30"])
    def context_intelligence_patch_proposal(
        body: ContextPatchProposalRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        project = validate_project_name(body.project)
        proposal = _engine(settings).patch_proposal(
            project=project,
            target_file=body.target_file,
            target_symbol=body.target_symbol,
            proposed_change=body.proposed_change,
            reason=body.reason,
            expected_impact=body.expected_impact,
            risk=body.risk,
            agent=body.agent,
        )

        def preview() -> str:
            return f"RECORD Patch Proposal {proposal.id} for {proposal.target_file} ({proposal.risk} risk); proposal record only — no source file is written"

        return _register_pending(
            action="context_patch_proposal",
            project=project,
            path="context/dev/intelligence/patch-proposal",
            payload=proposal.as_dict(),
            reason=body.reason,
            preview_factory=preview,
            settings=settings, audit=audit, approvals=approvals,
        )
