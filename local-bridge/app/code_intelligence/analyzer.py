from __future__ import annotations

from collections import Counter
from typing import Any

from .index import CodeIndex


class CodeAnalyzer:
    def __init__(self, index: CodeIndex) -> None:
        self.index = index

    def profile_data(self, project: str) -> dict[str, Any]:
        files = self.index.files(project)
        stats = self.index.stats(project)
        languages = Counter(item["language"] for item in files)
        frameworks: list[str] = []
        paths = " ".join(item["path"] for item in files).lower()
        if "fastapi" in paths or any(item["path"].endswith("main.py") for item in files): frameworks.append("FastAPI/Python")
        if "package.json" in paths or any(item["language"] in {"TypeScript", "JavaScript"} for item in files): frameworks.append("TypeScript/JavaScript")
        complexity = min(100, stats["symbols"] + stats["dependencies"] * 2 + stats["files"])
        architecture = "layered" if any(token in paths for token in ("/api/", "/service", "/manager", "/storage")) else "modular"
        return {"languages": dict(languages), "frameworks": frameworks, "architectureSummary": architecture, "moduleCount": stats["files"], "complexityScore": complexity}
