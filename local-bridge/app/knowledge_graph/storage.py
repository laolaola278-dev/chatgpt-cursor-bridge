from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class GraphStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS graph_nodes (project TEXT NOT NULL, node_id TEXT NOT NULL, node_type TEXT NOT NULL, label TEXT NOT NULL, metadata TEXT NOT NULL, PRIMARY KEY(project,node_id));
        CREATE TABLE IF NOT EXISTS graph_edges (project TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL, relation TEXT NOT NULL, PRIMARY KEY(project,source,target,relation));
        CREATE INDEX IF NOT EXISTS graph_node_label ON graph_nodes(project,label);
        CREATE INDEX IF NOT EXISTS graph_edge_source ON graph_edges(project,source);
        CREATE INDEX IF NOT EXISTS graph_edge_target ON graph_edges(project,target);
        """)
        self.connection.commit()

    def replace(self, project: str, nodes: list[dict], edges: list[dict]) -> None:
        conn = self.connection
        conn.execute("DELETE FROM graph_edges WHERE project=?", (project,))
        conn.execute("DELETE FROM graph_nodes WHERE project=?", (project,))
        conn.executemany("INSERT INTO graph_nodes VALUES(?,?,?,?,?)", [(project, item["id"], item["type"], item["label"], json.dumps(item.get("metadata", {}), ensure_ascii=False)) for item in nodes])
        conn.executemany("INSERT OR IGNORE INTO graph_edges VALUES(?,?,?,?)", [(project, item["source"], item["target"], item["relation"]) for item in edges])
        conn.commit()
