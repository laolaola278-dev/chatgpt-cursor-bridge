from __future__ import annotations

from typing import Any

from app.code_intelligence.dependency import reverse_impact
from app.code_intelligence.index import CodeIndex


class ImpactAnalyzer:
    def __init__(self, index: CodeIndex) -> None:
        self.index = index

    def analyze(self, project: str, changed_files: list[str]) -> dict[str, Any]:
        affected = reverse_impact(self.index, project, changed_files)
        risk = "high" if len(affected) > 20 else "medium" if len(affected) > 5 else "low"
        return {"project": project, "changedFiles": changed_files, "affectedModules": affected, "risk": risk, "readOnly": True}
