from __future__ import annotations

from typing import Any

from app.code_intelligence.index import CodeIndex
from app.impact.analyzer import ImpactAnalyzer
from .project import ProjectMemory


class ContextQueryEngine:
    def __init__(self, index: CodeIndex, project_memory: ProjectMemory) -> None:
        self.index = index
        self.project_memory = project_memory

    def query(self, project: str, agent_role: str, query: str, changed_files: list[str] | None = None) -> dict[str, Any]:
        role = agent_role.strip().upper()
        symbols = self.index.search(project, query, limit=50) if query else self.index.files(project, limit=50)
        impact = ImpactAnalyzer(self.index).analyze(project, changed_files or []) if changed_files else None
        return {"project": project, "agentRole": role, "query": query, "files": symbols, "memory": self.project_memory.history(project, 20), "impact": impact, "readOnly": True}
