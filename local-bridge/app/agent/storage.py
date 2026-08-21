"""File-backed storage for agent metadata and protocol messages."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.security.validator import ResourceNotFound

from .models import Agent, AgentRole, AgentStatus
from .protocol import AgentMessage


class AgentStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._messages_path = self.root / "messages.jsonl"
        self._lock = Lock()

    @property
    def messages_path(self) -> Path:
        return self._messages_path

    @staticmethod
    def _to_dict(agent: Agent) -> dict:
        return {
            "id": agent.id,
            "project": agent.project,
            "session_id": agent.session_id,
            "role": agent.role.value,
            "model_id": agent.model_id,
            "memory_scope": agent.memory_scope,
            "permissions": list(agent.permissions),
            "status": agent.status.value,
            "workflow_id": agent.workflow_id,
            "stage_id": agent.stage_id,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at,
            "history": list(agent.history),
        }

    @staticmethod
    def _from_dict(data: dict) -> Agent:
        return Agent(
            id=data["id"],
            project=data["project"],
            session_id=data["session_id"],
            role=AgentRole(data["role"]),
            model_id=data["model_id"],
            memory_scope=data["memory_scope"],
            permissions=list(data.get("permissions") or []),
            status=AgentStatus(data["status"]),
            workflow_id=data.get("workflow_id"),
            stage_id=data.get("stage_id"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            history=list(data.get("history") or []),
        )

    def save(self, agent: Agent) -> None:
        target = self.root / f"{agent.id}.json"
        temporary = target.with_suffix(".json.tmp")
        with self._lock:
            temporary.write_text(json.dumps(self._to_dict(agent), ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(target)

    def get(self, agent_id: str) -> Agent:
        path = self.root / f"{agent_id}.json"
        if not path.exists():
            raise ResourceNotFound(f"Agent '{agent_id}' was not found")
        with self._lock:
            return self._from_dict(json.loads(path.read_text(encoding="utf-8")))

    def all(self) -> list[Agent]:
        with self._lock:
            paths = sorted(self.root.glob("ag_*.json"))
        agents: list[Agent] = []
        for path in paths:
            try:
                agents.append(self._from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError):
                continue
        return agents

    def save_message(self, message: AgentMessage) -> None:
        with self._lock:
            with self._messages_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message.as_dict(), ensure_ascii=False) + "\n")

    def messages(self, *, limit: int = 100) -> list[dict[str, object]]:
        if not self._messages_path.exists():
            return []
        with self._lock:
            lines = self._messages_path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, object]] = []
        for line in lines[-max(1, min(limit, 500)) :]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records
