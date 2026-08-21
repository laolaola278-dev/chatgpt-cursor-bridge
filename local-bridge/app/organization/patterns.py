"""Enterprise Engineering Pattern Library.

Automatically curated knowledge base of engineering patterns: successful
refactors, bad migrations, deployment failures and architecture successes.
Pattern writes are approval-gated metadata; reads are always read-only.
"""

from __future__ import annotations

import re
from typing import Any

from app.security.validator import ValidationFailed

from .models import OrgPattern, PatternCategory
from .storage import OrganizationStorage


class EngineeringPatternLibrary:
    CATEGORIES = {category.value for category in PatternCategory}

    def __init__(self, storage: OrganizationStorage) -> None:
        self.storage = storage

    def record(
        self,
        category: str,
        name: str,
        summary: str,
        project: str,
        tags: list[str] | None = None,
    ) -> OrgPattern:
        try:
            category_enum = PatternCategory(category.strip().lower())
        except ValueError as exc:
            raise ValidationFailed(f"Unknown pattern category '{category}'") from exc
        name = (name or "").strip()
        summary = (summary or "").strip()
        project = (project or "").strip()
        if not name or len(name) > 200:
            raise ValidationFailed("Pattern name must contain 1-200 characters")
        if not summary or len(summary) > 4000:
            raise ValidationFailed("Pattern summary must contain 1-4000 characters")
        if not project:
            raise ValidationFailed("Pattern project is required")
        pattern = OrgPattern(
            category=category_enum,
            name=name,
            summary=summary,
            project=project,
            tags=list(dict.fromkeys(tags or []))[:20],
        )
        self.storage.save_pattern(pattern)
        return pattern

    def list(self, category: str | None = None, limit: int = 200) -> list[OrgPattern]:
        if category is not None and category not in self.CATEGORIES:
            raise ValidationFailed(f"Unknown pattern category '{category}'")
        return self.storage.list_patterns(category, limit)

    def search(self, query: str, limit: int = 50) -> list[OrgPattern]:
        query = (query or "").strip().lower()
        if not query:
            return []
        return [
            pattern
            for pattern in self.storage.list_patterns()
            if query in pattern.name.lower() or query in pattern.summary.lower() or query in pattern.project.lower()
            or any(query in tag.lower() for tag in pattern.tags)
        ][:limit]

    def suggest(self, project: str, failure_signals: list[str], limit: int = 5) -> list[dict[str, Any]]:
        """Read-only: suggest library patterns relevant to current failure signals."""
        signals = {signal.strip().lower() for signal in failure_signals if signal.strip()}
        if not signals:
            return []
        scored: list[tuple[float, OrgPattern]] = []
        for pattern in self.storage.list_patterns():
            if pattern.project == project:
                continue
            haystack = {pattern.name, pattern.summary, pattern.project, *pattern.tags}
            haystack_tokens = {
                token.lower()
                for piece in haystack
                for token in re.split(r"[^a-zA-Z0-9_]+", piece)
                if token
            }
            overlap = signals & haystack_tokens
            score = len(overlap) / len(signals) if signals else 0.0
            if score > 0:
                scored.append((score, pattern))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [pattern.as_dict() for _, pattern in scored[:limit]]
