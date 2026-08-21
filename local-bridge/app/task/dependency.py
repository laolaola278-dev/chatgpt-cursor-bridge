"""Task dependency graph with deterministic cycle detection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from app.audit.logger import AuditLogger
from app.security.validator import ApprovalError, ValidationFailed


@dataclass(frozen=True)
class TaskDependency:
    source_task: str
    target_task: str
    dependency_type: str

    def as_dict(self) -> dict[str, str]: return {"sourceTask": self.source_task, "targetTask": self.target_task, "dependencyType": self.dependency_type}


class DependencyCycleError(ValidationFailed): pass


class TaskDependencyGraph:
    ALLOWED_TYPES = {"depends_on", "blocks", "requires_review"}

    def __init__(self, path: str | Path | None = None, audit: AuditLogger | None = None) -> None:
        self.path = Path(path) if path else None
        if self.path: self.path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = audit; self._lock = Lock(); self._edges: list[TaskDependency] = []
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists(): return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line); self._edges.append(TaskDependency(item["sourceTask"], item["targetTask"], item["dependencyType"]))
            except (json.JSONDecodeError, KeyError, TypeError): continue

    def _has_path(self, start: str, target: str, edges: list[TaskDependency] | None = None) -> bool:
        adjacency: dict[str, set[str]] = {}
        for edge in edges or self._edges: adjacency.setdefault(edge.source_task, set()).add(edge.target_task)
        seen: set[str] = set(); stack = [start]
        while stack:
            node = stack.pop()
            if node == target: return True
            if node in seen: continue
            seen.add(node); stack.extend(adjacency.get(node, ()))
        return False

    def add(self, *, source_task: str, target_task: str, dependency_type: str = "depends_on") -> TaskDependency:
        source_task, target_task = source_task.strip(), target_task.strip(); dependency_type = dependency_type.strip().lower()
        if not source_task or not target_task or source_task == target_task: raise DependencyCycleError("Dependency endpoints must be distinct")
        if dependency_type not in self.ALLOWED_TYPES: raise ValidationFailed("Unknown dependency type")
        edge = TaskDependency(source_task, target_task, dependency_type)
        with self._lock:
            if edge in self._edges: return edge
            if self._has_path(target_task, source_task, self._edges + [edge]): raise DependencyCycleError("Task dependency would create a cycle")
            self._edges.append(edge)
            if self.path:
                with self.path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(edge.as_dict(), ensure_ascii=False) + "\n")
        if self.audit: self.audit.record(action="task_dependency_added", path=f"task/{source_task}->{target_task}", permission="LEVEL_1", approved=True, result="success", detail=dependency_type)
        return edge

    def list(self, task_id: str | None = None) -> list[TaskDependency]:
        if task_id is None: return list(self._edges)
        return [edge for edge in self._edges if edge.source_task == task_id or edge.target_task == task_id]

    def dependencies_for(self, task_id: str) -> list[TaskDependency]: return [edge for edge in self._edges if edge.target_task == task_id]
    def dependents_for(self, task_id: str) -> list[TaskDependency]: return [edge for edge in self._edges if edge.source_task == task_id]
    def has_cycle(self) -> bool: return any(self._has_path(edge.target_task, edge.source_task, self._edges[:index] + self._edges[index + 1:]) for index, edge in enumerate(self._edges))
    def as_dict(self, task_id: str | None = None) -> dict[str, Any]: return {"taskId": task_id, "dependencies": [edge.as_dict() for edge in self.list(task_id)], "hasCycle": self.has_cycle()}
