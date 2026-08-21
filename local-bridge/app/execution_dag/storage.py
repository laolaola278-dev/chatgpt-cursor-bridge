from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import DagEdge, DagStatus, DependencyType, ExecutionDag


class ExecutionDagStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS execution_dags (
                id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                loop_ids_json TEXT NOT NULL,
                edges_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                history_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS execution_dag_project ON execution_dags(project, updated_at);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def save(self, dag: ExecutionDag) -> None:
        self.connection.execute(
            """
            INSERT INTO execution_dags (
                id, project, loop_ids_json, edges_json, status, created_at, updated_at, history_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              project=excluded.project,
              loop_ids_json=excluded.loop_ids_json,
              edges_json=excluded.edges_json,
              status=excluded.status,
              updated_at=excluded.updated_at,
              history_json=excluded.history_json
            """,
            (
                dag.id,
                dag.project,
                json.dumps(dag.loop_ids, ensure_ascii=False),
                json.dumps([edge.as_dict() for edge in dag.edges], ensure_ascii=False),
                dag.status.value,
                dag.created_at,
                dag.updated_at,
                json.dumps(dag.history, ensure_ascii=False),
            ),
        )
        self.connection.commit()

    @staticmethod
    def _dag(row: sqlite3.Row) -> ExecutionDag:
        edges = [
            DagEdge(
                source_loop=item["sourceLoop"],
                target_loop=item["targetLoop"],
                dependency_type=DependencyType(item["dependencyType"]),
            )
            for item in json.loads(row["edges_json"])
        ]
        return ExecutionDag(
            id=row["id"],
            project=row["project"],
            loop_ids=json.loads(row["loop_ids_json"]),
            edges=edges,
            status=DagStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            history=json.loads(row["history_json"] or "[]"),
        )

    def get(self, dag_id: str) -> ExecutionDag | None:
        row = self.connection.execute("SELECT * FROM execution_dags WHERE id=?", (dag_id,)).fetchone()
        return self._dag(row) if row else None

    def list_dags(self, project: str | None = None, limit: int = 200) -> list[ExecutionDag]:
        if project:
            rows = self.connection.execute("SELECT * FROM execution_dags WHERE project=? ORDER BY updated_at DESC LIMIT ?", (project, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM execution_dags ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._dag(row) for row in rows]
