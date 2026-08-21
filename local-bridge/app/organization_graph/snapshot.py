"""Graph Snapshot Versioning (Phase 23).

Creates SHA-256 checksummed snapshots of the organization graph and restores
them transactionally. A restore verifies the checksum first, then replaces the
graph in a single BEGIN/COMMIT/ROLLBACK transaction: a failed restore never
pollutes the current graph.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.security.validator import ResourceNotFound, ValidationFailed

from .models import GraphSnapshot, canonical_graph_json, checksum_of
from .storage import OrganizationGraphStorage


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[-14:]


class GraphSnapshotManager:
    def __init__(self, storage: OrganizationGraphStorage) -> None:
        self.storage = storage

    def create(self) -> GraphSnapshot:
        graph = self.storage.export_graph()
        payload = canonical_graph_json(graph["nodes"], graph["edges"])
        snapshot = GraphSnapshot(
            id=f"snap_{_stamp()}",
            checksum=checksum_of(payload),
            node_count=len(graph["nodes"]),
            edge_count=len(graph["edges"]),
            graph_json=payload,
        )
        self.storage.save_snapshot(snapshot)
        return snapshot

    def list(self, limit: int = 50) -> list[GraphSnapshot]:
        return self.storage.list_snapshots(limit)

    def restore(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.storage.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ResourceNotFound(f"Snapshot '{snapshot_id}' was not found")
        graph = json.loads(snapshot.graph_json)
        payload = canonical_graph_json(graph.get("nodes", []), graph.get("edges", []))
        if checksum_of(payload) != snapshot.checksum:
            raise ValidationFailed(f"Snapshot '{snapshot_id}' checksum mismatch; refusing to restore")
        self.storage.replace_graph(graph.get("nodes", []), graph.get("edges", []))
        return {
            "snapshotId": snapshot.id,
            "restored": True,
            "nodeCount": snapshot.node_count,
            "edgeCount": snapshot.edge_count,
            "readOnly": True,
        }
