"""Task 4 · Decision Outcome Intelligence.

Analyzes how engineering decisions (architecture, debugging, refactoring,
test, dependency, risk) turned out compared with their stated expectations,
and reports success rates by decision type.
"""

from __future__ import annotations

from dataclasses import dataclass
from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import ensure_project, ids, sanitize_text, utc_now

from .models import DECISION_TYPES, DecisionOutcome, DecisionOutcomeStatus


@dataclass(frozen=True)
class DecisionOutcomeSummary:
    project_id: str
    total: int
    by_type: dict[str, dict[str, float]]
    overall_success_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "total": self.total,
            "byType": self.by_type,
            "overallSuccessRate": round(max(0.0, min(1.0, self.overall_success_rate)), 3),
            "readOnly": True,
        }


class DecisionOutcomeIntelligence:
    def record(
        self,
        *,
        project_id: str,
        decision_id: str,
        decision_type: str,
        title: str,
        expected_outcome: str,
        actual_outcome: str,
        status: str,
        agent_id: str = "",
        model_id: str = "",
        evidence: list[str] | None = None,
    ) -> DecisionOutcome:
        return DecisionOutcome(
            outcome_id=f"dout_{token_hex(8)}",
            project_id=project_id,
            decision_id=decision_id,
            decision_type=decision_type,
            title=title,
            expected_outcome=expected_outcome,
            actual_outcome=actual_outcome,
            status=status,
            agent_id=agent_id,
            model_id=model_id,
            evidence=ids(evidence),
            evaluated_at=utc_now(),
        )

    @staticmethod
    def summary(project_id: str, records: Iterable[DecisionOutcome]) -> DecisionOutcomeSummary:
        project = ensure_project(project_id)
        items = [record for record in records if record.project_id == project]
        by_type: dict[str, dict[str, float]] = {}
        successes = 0
        for record in items:
            bucket = by_type.setdefault(record.decision_type, {"total": 0.0, "successes": 0.0, "successRate": 0.0})
            bucket["total"] += 1
            if record.status == DecisionOutcomeStatus.SUCCESS.value:
                bucket["successes"] += 1
                successes += 1
        for values in by_type.values():
            values["successRate"] = round(values["successes"] / values["total"], 3) if values["total"] else 0.0
        return DecisionOutcomeSummary(
            project_id=project,
            total=len(items),
            by_type=by_type,
            overall_success_rate=successes / len(items) if items else 0.0,
        )


DecisionOutcomeEvaluator = DecisionOutcomeIntelligence
