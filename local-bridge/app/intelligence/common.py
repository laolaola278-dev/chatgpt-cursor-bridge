"""Shared safety helpers for Phase 25 intelligence data.

The intelligence layer is deliberately metadata-only. These helpers make the
boundary explicit: untrusted event metadata is scrubbed before it reaches
SQLite, derived results, audit previews, or knowledge proposals.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.security.sandbox import validate_project_name
from app.security.validator import ValidationFailed


_SENSITIVE_KEY = re.compile(
    r"(?:secret|token|password|passwd|api[_-]?key|authorization|private[_-]?key|credential|cookie|session|database[_-]?url)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+|basic\s+)[A-Za-z0-9._~+/=-]+|(?:sk|pk|ghp|github_pat|xox[baprs])-[-A-Za-z0-9_]+|AKIA[0-9A-Z]{12,}|-----BEGIN [^-]+ PRIVATE KEY-----|\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"
)
_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s\n,;:]+/){1,}[^\s\n,;:]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_project(project: str) -> str:
    value = (project or "").strip()
    validate_project_name(value)
    return value


def sanitize_text(value: Any, *, limit: int = 4000) -> str:
    text = str(value or "")
    text = _SECRET_VALUE.sub("[REDACTED]", text)
    # Do not expose the bridge host's absolute workspace or home path through
    # an intelligence response. Relative source names remain useful evidence.
    text = _ABSOLUTE_PATH.sub("<internal-path>", text)
    return text[:limit]


def sanitize_value(value: Any, *, key: str = "", depth: int = 0) -> Any:
    """Recursively sanitize JSON-like metadata without executing user data."""
    if depth > 8:
        return "[TRUNCATED]"
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {
            str(item_key)[:120]: sanitize_value(item_value, key=str(item_key), depth=depth + 1)
            for item_key, item_value in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(item, depth=depth + 1) for item in list(value)[:100]]
    return sanitize_text(value)


def sanitize_metadata(value: Any) -> dict[str, Any]:
    cleaned = sanitize_value(value if isinstance(value, dict) else {}, depth=0)
    return cleaned if isinstance(cleaned, dict) else {}


def safe_source(value: Any) -> str:
    source = sanitize_text(value, limit=500).strip()
    if not source:
        raise ValidationFailed("Observation source is required")
    # Preserve a useful relative identifier while never returning an absolute
    # host path. PurePath also handles Windows-looking paths in test fixtures.
    if source.startswith("<internal-path>"):
        return source
    if len(source) > 500:
        return source[:500]
    return source


def tokens(*values: Any) -> set[str]:
    text = " ".join(sanitize_text(item, limit=1000).lower() for item in values)
    return {item for item in re.findall(r"[a-z0-9][a-z0-9_.-]{1,}", text) if item not in {"the", "and", "with"}}


def similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    return round(len(left & right) / len(union), 3) if union else 0.0


def bounded_confidence(value: float, *, ceiling: float = 0.95) -> float:
    return round(max(0.0, min(ceiling, float(value))), 3)


def ids(values: list[Any] | None) -> list[str]:
    """Return bounded, secret-scrubbed identifiers for evidence references."""
    result: list[str] = []
    for value in values or []:
        cleaned = sanitize_text(value, limit=300).strip()
        if cleaned and cleaned != "[REDACTED]":
            result.append(cleaned)
    return list(dict.fromkeys(result))
