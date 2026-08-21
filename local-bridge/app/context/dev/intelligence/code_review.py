"""Phase 30 · Read-only Code Review Assistant.

Deterministic heuristic review of a file or symbol: correctness,
maintainability, security, performance, error handling, test coverage and
API compatibility. Findings carry a severity (Info/Low/Medium/High/Critical),
a location and a recommendation. Reviews only produce suggestions — the only
way to change code is a Patch Proposal routed through ApprovalStore.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.context.dev.git_context import GitContextService
from app.context.dev.security import is_sensitive_path, redact_secrets
from app.security.sandbox import validate_path

from .index_source import ReadOnlyProjectIndex
from .models import CodeReviewFinding, CodeReviewResult, stable_id

_RULES: list[tuple[str, str, str, re.Pattern, str, str]] = [
    # (category, severity, title, pattern, explanation, recommendation)
    ("security", "Critical", "Shell execution via unsafe shell flag", re.compile(r"shell\s*=\s*True", re.IGNORECASE), "Enabling the shell flag allows shell metacharacter injection.", "Use an argument list with the shell flag disabled and a fixed argv policy."),
    ("security", "High", "Dynamic code execution", re.compile(r"\beval\s*\(|\bexec\s*\(|os\.system\s*\(|subprocess\.call\s*\(", re.IGNORECASE), "Dynamic execution of strings can be dangerous with untrusted input.", "Avoid eval/exec; prefer typed, reviewed alternatives."),
    ("security", "High", "Potential secret assignment", re.compile(r"(?:password|secret|token|api[_-]?key|credential)\s*[:=]\s*[\"']", re.IGNORECASE), "Hard-coded credential-like values may leak secrets.", "Move secrets to environment variables or the project's key store."),
    ("security", "Medium", "Unsafe HTML injection", re.compile(r"innerHTML\s*=|dangerouslySetInnerHTML|v-html", re.IGNORECASE), "Unescaped HTML can enable XSS.", "Escape output or use safe rendering APIs."),
    ("security", "Medium", "Unvalidated user input", re.compile(r"\braw_input\s*\(|\binput\s*\(", re.IGNORECASE), "Direct input without validation can break invariants.", "Validate and constrain input at the boundary."),
    ("error_handling", "Medium", "Bare except swallows errors", re.compile(r"except\s*:", re.IGNORECASE), "A bare except hides the real failure and catches everything.", "Catch specific exception types and log/handle them."),
    ("error_handling", "Medium", "Silent exception pass", re.compile(r"except[^\n]*:\s*\n\s*pass", re.IGNORECASE), "pass in an except block silently ignores failures.", "Handle the error or re-raise after logging."),
    ("maintainability", "Low", "Debug logging left in code", re.compile(r"console\.log\s*\(|print\s*\(.*debug", re.IGNORECASE), "Debug output clutters production logs.", "Remove or gate debug logging behind a flag."),
    ("maintainability", "Info", "Marker comment", re.compile(r"\bTODO\b|\bFIXME\b|\bHACK\b|\bXXX\b"), "Marker comments indicate unfinished work.", "Resolve or track the marker in the task list."),
    ("performance", "Medium", "Potentially unbounded loop", re.compile(r"while\s+True|for\s+[^:]+in\s+range\s*\(\s*\)", re.IGNORECASE), "Unbounded loops can hang or exhaust resources.", "Add explicit bounds and timeout handling."),
    ("performance", "Low", "Repeated import inside function", re.compile(r"^\s{4,}import\s+", re.MULTILINE), "Imports inside functions run on every call.", "Hoist imports to module scope."),
    ("api_compatibility", "Medium", "Public API surface changed", re.compile(r"^(?:export\s+)?(?:class|function|const|let|interface|type|enum)\s+\w+", re.MULTILINE), "Public declaration may be consumed elsewhere.", "Check callers and update them or keep backward compatibility."),
]


class CodeReviewAssistant:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._index = ReadOnlyProjectIndex(settings)
        self._git = GitContextService(settings)

    def review(self, project: str, *, file: str | None = None, symbol: str | None = None, selection: str = "", diff: str = "") -> CodeReviewResult:
        content = selection
        target = "selection"
        if not content and file:
            target = file
            if is_sensitive_path(file):
                content = ""
            else:
                try:
                    path = validate_path(project, file, self._settings, must_exist=True)
                    content = path.read_text(encoding="utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    content = ""
        if not content and symbol:
            for row in self._index.symbols(project, "", limit=5000):
                if row["name"] == symbol:
                    target = f"{row['path']}:{row['lineStart']}"
                    try:
                        path = validate_path(project, row["path"], self._settings, must_exist=True)
                        content = path.read_text(encoding="utf-8", errors="replace")
                    except Exception:  # noqa: BLE001
                        content = ""
                    break
        if diff:
            content = f"{content}\n{diff}"

        content = redact_secrets(content)
        findings: list[CodeReviewFinding] = []
        lines = content.splitlines()
        for category, severity, title, pattern, explanation, recommendation in _RULES:
            for index, line in enumerate(lines, start=1):
                if pattern.search(line):
                    findings.append(
                        CodeReviewFinding(
                            id=stable_id(project, target, category, title, str(index)),
                            severity=severity,
                            category=category,
                            location=f"{target}:{index}",
                            title=title,
                            explanation=explanation,
                            recommendation=recommendation,
                        )
                    )
                    break  # one finding per rule per file

        # Test coverage heuristic: a source file with no test/spec sibling.
        if file and not findings:
            has_test = any(
                "test" in row["path"].lower() or "spec" in row["path"].lower()
                for row in self._index.files(project)
                if file.rsplit("/", 1)[-1].rsplit(".", 1)[0] in row["path"]
            )
            if not has_test:
                findings.append(
                    CodeReviewFinding(
                        id=stable_id(project, target, "test_coverage", "No test sibling", "0"),
                        severity="Info",
                        category="test_coverage",
                        location=target,
                        title="No test file found for this module",
                        explanation="Changed source without a matching test increases regression risk.",
                        recommendation="Add or extend a test through the normal workflow, or record a test-coverage gap.",
                    )
                )

        findings.sort(key=lambda finding: ("Critical", "High", "Medium", "Low", "Info").index(finding.severity))
        summary = f"{len(findings)} finding(s) for {target}."
        return CodeReviewResult(
            project=project,
            target=target,
            findings=findings[:50],
            summary=summary,
            patch_proposal_only=True,
        )
