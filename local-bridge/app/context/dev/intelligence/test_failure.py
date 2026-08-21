"""Phase 30 · Test Failure Intelligence.

Builds a read-only Test Failure Context from a failed test: locates the test
file, finds related source files / symbols via the existing CodeIndex, and
produces deterministic suggested investigation steps. It never runs tests,
never modifies tests, and never fixes code — the only escape hatch is a Patch
Proposal that must go through ApprovalStore.
"""

from __future__ import annotations

import re

from app.config import Settings
from app.context.dev.security import redact_secrets
from app.context.dev.symbols import SymbolContextService

from .index_source import ReadOnlyProjectIndex
from .models import TestFailureContext

_SYMBOL_HINT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")


class TestFailureAssistant:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._index = ReadOnlyProjectIndex(settings)
        self._symbols = SymbolContextService(settings)

    def build(
        self,
        project: str,
        *,
        test: str,
        failure: str = "",
        expected: str = "",
        actual: str = "",
        traceback: str = "",
    ) -> TestFailureContext:
        test = redact_secrets(test)[:1000]
        failure = redact_secrets(failure)[:4000]
        expected = redact_secrets(expected)[:2000]
        actual = redact_secrets(actual)[:2000]

        test_file: str | None = None
        haystack = f"{test} {failure} {traceback}".lower()
        for row in self._index.files(project):
            if "test" in row["path"].lower() or "spec" in row["path"].lower():
                if test_file is None and (test.lower()[:40] in row["path"].lower() or test.lower() in haystack):
                    test_file = row["path"]
                if test_file is None:
                    test_file = row["path"]

        tokens = set(re.findall(r"[a-z0-9_]{3,}", haystack))
        all_symbols = self._index.symbols(project, "", limit=5000)
        related_symbols: list[dict] = []
        related_paths: set[str] = set()
        for symbol in all_symbols:
            name = symbol["name"].lower()
            if any(token in name for token in tokens) or any(token in symbol["path"].lower() for token in tokens):
                related_symbols.append(symbol)
                related_paths.add(symbol["path"])
        related_symbols = related_symbols[:40]
        related_source = sorted(related_paths)[:20]

        investigation: list[str] = []
        if test_file:
            investigation.append(f"Open the failing test {test_file} and confirm the assertion that produced the mismatch.")
        if expected and actual:
            investigation.append("Compare the expected and actual values; look for a recent change that altered the produced value.")
        for symbol in related_symbols[:5]:
            investigation.append(f"Inspect {symbol['name']} at {symbol['path']}:{symbol['lineStart']} — it matches tokens from the failure.")
        if not related_symbols:
            investigation.append("No symbol matched the failure tokens; search the failure message keywords across the project.")
        investigation.append("If a source change is needed, generate a Patch Proposal and route it through ApprovalStore → Human Approval.")

        return TestFailureContext(
            project=project,
            test=test,
            failure=failure,
            expected=expected,
            actual=actual,
            test_file=test_file,
            related_source=related_source,
            related_symbols=related_symbols,
            suggested_investigation=investigation[:10],
            patch_proposal_only=True,
        )
