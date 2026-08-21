from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import EngineeringGraph, GraphEdge, GraphNode


class EngineeringGraphStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY, type TEXT NOT NULL, project TEXT NOT NULL,
                label TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT NOT NULL, target TEXT NOT NULL, relation TEXT NOT NULL,
                project TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(source, target, relation, project)
            );
            CREATE INDEX IF NOT EXISTS graph_nodes_project ON graph_nodes(project);
            CREATE INDEX IF NOT EXISTS graph_edges_project ON graph_edges(project);
            CREATE TABLE IF NOT EXISTS attributes (
                node_id TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL,
                PRIMARY KEY(node_id, key)
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def clear_project(self, project: str) -> None:
        self.connection.execute("DELETE FROM graph_edges WHERE project=?", (project,))
        self.connection.execute("DELETE FROM graph_nodes WHERE project=?", (project,))
        self.connection.commit()

    def save_node(self, node: GraphNode) -> None:
        encoded = json.dumps(node.metadata, ensure_ascii=False)
        self.connection.execute(
            """INSERT INTO graph_nodes(id,type,project,label,metadata_json,created_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET type=excluded.type,
               project=excluded.project,label=excluded.label,metadata_json=excluded.metadata_json""",
            (node.id, node.type, node.project, node.label, encoded, node.created_at),
        )
        self.connection.execute("DELETE FROM attributes WHERE node_id=?", (node.id,))
        self.connection.executemany("INSERT INTO attributes(node_id,key,value_json) VALUES (?,?,?)", [(node.id, key, json.dumps(value, ensure_ascii=False)) for key, value in node.metadata.items()])
        self.connection.commit()

    def save_edge(self, edge: GraphEdge) -> None:
        self.connection.execute(
            """INSERT INTO graph_edges(source,target,relation,project,metadata_json,created_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(source,target,relation,project) DO UPDATE SET
               metadata_json=excluded.metadata_json""",
            (edge.source, edge.target, edge.relation, edge.project, json.dumps(edge.metadata, ensure_ascii=False), edge.created_at),
        )
        self.connection.commit()

    @staticmethod
    def _node(row: sqlite3.Row) -> GraphNode:
        return GraphNode(row["id"], row["type"], row["project"], row["label"], json.loads(row["metadata_json"] or "{}"), row["created_at"])

    @staticmethod
    def _edge(row: sqlite3.Row) -> GraphEdge:
        return GraphEdge(row["source"], row["target"], row["relation"], row["project"], json.loads(row["metadata_json"] or "{}"), row["created_at"])

    def get_graph(self, project: str) -> EngineeringGraph:
        nodes = [self._node(row) for row in self.connection.execute("SELECT * FROM graph_nodes WHERE project=? ORDER BY id", (project,)).fetchall()]
        edges = [self._edge(row) for row in self.connection.execute("SELECT * FROM graph_edges WHERE project=? ORDER BY source,target", (project,)).fetchall()]
        return EngineeringGraph(project=project, nodes=nodes, edges=edges)

    def query(self, project: str, keyword: str) -> EngineeringGraph:
        return self.get_graph(project)
