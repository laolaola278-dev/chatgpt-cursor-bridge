"""Phase 30 · Code Relationship Analysis.

Reads the existing Phase 12 ``CodeIndex`` (the canonical symbol / dependency
store) to derive imports, importers, callers, callees, references and related
files for a target file or symbol. The Engineering Graph / Code Index is never
mutated here — this module is strictly read-only.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import Settings

from .index_source import ReadOnlyProjectIndex
from .models import RelationshipReport


def _module_names(path: str) -> set[str]:
    """Map a project path to module-style names (auth.service, src/auth/service...)."""
    normalized = path.replace("\\", "/").lstrip("./")
    stem = normalized[:-3] if normalized.endswith(".py") else normalized
    names = {stem}
    if stem.startswith("src/"):
        names.add(stem[4:])
    names.add(stem.rsplit("/", 1)[-1])
    dotted = stem.replace("/", ".")
    names.add(dotted)
    if dotted.startswith("src."):
        names.add(dotted[4:])
    return names


class RelationshipAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._index = ReadOnlyProjectIndex(settings)

    def analyze(self, project: str, *, file: str | None = None, symbol: str | None = None) -> RelationshipReport:
        rows = self._index.symbols(project, "", limit=5000)
        deps = self._index.dependencies(project, limit=2000)

        if symbol:
            matches = [row for row in rows if row["name"].lower() == symbol.lower()]
            if not matches:
                matches = [row for row in rows if symbol.lower() in row["name"].lower()]
        elif file:
            matches = [row for row in rows if row["path"] == file]
        else:
            matches = []

        target_file = file or (matches[0]["path"] if matches else "")
        imports: list[dict[str, Any]] = []
        importers: list[dict[str, Any]] = []
        if target_file:
            target_modules = _module_names(target_file)
            for dep in deps:
                if dep["source"] == target_file and dep["type"] in ("import", "from_import"):
                    imports.append({"name": dep["target"], "kind": "import", "file": target_file, "line": 0, "direction": "import"})
                if dep["type"] in ("import", "from_import") and (dep["target"] == target_file or dep["target"] in target_modules):
                    importers.append({"name": dep["source"], "kind": "importer", "file": dep["source"], "line": 0, "direction": "import"})

        target_names = {match["name"] for match in matches}
        callers: list[dict[str, Any]] = []
        callees: list[dict[str, Any]] = []
        for row in rows:
            if row["name"] in target_names and row["path"] != target_file:
                callers.append({"name": row["name"], "kind": row["type"], "file": row["path"], "line": row["lineStart"], "direction": "caller"})

        if target_names:
            # Callees: symbols referenced by name inside the target file(s).
            try:
                from app.security.sandbox import get_project_dir, validate_path
                from pathlib import Path

                target = validate_path(project, target_file, self._settings, must_exist=False)
                root = get_project_dir(project, self._settings)
                full = root / target
                if full.exists():
                    text = full.read_text(encoding="utf-8", errors="replace")
                    for row in rows:
                        if row["name"] in target_names:
                            continue
                        if re.search(rf"\b{re.escape(row['name'])}\s*\(", text):
                            callees.append({"name": row["name"], "kind": row["type"], "file": row["path"], "line": row["lineStart"], "direction": "callee"})
            except Exception:  # noqa: BLE001 - relationship analysis degrades gracefully
                callees = []

        references: list[dict[str, Any]] = []
        related_files: list[str] = []
        if target_names:
            seen: set[str] = set()
            for row in rows:
                if row["name"] in target_names and row["path"] not in seen:
                    seen.add(row["path"])
                    references.append({"name": row["name"], "kind": row["type"], "file": row["path"], "line": row["lineStart"], "direction": "reference"})
            related_files = sorted(seen)

        return RelationshipReport(
            project=project,
            target=symbol or target_file,
            imports=imports[:200],
            importers=importers[:200],
            callers=callers[:200],
            callees=callees[:200],
            references=references[:200],
            related_files=related_files[:100],
        )
