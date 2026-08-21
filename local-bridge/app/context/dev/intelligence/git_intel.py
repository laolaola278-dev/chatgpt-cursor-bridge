"""Phase 30 · Git Diff Intelligence.

Analyzes the working tree diff (via the existing read-only ``GitContextService``)
to produce a change summary, changed files with added/removed line counts,
changed symbols, affected tests and dependencies, risk indicators and
suggested review points. Never stages, commits, pushes, resets or mutates the
working tree.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.context.dev.budget import ContextBudget
from app.context.dev.dependencies import DependencyContextService
from app.context.dev.git_context import GitContextService

from .index_source import ReadOnlyProjectIndex
from .models import GitDiffAnalysis

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_ADDED = re.compile(r"^\+[^+]")
_REMOVED = re.compile(r"^-[^-]")

_RISK_PATTERNS = [
    (re.compile(r"\b(shell\s*=\s*True|os\.system|subprocess\.call|eval\(|exec\(|pickle\.loads)\b", re.IGNORECASE), "high", "dangerous API usage"),
    (re.compile(r"\b(password|secret|token|api[_-]?key|credential)\b", re.IGNORECASE), "high", "credential-like content"),
    (re.compile(r"\.env|id_rsa|credentials", re.IGNORECASE), "high", "sensitive file touched"),
    (re.compile(r"\b(raw_input|input\(|innerHTML|dangerouslySetInnerHTML)\b"), "medium", "unvalidated input surface"),
    (re.compile(r"\b(TODO|FIXME|HACK|XXX)\b"), "low", "marker left behind"),
    (re.compile(r"\.skip\(|\.only\(|@pytest\.mark\.skip|skipif"), "medium", "test skipped/disabled"),
]


class GitDiffIntelligence:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._git = GitContextService(settings)
        self._index = ReadOnlyProjectIndex(settings)
        self._deps = DependencyContextService(settings)

    def analyze(self, project: str) -> GitDiffAnalysis:
        payload = self._git.build(project, ContextBudget())
        diff_text = payload.get("diff", "")
        changed_files = payload.get("changedFiles", [])

        per_file: list[dict[str, Any]] = []
        added_total = removed_total = 0
        current_file = ""
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if line.startswith("--- a/"):
                continue
            if current_file and current_file not in {item["path"] for item in per_file}:
                per_file.append({"path": current_file, "added": 0, "removed": 0})
            if _ADDED.match(line):
                added_total += 1
                if current_file:
                    for item in per_file:
                        if item["path"] == current_file:
                            item["added"] += 1
            elif _REMOVED.match(line):
                removed_total += 1
                if current_file:
                    for item in per_file:
                        if item["path"] == current_file:
                            item["removed"] += 1

        changed_symbols: list[dict[str, Any]] = []
        changed_set = set(changed_files)
        for row in self._index.symbols(project, "", limit=5000):
            if row["path"] in changed_set:
                changed_symbols.append({"name": row["name"], "type": row["type"], "file": row["path"], "line": row["lineStart"]})
        changed_symbols = changed_symbols[:100]

        affected_tests: list[str] = []
        affected_dependencies: list[str] = []
        for path in changed_files:
            if "test" in path.lower() or "spec" in path.lower():
                affected_tests.append(path)
            if path in ("package.json", "requirements.txt", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml", "Gemfile", "build.gradle"):
                affected_dependencies.append(path)
        # Tests that import or reference changed files.
        known = set(changed_files)
        for row in self._index.symbols(project, "", limit=5000):
            if ("test" in row["path"].lower() or "spec" in row["path"].lower()) and row["path"] not in affected_tests:
                if any(changed in row["path"] for changed in known) or any(part in row["path"] for part in known):
                    affected_tests.append(row["path"])
        affected_tests = sorted(set(affected_tests))[:20]

        risk_indicators: list[dict[str, Any]] = []
        for pattern, severity, label in _RISK_PATTERNS:
            matches = pattern.findall(diff_text)
            if matches:
                risk_indicators.append({"severity": severity, "label": label, "matches": min(len(matches), 50)})

        review_points: list[str] = []
        if per_file:
            review_points.append(f"Review {len(per_file)} changed file(s); verify each change matches the proposal intent.")
        for item in per_file[:10]:
            if item["removed"] == 0:
                review_points.append(f"{item['path']} only adds lines — confirm nothing was deleted unintentionally.")
            if item["added"] > 100:
                review_points.append(f"{item['path']} adds {item['added']} lines — large changes deserve extra review.")
        for risk in risk_indicators[:5]:
            review_points.append(f"High-risk pattern '{risk['label']}' appears {risk['matches']}x — requires explicit human review.")
        if affected_tests:
            review_points.append(f"Affected tests: {', '.join(affected_tests[:5])} — run them through the normal approval-gated test flow.")

        return GitDiffAnalysis(
            project=project,
            change_summary=[
                f"{len(changed_files)} file(s) changed, {added_total} added / {removed_total} removed line(s).",
                f"{len(changed_symbols)} symbol(s) in changed files.",
                f"{len(affected_tests)} test file(s) affected.",
            ],
            changed_files=per_file[:100],
            changed_symbols=changed_symbols,
            affected_tests=affected_tests,
            affected_dependencies=affected_dependencies,
            risk_indicators=risk_indicators,
            review_points=review_points[:20],
            stats={"files": len(changed_files), "added": added_total, "removed": removed_total, "symbols": len(changed_symbols), "tests": len(affected_tests)},
        )
