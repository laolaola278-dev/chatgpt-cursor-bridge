"""Read-only context bundles for runtime agents."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.config import Settings
from app.git.manager import GitManager
from app.security.sandbox import validate_project_name


class ContextBuilder:
    """Selects context; it has no write methods by design."""

    DOCUMENTS = ("architecture.md", "decisions.md", "tasks.md", "project.md", "changelog.md")

    def __init__(self, settings: Settings) -> None: self.settings = settings

    def build(self, *, project: str, agent_role: str, current_task: str = "") -> dict[str, Any]:
        project = validate_project_name(project)
        memory_dir = self.settings.memory_root / project
        documents: list[dict[str, str]] = []
        role = agent_role.upper()
        names = ("architecture.md", "decisions.md", "tasks.md") if role in {"CODER", "ARCHITECT", "PLANNER"} else ("project.md", "changelog.md", "tasks.md")
        if role == "TESTER": names = ("tasks.md", "changelog.md", "decisions.md")
        for name in names:
            path = memory_dir / name
            if path.is_file():
                content = path.read_text(encoding="utf-8")[-12000:]
                documents.append({"name": name, "content": content})
        diff = ""
        try: diff = str(GitManager(self.settings).diff(project).get("diff", ""))[-12000:]
        except Exception: diff = ""
        if diff: documents.append({"name": "recent.diff", "content": diff})
        summary = f"{role} context for {project}: {len(documents)} read-only document(s)"
        if current_task: summary += f"; task={current_task[:300]}"
        context_id = hashlib.sha256((project + role + current_task + "|".join(item["name"] for item in documents)).encode()).hexdigest()[:20]
        return {"contextId": f"ctx_{context_id}", "project": project, "agentRole": role, "documents": documents, "summary": summary}
