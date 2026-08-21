"""Phase 23 organization graph API routes.

Read-only reasoning endpoints (ancestors, descendants, owner, impact,
context, snapshot list) plus approval-gated writes (sync from the Phase 22
org store, snapshot create, snapshot restore). No route here can execute
actions or modify source code.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.models.request import (
    OrganizationGraphSnapshotCreateRequest,
    OrganizationGraphSnapshotRestoreRequest,
    OrganizationGraphSyncRequest,
)
from app.organization_graph.context import OrganizationContextBuilder
from app.organization_graph.reasoning import GraphReasoningEngine
from app.organization_graph.snapshot import GraphSnapshotManager
from app.organization_graph.storage import OrganizationGraphStorage
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _graph_storage(settings: Settings) -> OrganizationGraphStorage:
    return OrganizationGraphStorage(settings.organization_graph_db_path)


def register_organization_graph_routes(app: Any) -> None:
    """Attach all Phase 23 organization graph routes to the FastAPI app."""

    @app.get("/organization-graph/ancestors", tags=["organization-graph"])
    def organization_graph_ancestors(
        node_id: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        ancestors = GraphReasoningEngine(_graph_storage(settings)).get_ancestors(node_id)
        audit.record(
            action="organization_graph_ancestors_read", path=f"organization-graph/{node_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(ancestors)} ancestor(s)",
        )
        return {"node": node_id, "ancestors": ancestors, "count": len(ancestors), "readOnly": True}

    @app.get("/organization-graph/descendants", tags=["organization-graph"])
    def organization_graph_descendants(
        node_id: str = Query(..., min_length=1, max_length=100),
        entity_type: str | None = Query(default=None, alias="type", max_length=32),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        engine = GraphReasoningEngine(_graph_storage(settings))
        if entity_type:
            descendants = engine.get_descendants_by_type(node_id, entity_type)
        else:
            descendants = engine.get_descendants(node_id)
        audit.record(
            action="organization_graph_descendants_read", path=f"organization-graph/{node_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(descendants)} descendant(s)",
        )
        return {"node": node_id, "type": entity_type, "descendants": descendants, "count": len(descendants), "readOnly": True}

    @app.get("/organization-graph/owner", tags=["organization-graph"])
    def organization_graph_owner(
        node_id: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        result = GraphReasoningEngine(_graph_storage(settings)).find_owner(node_id)
        audit.record(
            action="organization_graph_owner_read", path=f"organization-graph/{node_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"owner={result['owner'].get('id') if result['owner'] else None}",
        )
        return {**result, "readOnly": True}

    @app.get("/organization-graph/impact", tags=["organization-graph"])
    def organization_graph_impact(
        node_id: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = GraphReasoningEngine(_graph_storage(settings)).impact_analysis(node_id)
        audit.record(
            action="organization_graph_impact_read", path=f"organization-graph/{node_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(report['impacted'])} impacted node(s)",
        )
        return report

    @app.get("/organization-graph/context", tags=["organization-graph"])
    def organization_graph_context(
        node_id: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        context = OrganizationContextBuilder(_graph_storage(settings)).build_context(node_id)
        audit.record(
            action="organization_graph_context_read", path=f"organization-graph/{node_id}",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"chain={len(context['ancestorChain'])}",
        )
        return context

    @app.get("/organization-graph/snapshot/list", tags=["organization-graph"])
    def organization_graph_snapshot_list(
        limit: int = Query(default=50, ge=1, le=200),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        snapshots = [snapshot.as_dict() for snapshot in GraphSnapshotManager(_graph_storage(settings)).list(limit)]
        audit.record(
            action="organization_graph_snapshot_list_read", path="organization-graph/snapshot/list",
            permission=PermissionLevel.LEVEL_0.value, approved=True, result="success",
            detail=f"{len(snapshots)} snapshot(s)",
        )
        return {"snapshots": snapshots, "readOnly": True}

    @app.post("/organization-graph/sync", status_code=status.HTTP_202_ACCEPTED, tags=["organization-graph"])
    def organization_graph_sync(
        body: OrganizationGraphSyncRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_graph_sync", project="organization", path="organization-graph/sync",
            payload={}, reason=body.reason,
            preview_factory=lambda: "SYNC Phase 22 org entities into the reasoning graph (metadata only)",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/organization-graph/snapshot/create", status_code=status.HTTP_202_ACCEPTED, tags=["organization-graph"])
    def organization_graph_snapshot_create(
        body: OrganizationGraphSnapshotCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        return _register_pending(
            action="organization_graph_snapshot_create", project="organization", path="organization-graph/snapshot",
            payload={}, reason=body.reason,
            preview_factory=lambda: "CREATE checksummed snapshot of the organization graph; no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.post("/organization-graph/snapshot/restore", status_code=status.HTTP_202_ACCEPTED, tags=["organization-graph"])
    def organization_graph_snapshot_restore(
        body: OrganizationGraphSnapshotRestoreRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        from app.main import _register_pending

        manager = GraphSnapshotManager(_graph_storage(settings))
        snapshot = manager.storage.get_snapshot(body.snapshot_id)
        if snapshot is None:
            from app.security.validator import ResourceNotFound

            raise ResourceNotFound(f"Snapshot '{body.snapshot_id}' was not found")
        return _register_pending(
            action="organization_graph_snapshot_restore", project="organization", path="organization-graph/snapshot",
            payload={"snapshot_id": body.snapshot_id}, reason=body.reason,
            preview_factory=lambda: f"RESTORE graph to snapshot {body.snapshot_id} (nodes={snapshot.node_count}, edges={snapshot.edge_count})",
            settings=settings, audit=audit, approvals=approvals,
        )
