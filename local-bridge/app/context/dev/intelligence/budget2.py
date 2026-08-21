"""Phase 30 · Context Budget 2.0.

Extends the Phase 29 ``ContextBudget`` with per-context-type buckets plus a
global cap. Selection keeps the highest-relevance candidates, truncates
lower-priority content, and never silently exceeds the budget: every response
carries a usage report and explicit ``truncated`` flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import BUDGET_BY_KIND, GLOBAL_CONTEXT_BUDGET, KIND_PRIORITY, BudgetUsage, ContextCandidate

#: Per-item hard cap before truncation kicks in (bytes).
MAX_ITEM_BYTES = 16 * 1024


@dataclass(frozen=True)
class BudgetReport:
    usages: list[BudgetUsage]
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "budget": [usage.as_dict() for usage in self.usages],
            "truncated": self.truncated,
            "globalLimit": GLOBAL_CONTEXT_BUDGET,
        }


class ContextBudget2:
    def __init__(
        self,
        *,
        global_budget: int = GLOBAL_CONTEXT_BUDGET,
        budget_by_kind: dict[str, int] | None = None,
    ) -> None:
        self._global_budget = max(64, global_budget)
        self._budget_by_kind = dict(budget_by_kind or BUDGET_BY_KIND)
        self._bucket_used: dict[str, int] = {key: 0 for key in KIND_PRIORITY}
        self._bucket_items: dict[str, int] = {key: 0 for key in KIND_PRIORITY}
        self._used_total = 0

    def select(self, candidates: list[ContextCandidate]) -> tuple[list[ContextCandidate], list[ContextCandidate], bool]:
        """Return (included, excluded_by_budget, truncated_any)."""
        ranked = sorted(candidates, key=lambda item: (-len(item.reasons), item.path))
        included: list[ContextCandidate] = []
        excluded: list[ContextCandidate] = []
        truncated_any = False
        for candidate in ranked:
            bucket = candidate.bucket
            bucket_limit = self._budget_by_kind.get(bucket, BUDGET_BY_KIND["code"])
            if self._bucket_used[bucket] + candidate.size > bucket_limit or self._used_total + candidate.size > self._global_budget:
                excluded.append(candidate)
                continue
            # Per-item truncation: never ship a giant blob silently.
            if candidate.size > MAX_ITEM_BYTES:
                truncated_any = True
            self._bucket_used[bucket] += candidate.size
            self._bucket_items[bucket] += 1
            self._used_total += candidate.size
            included.append(candidate)
        return included, excluded, truncated_any

    def usage(self) -> list[BudgetUsage]:
        return [
            BudgetUsage(
                bucket=bucket,
                used=self._bucket_used[bucket],
                limit=self._budget_by_kind.get(bucket, BUDGET_BY_KIND["code"]),
                items=self._bucket_items[bucket],
            )
            for bucket in KIND_PRIORITY
        ]
