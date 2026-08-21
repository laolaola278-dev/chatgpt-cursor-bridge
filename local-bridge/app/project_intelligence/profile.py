from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.code_intelligence.analyzer import CodeAnalyzer
from app.code_intelligence.index import CodeIndex


@dataclass(frozen=True)
class ProjectProfile:
    project_id: str
    languages: dict[str, int]
    frameworks: list[str]
    architecture_summary: str
    module_count: int
    complexity_score: int

    def as_dict(self) -> dict[str, Any]:
        return {"projectId": self.project_id, "languages": self.languages, "frameworks": self.frameworks, "architectureSummary": self.architecture_summary, "moduleCount": self.module_count, "complexityScore": self.complexity_score, "readOnly": True}


class ProjectProfileService:
    def __init__(self, index: CodeIndex) -> None:
        self.index = index

    def build(self, project: str) -> ProjectProfile:
        data = CodeAnalyzer(self.index).profile_data(project)
        return ProjectProfile(project, data["languages"], data["frameworks"], data["architectureSummary"], data["moduleCount"], data["complexityScore"])
