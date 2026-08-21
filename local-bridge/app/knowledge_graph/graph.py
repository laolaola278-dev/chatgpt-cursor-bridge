from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.code_intelligence.index import CodeIndex

from .models import GraphEdge, GraphNode
from .storage import GraphStorage


class KnowledgeGraph:
    def __init__(self, db_path: str | Path, code_index: CodeIndex) -> None:
        self.storage = GraphStorage(db_path)
        self.code_index = code_index

    def build(self, project: str) -> dict[str, Any]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        for file in self.code_index.files(project):
            node_id = f"module:{file['path']}"
            nodes.append(GraphNode(node_id, "Module", file["path"], {"language": file["language"], "hash": file["hash"]}))
        known = {node.label: node.node_id for node in nodes}
        for dep in self.code_index.dependencies(project):
            target = known.get(dep["target"], f"external:{dep['target']}")
            if target.startswith("external:"):
                nodes.append(GraphNode(target, "Service", dep["target"], {}))
                known[dep["target"]] = target
            edges.append(GraphEdge(f"module:{dep['source']}", target, "depends_on"))
        self.storage.replace(project, [node.as_dict() for node in nodes], [edge.as_dict() for edge in edges])
        return {"project": project, "nodes": [node.as_dict() for node in nodes], "edges": [edge.as_dict() for edge in edges], "readOnly": True}

    def query(self, project: str, keyword: str = "", limit: int = 200) -> dict[str, Any]:
        term = f"%{keyword.strip()}%"
        conn = self.storage.connection
        rows = conn.execute("SELECT * FROM graph_nodes WHERE project=? AND (label LIKE ? OR node_type LIKE ?) ORDER BY label LIMIT ?", (project, term, term, limit)).fetchall()
        nodes = [{"id": row["node_id"], "type": row["node_type"], "label": row["label"], "metadata": __import__("json").loads(row["metadata"])} for row in rows]
        ids = {node["id"] for node in nodes}
        edges = [dict(row) for row in conn.execute("SELECT source,target,relation FROM graph_edges WHERE project=? ORDER BY source,target LIMIT ?", (project, limit)).fetchall() if not ids or row["source"] in ids or row["target"] in ids]
        return {"project": project, "nodes": nodes, "edges": edges, "readOnly": True}
