"""Read-only symbol context.

Reuses the existing Phase 12 ``CodeIndex`` as the canonical symbol store
(function/class/interface/type/enum/variable). Import symbols are derived from
the index's dependency edges (``import`` / ``from_import``) and export flags
from the file text — the parser itself is untouched, so older phases keep
their exact symbol output.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.code_intelligence.index import CodeIndex
from app.code_intelligence.parser import parse_source
from app.code_intelligence.scanner import CodeScanner
from app.config import Settings
from app.security.sandbox import get_project_dir, validate_path

from .budget import ContextBudget
from .security import is_sensitive_path, redact_secrets

_EXPORT_PREFIX = re.compile(r"^\s*export\s+")
#: On-the-fly parse cap when the code index has no data for the project.
FALLBACK_SCAN_FILES = 300


def symbol_id(project: str, path: str, symbol_type: str, name: str, line: int) -> str:
    raw = f"{project}|{path}|{symbol_type}|{name}|{line}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class SymbolContextService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._index = CodeIndex(settings.code_index_db_path)

    def build(self, project: str, *, query: str = "", limit: int | None = None, budget: ContextBudget | None = None) -> dict[str, Any]:
        budget = budget or ContextBudget()
        effective_limit = min(limit or budget.max_symbols, budget.max_symbols)
        term = query.strip().lower()
        if term:
            if self._index.stats(project)["files"] > 0:
                rows = self._index.search(project, term, limit=budget.max_symbols * 4)
            else:
                rows = [row for row in self._all_symbols(project) if term in row["name"].lower() or term in row.get("signature", "").lower() or term in row["path"].lower()]
        else:
            rows = self._all_symbols(project)
        parents = self._parent_map(project, [row for row in rows if row["type"] == "class"])
        symbols = [self._enrich(project, row, parents) for row in rows[:effective_limit]]
        return {"symbols": symbols, "total": len(rows), "truncated": len(rows) > effective_limit}

    def get(self, project: str, target_id: str) -> dict[str, Any] | None:
        for row in self._all_symbols(project):
            if symbol_id(project, row["path"], row["type"], row["name"], row["lineStart"]) == target_id:
                parents = self._parent_map(project, [item for item in self._all_symbols(project) if item["type"] == "class"])
                return self._enrich(project, row, parents)
        return None

    def file_symbols(self, project: str, path: str) -> dict[str, Any]:
        """Symbols + imports + export flag for a single file."""
        rows = [row for row in self._all_symbols(project) if row["path"] == path]
        parents = self._parent_map(project, [row for row in rows if row["type"] == "class"])
        symbols = [self._enrich(project, row, parents) for row in rows]
        imports = sorted({edge["target"] for edge in self._index.dependencies(project, path, limit=500) if edge.get("type") in {"import", "from_import"}})
        exported = any(symbol.get("exported") for symbol in symbols)
        return {"symbols": symbols, "imports": imports, "exported": exported}

    def _all_symbols(self, project: str) -> list[dict[str, Any]]:
        if self._index.stats(project)["files"] > 0:
            return self._index.search(project, "", limit=5000)
        # No indexed data: fall back to a bounded, read-only on-the-fly parse.
        rows: list[dict[str, Any]] = []
        root = get_project_dir(project, self._settings)
        scanner = CodeScanner(self._settings)
        for index, (path, relative) in enumerate(scanner.files(project)):
            if index >= FALLBACK_SCAN_FILES:
                break
            if is_sensitive_path(relative):
                continue
            symbols, _ = parse_source(path, relative)
            for symbol in symbols:
                rows.append(
                    {
                        "path": symbol.path,
                        "type": symbol.symbol_type,
                        "name": symbol.name,
                        "signature": symbol.signature,
                        "lineStart": symbol.line_start,
                        "lineEnd": symbol.line_end,
                    }
                )
        rows.sort(key=lambda row: (row["name"], row["path"]))
        return rows

    def _parent_map(self, project: str, classes: list[dict[str, Any]]) -> dict[str, str | None]:
        by_file: dict[str, list[dict[str, Any]]] = {}
        for row in classes:
            by_file.setdefault(row["path"], []).append(row)
        mapping: dict[str, str | None] = {}
        for path, items in by_file.items():
            for item in items:
                for line in range(item["lineStart"], item["lineEnd"] + 1):
                    mapping.setdefault(f"{path}:{line}", item["name"])
        return mapping

    def _enrich(self, project: str, row: dict[str, Any], parents: dict[str, str | None]) -> dict[str, Any]:
        exported = self._is_exported(project, row["path"], row["lineStart"])
        return {
            "id": symbol_id(project, row["path"], row["type"], row["name"], row["lineStart"]),
            "name": row["name"],
            "type": row["type"],
            "file": row["path"],
            "line": row["lineStart"],
            "endLine": row["lineEnd"],
            "signature": redact_secrets(row.get("signature") or ""),
            "parent": parents.get(f"{row['path']}:{row['lineStart']}"),
            "exported": exported,
        }

    def _is_exported(self, project: str, path: str, line: int) -> bool:
        if is_sensitive_path(path):
            return False
        try:
            target = validate_path(project, path, self._settings, must_exist=True)
        except Exception:
            return False
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        lines = text.splitlines()
        if not 1 <= line <= len(lines):
            return False
        return bool(_EXPORT_PREFIX.match(lines[line - 1]))
