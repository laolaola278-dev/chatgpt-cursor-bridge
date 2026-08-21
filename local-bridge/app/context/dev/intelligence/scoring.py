"""Phase 30 · Deterministic context relevance scoring.

Scores a context candidate against a user query plus optional signals
(selected code, error message, test failure, recent git diff). Every signal
contributes a bounded, explainable delta so the final score stays in [0, 1]
and the reasons can be surfaced in the UI ("why this context?").
"""

from __future__ import annotations

import re
from typing import Iterable

from .models import ContextCandidate

_TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN.findall((text or "").lower()) if len(token) > 1]


def _overlap(tokens: list[str], haystack: str) -> int:
    lowered = haystack.lower()
    return sum(1 for token in set(tokens) if token in lowered)


class ContextRelevanceScorer:
    """Deterministic scorer; identical inputs always produce identical scores."""

    def __init__(self) -> None:
        # (signal weight, reason label)
        self._weights: list[tuple[float, str]] = [
            (0.35, "query keyword matched in path"),
            (0.30, "query keyword matched symbol or file name"),
            (0.15, "query keyword matched content"),
            (0.10, "related import or reference"),
            (0.15, "file appears in the recent git diff"),
            (0.25, "error or failure text matched"),
            (0.20, "matches the user selected code"),
        ]

    def score(
        self,
        candidate: ContextCandidate,
        *,
        query: str = "",
        selected_path: str = "",
        selected_text: str = "",
        error_text: str = "",
        test_failure_text: str = "",
        diff_files: Iterable[str] = (),
    ) -> tuple[float, list[str]]:
        tokens = tokenize(query)
        reasons: list[str] = []
        score = 0.0

        path = (candidate.path or "").lower()
        name = (candidate.name or "").lower()
        content = (candidate.content or "").lower()

        if tokens and _overlap(tokens, candidate.path):
            score += 0.35
            reasons.append("query keyword matched in path")
        if tokens and _overlap(tokens, name):
            score += 0.30
            reasons.append("query keyword matched symbol or file name")
        if tokens and _overlap(tokens, content):
            score += 0.15
            reasons.append("query keyword matched content")

        if selected_path and selected_path == candidate.path:
            score += 0.20
            reasons.append("matches the user selected code")
        if selected_text and tokens and _overlap(tokens, selected_text):
            score += 0.10
            reasons.append("related import or reference")

        diff_set = {item.lower() for item in diff_files}
        if candidate.path and candidate.path.lower() in diff_set:
            score += 0.15
            reasons.append("file appears in the recent git diff")

        error_haystack = f"{error_text} {test_failure_text}".lower()
        if error_haystack:
            error_tokens = tokenize(error_haystack)
            if _overlap(error_tokens, content) or _overlap(error_tokens, name):
                score += 0.25
                reasons.append("error or failure text matched")

        return round(min(score, 1.0), 2), reasons
