"""Context budgets for developer context bundles.

Every bounded read (file, symbol list, diff, dependency list, bundle) goes
through these limits. When a limit is exceeded the payload is truncated and
``truncated=True`` is set; nothing is silently sent in full.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

#: Default per-file read limit for context bundles (bytes).
DEFAULT_MAX_FILE_BYTES = 256 * 1024
#: Default maximum number of symbols in one context payload.
DEFAULT_MAX_SYMBOLS = 500
#: Default maximum number of dependency entries in one context payload.
DEFAULT_MAX_DEPENDENCIES = 200
#: Default maximum number of files listed in one context payload.
DEFAULT_MAX_FILES = 200
#: Default maximum diff size (bytes) included in Git context.
DEFAULT_MAX_DIFF_BYTES = 64 * 1024
#: Default maximum total bundle size (bytes) before truncation.
DEFAULT_MAX_BUNDLE_BYTES = 512 * 1024
#: Default maximum number of recent commits surfaced in Git context.
DEFAULT_MAX_COMMITS = 10
#: Default maximum number of manifest/dependency files scanned.
DEFAULT_MAX_MANIFEST_FILES = 20


@dataclass(frozen=True)
class ContextBudget:
    """Tunable limits for one developer context bundle."""

    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_symbols: int = DEFAULT_MAX_SYMBOLS
    max_dependencies: int = DEFAULT_MAX_DEPENDENCIES
    max_files: int = DEFAULT_MAX_FILES
    max_diff_bytes: int = DEFAULT_MAX_DIFF_BYTES
    max_bundle_bytes: int = DEFAULT_MAX_BUNDLE_BYTES
    max_commits: int = DEFAULT_MAX_COMMITS
    max_manifest_files: int = DEFAULT_MAX_MANIFEST_FILES

    def with_limits(self, **overrides: int) -> "ContextBudget":
        return replace(self, **overrides)


def truncate_bytes(text: str, limit: int, marker: str = "\n... [context truncated]") -> tuple[str, bool]:
    """Truncate ``text`` to ``limit`` bytes; return ``(text, truncated)``."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text, False
    head = raw[: max(0, limit - len(marker.encode("utf-8")))]
    return head.decode("utf-8", errors="replace") + marker, True


def budget_report(
    *,
    project: str,
    agent: str,
    context_type: str,
    payload: dict[str, Any],
    budget: ContextBudget,
) -> dict[str, Any]:
    """Wrap a context payload in the standard bundle envelope."""
    encoded = __import__("json").dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    size = len(encoded)
    truncated = size > budget.max_bundle_bytes
    if truncated:
        payload = {"message": "Context bundle exceeded the size budget and was truncated.", "truncated": True, **payload}
    return {
        "source": "context/dev",
        "project": project,
        "agent": agent,
        "contextType": context_type,
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "size": size,
        "truncated": truncated,
        "securityFiltering": True,
        "data": payload,
    }
