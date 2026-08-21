"""Shared pytest fixtures: isolated workspace + FastAPI test client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.audit.logger import reset_audit_logger
from app.config import reset_settings_cache
from app.main import reset_workflow_storage_cache
from app.security.permissions import reset_approval_store


@dataclass
class Bridge:
    client: TestClient
    projects_root: Path
    logs_root: Path
    demo: Path
    memory_root: Path
    workflow_root: Path
    rollback_root: Path

    def audit_entries(self) -> list[dict]:
        log_file = self.logs_root / "audit.jsonl"
        if not log_file.exists():
            return []
        return [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def approve(self, request_id: str):
        """Approve a pending request and return the response."""
        return self.client.post("/permission/approve", json={"request_id": request_id})

    def submit_and_approve(self, endpoint: str, payload: dict):
        """POST a Level 1 endpoint then approve it. Returns (pending, executed)."""
        pending = self.client.post(endpoint, json=payload)
        if pending.status_code != 202:
            return pending, None
        return pending, self.approve(pending.json()["requestId"])

    def memory_dir(self, project: str) -> Path:
        return self.memory_root / project


def _reset_caches() -> None:
    reset_settings_cache()
    reset_audit_logger()
    reset_approval_store()
    reset_workflow_storage_cache()


@pytest.fixture()
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Bridge]:
    projects_root = tmp_path / "workspace" / "projects"
    logs_root = tmp_path / "workspace" / "logs"
    memory_root = tmp_path / "workspace" / "memory"
    workflow_root = tmp_path / "workspace" / "workflows"
    rollback_root = tmp_path / "workspace" / "rollback"
    approval_db = tmp_path / "workspace" / "approvals" / "approvals.db"
    context_root = tmp_path / "workspace" / "context"
    backup_root = tmp_path / "workspace" / "backups"
    session_root = tmp_path / "workspace" / "sessions"
    agent_root = tmp_path / "workspace" / "agents"
    event_root = tmp_path / "workspace" / "events"
    message_root = tmp_path / "workspace" / "messages"
    runtime_root = tmp_path / "workspace" / "runtimes"
    task_db = tmp_path / "workspace" / "tasks" / "task.db"
    code_index_db = tmp_path / "workspace" / "code" / "code_index.db"
    knowledge_graph_db = tmp_path / "workspace" / "knowledge" / "knowledge_graph.db"
    intelligence_db = tmp_path / "workspace" / "intelligence" / "intelligence.db"
    simulation_db = tmp_path / "workspace" / "simulation" / "simulation.db"
    execution_db = tmp_path / "workspace" / "execution" / "execution.db"
    execution_loop_db = tmp_path / "workspace" / "execution" / "execution_loop.db"
    execution_dag_db = tmp_path / "workspace" / "execution" / "execution_dag.db"
    agent_profile_db = tmp_path / "workspace" / "agents" / "agent_profile.db"
    execution_snapshots = tmp_path / "workspace" / "execution_snapshots"
    projects_root.mkdir(parents=True)
    logs_root.mkdir(parents=True)
    memory_root.mkdir(parents=True)
    workflow_root.mkdir(parents=True)
    rollback_root.mkdir(parents=True)
    context_root.mkdir(parents=True)
    backup_root.mkdir(parents=True)
    session_root.mkdir(parents=True)
    agent_root.mkdir(parents=True)
    event_root.mkdir(parents=True)
    message_root.mkdir(parents=True)
    runtime_root.mkdir(parents=True)
    task_db.parent.mkdir(parents=True)
    code_index_db.parent.mkdir(parents=True)
    knowledge_graph_db.parent.mkdir(parents=True)
    intelligence_db.parent.mkdir(parents=True)
    simulation_db.parent.mkdir(parents=True)
    execution_db.parent.mkdir(parents=True)
    execution_snapshots.mkdir(parents=True)

    monkeypatch.setenv("WORKSPACE_ROOT", str(projects_root))
    monkeypatch.setenv("LOG_PATH", str(logs_root))
    monkeypatch.setenv("MEMORY_ROOT", str(memory_root))
    monkeypatch.setenv("WORKFLOW_ROOT", str(workflow_root))
    monkeypatch.setenv("ROLLBACK_ROOT", str(rollback_root))
    monkeypatch.setenv("CONTEXT_ROOT", str(context_root))
    monkeypatch.setenv("BACKUP_ROOT", str(backup_root))
    monkeypatch.setenv("APPROVAL_DB_PATH", str(approval_db))
    monkeypatch.setenv("SESSION_ROOT", str(session_root))
    monkeypatch.setenv("AGENT_ROOT", str(agent_root))
    monkeypatch.setenv("EVENT_ROOT", str(event_root))
    monkeypatch.setenv("MESSAGE_ROOT", str(message_root))
    monkeypatch.setenv("RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("TASK_DB_PATH", str(task_db))
    monkeypatch.setenv("CODE_INDEX_DB_PATH", str(code_index_db))
    monkeypatch.setenv("KNOWLEDGE_GRAPH_DB_PATH", str(knowledge_graph_db))
    monkeypatch.setenv("INTELLIGENCE_DB_PATH", str(intelligence_db))
    monkeypatch.setenv("SIMULATION_DB_PATH", str(simulation_db))
    monkeypatch.setenv("EXECUTION_DB_PATH", str(execution_db))
    monkeypatch.setenv("EXECUTION_LOOP_DB_PATH", str(execution_loop_db))
    monkeypatch.setenv("EXECUTION_DAG_DB_PATH", str(execution_dag_db))
    monkeypatch.setenv("AGENT_PROFILE_DB_PATH", str(agent_profile_db))
    monkeypatch.setenv("EXECUTION_SNAPSHOT_ROOT", str(execution_snapshots))
    monkeypatch.setenv("TEST_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("TEST_MAX_OUTPUT_KB", "4")
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "1")
    monkeypatch.setenv("MAX_TREE_DEPTH", "3")
    monkeypatch.setenv("MAX_MEMORY_APPEND_KB", "16")
    _reset_caches()

    demo = projects_root / "demo"
    (demo / "src").mkdir(parents=True)
    (demo / "src" / "main.py").write_text("print('hello')\nprint('world')\n", encoding="utf-8")
    (demo / "README.md").write_text("# demo\n", encoding="utf-8")
    (demo / "node_modules").mkdir()
    (demo / "node_modules" / "junk.js").write_text("junk", encoding="utf-8")
    (demo / ".git").mkdir()
    (demo / ".git" / "config").write_text("[core]", encoding="utf-8")

    # A secret that lives outside of the workspace sandbox.
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield Bridge(
            client=client,
            projects_root=projects_root,
            logs_root=logs_root,
            demo=demo,
            memory_root=memory_root,
            workflow_root=workflow_root,
            rollback_root=rollback_root,
        )

    _reset_caches()


@pytest.fixture()
def outside_secret(tmp_path: Path) -> Path:
    return tmp_path / "secret.txt"
