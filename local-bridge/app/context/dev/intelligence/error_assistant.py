"""Phase 30 · Error Context Assistant.

Given an error message and/or stack trace, build a read-only Error Context
Bundle: source location, related files, related symbols, dependencies, recent
diff and relevant tests. All user-supplied text is sanitized: secrets are
redacted and absolute workspace paths are replaced with a relative display so
stack traces never leak unnecessary absolute paths.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.context.dev.budget import ContextBudget
from app.context.dev.git_context import GitContextService
from app.context.dev.security import redact_secrets
from app.context.dev.symbols import SymbolContextService
from app.security.sandbox import get_project_dir

from .index_source import ReadOnlyProjectIndex
from .models import ErrorContextBundle

_FILE_RE = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|cpp|h|hpp))")
_LINE_RE = re.compile(r"(?:line\s+(\d+)|:(\d+)(?::\d+)?)")

_PYTHON_EXC = re.compile(r"\b(?:Traceback|Error|Exception|raise)\b")
_HTTP_EXC = re.compile(r"\b(?:HTTP|status\s+code|4\d\d|5\d\d)\b")
_TYPESCRIPT_EXC = re.compile(r"\b(?:TS\d+|TypeScript|Cannot find name|Property .* does not exist)\b")
_BUILD_EXC = re.compile(r"\b(?:build failed|Compilation failed|error TS|Module not found|Cannot resolve)\b")
_TEST_EXC = re.compile(r"\b(?:assert|AssertionError|FAILED|failed test|tests? failed)\b")


def classify_error(error: str, stack_trace: str = "") -> str:
    haystack = f"{error} {stack_trace}"
    if _TEST_EXC.search(haystack):
        return "test_failure"
    if _HTTP_EXC.search(haystack):
        return "http_error"
    if _TYPESCRIPT_EXC.search(haystack):
        return "typescript_error"
    if _BUILD_EXC.search(haystack):
        return "build_error"
    if _PYTHON_EXC.search(haystack):
        return "python_exception"
    return "generic"


def sanitize_stack_trace(text: str, workspace_root) -> tuple[str, bool]:
    """Replace the workspace root prefix and redact secrets.

    Returns (sanitized, changed).
    """
    root = str(workspace_root)
    changed = False
    sanitized = text
    if root and root.replace("\\", "/") in sanitized.replace("\\", "/"):
        sanitized = sanitized.replace(root, "<workspace>")
        changed = True
    redacted = redact_secrets(sanitized)
    if redacted != sanitized:
        changed = True
    return redacted, changed


class ErrorContextAssistant:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._index = ReadOnlyProjectIndex(settings)
        self._symbols = SymbolContextService(settings)
        self._git = GitContextService(settings)

    def build(
        self,
        project: str,
        *,
        error: str,
        stack_trace: str = "",
        test_failure: str = "",
        file: str | None = None,
    ) -> ErrorContextBundle:
        workspace = get_project_dir(project, self._settings)
        sanitized_trace, trace_changed = sanitize_stack_trace(stack_trace, workspace)
        sanitized_error = redact_secrets(error)
        kind = classify_error(error, stack_trace or test_failure)

        known_paths = self._index.known_paths(project)
        found_files: list[str] = []
        location: dict[str, Any] | None = None
        for match in _FILE_RE.finditer(f"{sanitized_error} {sanitized_trace}"):
            candidate = match.group(1).lstrip("./")
            if candidate in known_paths:
                found_files.append(candidate)
                line = None
                after = sanitized_trace[match.end() : match.end() + 120]
                line_match = _LINE_RE.search(after)
                if line_match:
                    line = int(line_match.group(1) or line_match.group(2) or 0)
                if location is None:
                    location = {"path": candidate, "line": line}

        if file and file in known_paths:
            found_files.append(file)
            location = location or {"path": file, "line": None}

        related_symbols: list[dict[str, Any]] = []
        for path in found_files[:5]:
            info = self._symbols.file_symbols(project, path)
            related_symbols.extend(info["symbols"][:8])

        root = workspace
        dependencies: list[dict[str, Any]] = []
        try:
            from app.context.dev.dependencies import DependencyContextService

            deps = DependencyContextService(self._settings).build(project, ContextBudget())
            dependencies = deps.get("dependencies", [])[:20]
        except Exception:  # noqa: BLE001 - dependency context degrades gracefully
            dependencies = []

        git_payload = self._git.build(project, ContextBudget())
        recent_diff = git_payload.get("changedFiles", [])

        error_tokens = set(re.findall(r"[a-z0-9_]{3,}", f"{sanitized_error} {test_failure}".lower()))
        relevant_tests: list[str] = [
            row["path"] for row in self._index.files(project) if "test" in row["path"].lower() or "spec" in row["path"].lower()
        ]
        relevant_tests.sort()
        # Prefer tests that mention the failing symbol/file.
        ranked_tests = sorted(relevant_tests, key=lambda path: sum(1 for token in error_tokens if token in path.lower()), reverse=True)

        return ErrorContextBundle(
            project=project,
            error=sanitized_error[:4000],
            kind=kind,
            source_location=location,
            related_files=sorted(set(found_files))[:20],
            related_symbols=related_symbols[:40],
            dependencies=dependencies,
            recent_diff=recent_diff[:20],
            relevant_tests=ranked_tests[:10],
            sanitized=True,
            absolute_paths_removed=trace_changed,
            secrets_redacted=sanitized_error != error or trace_changed,
        )
