"""Cross Project Learning.

Compares a project's failure pattern signatures against patterns recorded by
other projects in the enterprise library and emits read-only warnings such as
"Similar failure detected from Project A". Learning never executes anything:
it only produces SimilarFailureMatch records for the dashboard.
"""

from __future__ import annotations

import re
from typing import Any

from .models import SimilarFailureMatch


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9_]+", value.lower()) if token}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


class CrossProjectLearner:
    """Match a project's failure signatures against the recorded library."""

    def analyze(
        self,
        project: str,
        patterns: list[dict[str, Any]],
        library: list[dict[str, Any]],
        threshold: float = 0.5,
    ) -> list[SimilarFailureMatch]:
        matches: list[SimilarFailureMatch] = []
        for pattern in patterns:
            category = str(pattern.get("category", ""))
            signature = str(pattern.get("signature", ""))
            if not signature:
                continue
            signature_tokens = _tokens(signature)
            for entry in library:
                entry_project = str(entry.get("project", ""))
                if entry_project == project:
                    continue
                entry_category = str(entry.get("category", ""))
                entry_signature = str(entry.get("signature", ""))
                if not entry_signature or entry_category != category:
                    continue
                score = self._score(signature, entry_signature, signature_tokens)
                if score >= threshold:
                    matches.append(
                        SimilarFailureMatch(
                            source_project=entry_project,
                            target_project=project,
                            category=category,
                            signature=entry_signature,
                            match_score=score,
                        )
                    )
        matches.sort(key=lambda match: match.match_score, reverse=True)
        return matches

    @staticmethod
    def _score(left: str, right: str, left_tokens: set[str]) -> float:
        if left == right:
            return 1.0
        return _jaccard(left_tokens, _tokens(right))
