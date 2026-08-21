"""Phase 29 · Advanced Developer Context & Read-only Code Intelligence API.

Every endpoint is a read-only GET. No endpoint can execute tests, run builds,
run git mutations, install packages, write files, or enqueue approvals. File
reads are bounded by the context budget and filtered by the security layer;
sensitive paths (.env, key material, credentials) are never returned.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.context.dev.budget import ContextBudget
from app.context.dev.bundle import ContextBundleEngine
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.sandbox import SandboxViolation, validate_project_name
from app.security.validator import ResourceNotFound, ValidationFailed
from app.workflow.manager import WorkflowManager
from app.workflow.storage import WorkflowStorage


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def workflow_storage_dependency(settings: Settings = Depends(settings_dependency)) -> WorkflowStorage:
    # Imported lazily to avoid a circular import with app.main at load time.
    from app.main import _get_workflow_storage_cached

    return _get_workflow_storage_cached(str(settings.workflow_root))


def workflow_dependency(
    settings: Settings = Depends(settings_dependency),
    storage: WorkflowStorage = Depends(workflow_storage_dependency),
    approvals: ApprovalStore = Depends(approvals_dependency),
    audit: AuditLogger = Depends(audit_dependency),
) -> WorkflowManager:
    return WorkflowManager(settings=settings, storage=storage, approvals=approvals, audit=audit)


def _engine(settings: Settings, workflows: WorkflowManager) -> ContextBundleEngine:
    return ContextBundleEngine(settings, workflows)


def _budget(
    max_file_kb: int = 256,
    max_symbols: int = 500,
    max_deps: int = 200,
    max_files: int = 200,
) -> ContextBudget:
    return ContextBudget(
        max_file_bytes=max(1, min(max_file_kb, 4096)) * 1024,
        max_symbols=max(1, min(max_symbols, 5000)),
        max_dependencies=max(1, min(max_deps, 2000)),
        max_files=max(1, min(max_files, 2000)),
    )


def _error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, SandboxViolation):
        return JSONResponse(status_code=403, content={"detail": str(exc), "code": "sandbox_violation"})
    if isinstance(exc, ResourceNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    if isinstance(exc, ValidationFailed):
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    if isinstance(exc, PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc), "code": "sensitive_path"})
    return JSONResponse(status_code=500, content={"detail": f"Developer context unavailable: {exc}"})


def register_dev_context_routes(app: Any) -> None:
    @app.get("/context/dev/project", tags=["context-phase29"])
    def dev_project_context(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            payload = _engine(settings, workflows).project_context(project, ContextBudget())
        except Exception as exc:  # noqa: BLE001 - mapped to HTTP responses
            return _error_response(exc)
        audit.record(action="context_dev_project", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="Read-only project developer context")
        return {"source": "context/dev", "project": project, "contextType": "project", "securityFiltering": True, "data": payload}

    @app.get("/context/dev/files", tags=["context-phase29"])
    def dev_file_list(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            budget = _budget(max_files=limit)
            payload = _engine(settings, workflows).files(project, budget)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_files", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(payload['files'])} file(s)")
        return {"source": "context/dev", "project": project, "contextType": "files", "securityFiltering": True, **payload}

    @app.get("/context/dev/file/{file_path:path}", tags=["context-phase29"])
    def dev_file_context(
        file_path: str,
        project: str = Query(..., min_length=1, max_length=100),
        max_file_kb: int = Query(default=256, ge=1, le=4096),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            file_context = _engine(settings, workflows).file(project, file_path, _budget(max_file_kb=max_file_kb))
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_file", path=f"{project}:{file_path}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{file_context.size} byte(s)")
        return {"source": "context/dev", "project": project, "contextType": "file", "securityFiltering": True, "data": file_context.as_dict()}

    @app.get("/context/dev/symbols", tags=["context-phase29"])
    def dev_symbols(
        project: str = Query(..., min_length=1, max_length=100),
        q: str = Query(default="", max_length=300),
        limit: int = Query(default=200, ge=1, le=5000),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            payload = _engine(settings, workflows).symbols(project, query=q, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_symbols", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{payload.total} symbol(s)")
        return {"source": "context/dev", "project": project, "contextType": "symbols", "securityFiltering": True, "data": payload.as_dict()}

    @app.get("/context/dev/symbol/{symbol_id}", tags=["context-phase29"])
    def dev_symbol_detail(
        symbol_id: str,
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            symbol = _engine(settings, workflows).symbol(project, symbol_id)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        if symbol is None:
            return JSONResponse(status_code=404, content={"detail": f"Symbol not found: {symbol_id}"})
        audit.record(action="context_dev_symbol", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=symbol["name"])
        return {"source": "context/dev", "project": project, "contextType": "symbol", "securityFiltering": True, "data": symbol}

    @app.get("/context/dev/dependencies", tags=["context-phase29"])
    def dev_dependencies(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=200, ge=1, le=2000),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            payload = _engine(settings, workflows).dependencies(project, _budget(max_deps=limit))
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_dependencies", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{payload.total} dependency(ies)")
        return {"source": "context/dev", "project": project, "contextType": "dependencies", "securityFiltering": True, "data": payload.as_dict()}

    @app.get("/context/dev/git", tags=["context-phase29"])
    def dev_git_context(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            payload = _engine(settings, workflows).git(project, ContextBudget())
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_git", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"branch={payload.branch}")
        return {"source": "context/dev", "project": project, "contextType": "git", "securityFiltering": True, "data": payload.as_dict()}

    @app.get("/context/dev/tests", tags=["context-phase29"])
    def dev_test_context(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            payload = _engine(settings, workflows).tests(project)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_tests", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="Read-only test/build status")
        return {"source": "context/dev", "project": project, "contextType": "tests", "securityFiltering": True, "data": payload.as_dict()}

    @app.get("/context/dev/bundle", tags=["context-phase29"])
    def dev_context_bundle(
        project: str = Query(..., min_length=1, max_length=100),
        agent: str = Query(default="ASSISTANT", max_length=64),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            payload = _engine(settings, workflows).bundle(project, agent)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_bundle", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="Read-only developer context bundle")
        return payload

    @app.get("/context/dev/status", tags=["context-phase29"])
    def dev_context_status(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        workflows: WorkflowManager = Depends(workflow_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            engine = _engine(settings, workflows)
            budget = ContextBudget()
            project_ctx = engine.project_context(project, budget)
            tests = engine.tests(project)
            git = engine.git(project, budget)
            status = {
                "project": project,
                "available": {
                    "project": True,
                    "files": True,
                    "symbols": True,
                    "dependencies": True,
                    "git": True,
                    "tests": tests.test_status is not None or tests.build_status is not None,
                },
                "git": {"branch": git.branch, "clean": git.clean},
                "testStatus": tests.test_status,
                "buildStatus": tests.build_status,
                "securityFiltering": True,
            }
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(action="context_dev_status", path=f"{project}:context/dev", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="Developer context availability")
        return status
