"""Durable runtime state store."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from app.security.validator import ResourceNotFound

from .models import AgentRuntime, RuntimeState


class RuntimeStateStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path(self, runtime_id: str) -> Path: return self.root / f"{runtime_id}.json"

    def save(self, runtime: AgentRuntime) -> AgentRuntime:
        path, temp = self._path(runtime.id), self._path(runtime.id + ".tmp")
        with self._lock:
            temp.write_text(json.dumps(runtime.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, path)
        return runtime

    def get(self, runtime_id: str) -> AgentRuntime:
        path = self._path(runtime_id)
        if not path.exists(): raise ResourceNotFound(f"Runtime '{runtime_id}' was not found")
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"Runtime '{runtime_id}' is corrupted") from exc
        return AgentRuntime(value["id"], value["agentId"], value["sessionId"], value["workflowId"], value["stageId"], RuntimeState(value["state"]), value["createdAt"], value["updatedAt"], list(value.get("history", [])))

    def list(self) -> list[AgentRuntime]:
        records: list[AgentRuntime] = []
        for path in sorted(self.root.glob("rt_*.json")):
            try: records.append(self.get(path.stem))
            except (ValueError, ResourceNotFound): continue
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def running(self) -> list[AgentRuntime]: return [item for item in self.list() if item.state is RuntimeState.RUNNING]
