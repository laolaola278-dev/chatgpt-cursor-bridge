"""SQLite persistence for the organization graph reasoning layer.

Stores graph nodes, non-hierarchical edges and checksummed snapshots. All
records are metadata/derived analysis; nothing here can modify project source
code or memory. Restore uses a single BEGIN/COMMIT/ROLLBACK transaction so a
failed restore never pollutes the current graph.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import EdgeType, GraphNode, GraphSnapshot, OrgEdge


class OrganizationGraphStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
                parent_id TEXT, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT NOT NULL, target TEXT NOT NULL, relation TEXT NOT NULL,
                metadata_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(source, target, relation)
            );
            CREATE TABLE IF NOT EXISTS organization_graph_snapshots (
                id TEXT PRIMARY KEY, checksum TEXT NOT NULL, node_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL, graph_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS graph_nodes_parent ON graph_nodes(parent_id);
            CREATE INDEX IF NOT EXISTS graph_edges_target ON graph_edges(target);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    # -- nodes ---------------------------------------------------------------

    def save_node(self, node: GraphNode) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO graph_nodes(id,type,name,parent_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
            (node.id, node.type, node.name, node.parent_id,
             json.dumps(node.metadata, ensure_ascii=False), node.created_at),
        )
        self.connection.commit()

    def sync_from_entities(self, entities: list[dict[str, Any]]) -> int:
        """Upsert Phase 22 OrgEntity payloads into the graph (old-data compatible)."""
        for entity in entities:
            self.save_node(GraphNode.from_entity(entity))
        return len(entities)

    def get_node(self, node_id: str) -> GraphNode | None:
        row = self.connection.execute("SELECT * FROM graph_nodes WHERE id=?", (node_id,)).fetchone()
        return self._node(row) if row else None

    def list_nodes(self) -> list[GraphNode]:
        rows = self.connection.execute("SELECT * FROM graph_nodes ORDER BY created_at").fetchall()
        return [self._node(row) for row in rows]

    def children(self, parent_id: str) -> list[GraphNode]:
        rows = self.connection.execute("SELECT * FROM graph_nodes WHERE parent_id=? ORDER BY created_at", (parent_id,)).fetchall()
        return [self._node(row) for row in rows]

    @staticmethod
    def _node(row: sqlite3.Row) -> GraphNode:
        return GraphNode(row["id"], row["type"], row["name"], row["parent_id"],
                         json.loads(row["metadata_json"] or "{}"), row["created_at"])

    # -- edges ---------------------------------------------------------------

    def save_edge(self, edge: OrgEdge) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO graph_edges(source,target,relation,metadata_json,created_at) VALUES(?,?,?,?,?)",
            (edge.source, edge.target, edge.relation.value,
             json.dumps(edge.metadata, ensure_ascii=False), edge.created_at),
        )
        self.connection.commit()

    def list_edges(self) -> list[OrgEdge]:
        rows = self.connection.execute("SELECT * FROM graph_edges ORDER BY created_at").fetchall()
        return [
            OrgEdge(row["source"], row["target"], EdgeType(row["relation"]),
                    json.loads(row["metadata_json"] or "{}"), row["created_at"])
            for row in rows
        ]

    # -- snapshots -------------------------------------------------------------

    def save_snapshot(self, snapshot: GraphSnapshot) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO organization_graph_snapshots(id,checksum,node_count,edge_count,graph_json,created_at) VALUES(?,?,?,?,?,?)",
            (snapshot.id, snapshot.checksum, snapshot.node_count, snapshot.edge_count,
             snapshot.graph_json, snapshot.created_at),
        )
        self.connection.commit()

    def get_snapshot(self, snapshot_id: str) -> GraphSnapshot | None:
        row = self.connection.execute("SELECT * FROM organization_graph_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if row is None:
            return None
        return GraphSnapshot(row["id"], row["checksum"], int(row["node_count"]), int(row["edge_count"]), row["graph_json"], row["created_at"])

    def list_snapshots(self, limit: int = 50) -> list[GraphSnapshot]:
        rows = self.connection.execute(
            "SELECT * FROM organization_graph_snapshots ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            GraphSnapshot(row["id"], row["checksum"], int(row["node_count"]), int(row["edge_count"]), row["graph_json"], row["created_at"])
            for row in rows
        ]

    def export_graph(self) -> dict[str, Any]:
        return {
            "nodes": [node.as_dict() for node in self.list_nodes()],
            "edges": [edge.as_dict() for edge in self.list_edges()],
        }

    def replace_graph(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        """Atomic full replacement in a single transaction; failure rolls back."""
        cursor = self.connection
        try:
            cursor.execute("BEGIN")
            cursor.execute("DELETE FROM graph_nodes")
            cursor.execute("DELETE FROM graph_edges")
            for payload in nodes:
                node = GraphNode(
                    payload["id"], payload["type"], payload["name"],
                    payload.get("parentId"), payload.get("metadata") or {}, payload.get("createdAt") or _now(),
                )
                cursor.execute(
                    "INSERT INTO graph_nodes(id,type,name,parent_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
                    (node.id, node.type, node.name, node.parent_id,
                     json.dumps(node.metadata, ensure_ascii=False), node.created_at),
                )
            for payload in edges:
                edge = OrgEdge(
                    payload["source"], payload["target"], EdgeType(payload["relation"]),
                    payload.get("metadata") or {}, payload.get("createdAt") or _now(),
                )
                cursor.execute(
                    "INSERT INTO graph_edges(source,target,relation,metadata_json,created_at) VALUES(?,?,?,?,?)",
                    (edge.source, edge.target, edge.relation.value,
                     json.dumps(edge.metadata, ensure_ascii=False), edge.created_at),
                )
            cursor.execute("COMMIT")
        except Exception:
            cursor.execute("ROLLBACK")
            raise


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
