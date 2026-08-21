"""Phase 30 · Read-only project index source.

Prefer the Phase 12 ``CodeIndex`` when it has data for a project; otherwise
fall back to a bounded, read-only on-the-fly scan (mirroring Phase 29's
symbol service). Never writes the index, never executes project code.
"""

from __future__ import annotations

from typing import Any

from app.code_intelligence.index import CodeIndex
from app.code_intelligence.parser import language_for, parse_source
from app.code_intelligence.scanner import CodeScanner
from app.config import Settings
from app.context.dev.security import is_sensitive_path

FALLBACK_SCAN_FILES = 300


class ReadOnlyProjectIndex:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._index = CodeIndex(settings.code_index_db_path)
        self._scanner = CodeScanner(settings)

    def _indexed(self, project: str) -> bool:
        try:
            return self._index.stats(project)["files"] > 0
        except Exception:  # noqa: BLE001
            return False

    def known_paths(self, project: str) -> set[str]:
        if self._indexed(project):
            return {row["path"] for row in self._index.files(project, limit=5000)}
        paths: set[str] = set()
        try:
            for _path, relative in self._scanner.files(project):
                if is_sensitive_path(relative):
                    continue
                paths.add(relative)
        except Exception:  # noqa: BLE001 - unknown project degrades to empty
            return set()
        return paths

    def files(self, project: str) -> list[dict[str, Any]]:
        if self._indexed(project):
            return self._index.files(project, limit=5000)
        files: list[dict[str, Any]] = []
        try:
            for path, relative in self._scanner.files(project):
                if is_sensitive_path(relative):
                    continue
                files.append({"path": relative, "language": language_for(path)})
        except Exception:  # noqa: BLE001 - unknown project degrades to empty
            return []
        return files

    def symbols(self, project: str, query: str = "", limit: int = 5000) -> list[dict[str, Any]]:
        if self._indexed(project):
            return self._index.search(project, query, limit=limit)
        term = query.strip().lower()
        rows: list[dict[str, Any]] = []
        try:
            for count, (path, relative) in enumerate(self._scanner.files(project)):
                if count >= FALLBACK_SCAN_FILES:
                    break
                if is_sensitive_path(relative):
                    continue
                symbols, _ = parse_source(path, relative)
                for symbol in symbols:
                    if term and term not in symbol.name.lower() and term not in (symbol.signature or "").lower() and term not in relative.lower():
                        continue
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
        except Exception:  # noqa: BLE001 - unknown project degrades to empty
            return []
        rows.sort(key=lambda row: (row["name"], row["path"]))
        return rows

    def dependencies(self, project: str, path: str | None = None, limit: int = 2000) -> list[dict[str, Any]]:
        if self._indexed(project):
            return self._index.dependencies(project, path=path, limit=limit)
        deps: list[dict[str, Any]] = []
        try:
            for count, (path_obj, relative) in enumerate(self._scanner.files(project)):
                if count >= FALLBACK_SCAN_FILES:
                    break
                if is_sensitive_path(relative):
                    continue
                _, dep_records = parse_source(path_obj, relative)
                for dep in dep_records:
                    if path and dep.source != path and dep.target != path:
                        continue
                    deps.append({"source": dep.source, "target": dep.target, "type": dep.dependency_type})
        except Exception:  # noqa: BLE001 - unknown project degrades to empty
            return []
        deps.sort(key=lambda row: (row["source"], row["target"]))
        return deps[:limit]
