from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_hex
from typing import Iterable

from app.intelligence.common import ensure_project, similarity, tokens
from app.intelligence.confidence import derive_confidence
from app.intelligence.observation.models import Observation, ObservationType

from .models import CorrelationRelationship, CorrelationResult
from .storage import CorrelationStore


_FAILURES = {ObservationType.TEST_RESULT, ObservationType.BUILD_RESULT, ObservationType.ERROR_EVENT}
_FAILURE_WORDS = ("fail", "error", "broken", "timeout", "regression")


class FailureCorrelationEngine:
    """Finds temporal associations between recorded observations.

    The output explicitly says correlation-only and carries the observation IDs
    that support it. No source, dependency, or execution state is changed.
    """

    def __init__(self, store: CorrelationStore | None = None, *, max_gap_days: int = 14) -> None:
        self.store = store
        self.max_gap_days = max(1, int(max_gap_days))

    @staticmethod
    def _time(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_failure(item: Observation) -> bool:
        text = f"{item.summary} {item.metadata}".lower()
        return item.type in _FAILURES and any(word in text for word in _FAILURE_WORDS)

    @staticmethod
    def _relationship(left: Observation, right: Observation) -> CorrelationRelationship | None:
        if left.type is ObservationType.DEPENDENCY_CHANGE and FailureCorrelationEngine._is_failure(right):
            return CorrelationRelationship.DEPENDENCY_CHANGE_FOLLOWED_FAILURE
        if left.type in {ObservationType.CODE_CHANGE, ObservationType.GIT_DIFF} and (
            right.type in {ObservationType.TEST_RESULT, ObservationType.BUILD_RESULT} or "regression" in right.summary.lower()
        ):
            return CorrelationRelationship.CODE_CHANGE_FOLLOWED_REGRESSION
        if left.type is ObservationType.TEST_RESULT and right.type is ObservationType.BUILD_RESULT:
            return CorrelationRelationship.TEST_FAILURE_FOLLOWED_BUILD_FAILURE
        if left.type is ObservationType.PERFORMANCE_EVENT and right.type is ObservationType.ERROR_EVENT:
            return CorrelationRelationship.PERFORMANCE_CHANGE_ASSOCIATED_WITH_ERROR
        return None

    @staticmethod
    def _score(left: Observation, right: Observation) -> float:
        left_tokens = tokens(left.type.value, left.source, left.summary, left.metadata.get("file"), left.metadata.get("module"), left.metadata.get("dependency"))
        right_tokens = tokens(right.type.value, right.source, right.summary, right.metadata.get("file"), right.metadata.get("module"), right.metadata.get("dependency"))
        return similarity(left_tokens, right_tokens)

    def analyze(self, project: str, observations: Iterable[Observation]) -> list[CorrelationResult]:
        project = ensure_project(project)
        ordered = sorted((item for item in observations if item.project_id == project), key=lambda item: item.timestamp)
        results: list[CorrelationResult] = []
        for index, left in enumerate(ordered):
            left_time = self._time(left.timestamp)
            if left_time is None:
                continue
            for right in ordered[index + 1 :]:
                right_time = self._time(right.timestamp)
                if right_time is None:
                    continue
                gap = (right_time - left_time).total_seconds()
                if gap < 0 or gap > self.max_gap_days * 86400:
                    continue
                relationship = self._relationship(left, right)
                if relationship is None:
                    continue
                lexical = self._score(left, right)
                breakdown = derive_confidence(
                    evidence_count=2,
                    latest_timestamp=right.timestamp,
                    historical_similarity=lexical,
                    pattern_consistency=0.75 if relationship is not CorrelationRelationship.CODE_CHANGE_FOLLOWED_REGRESSION else 0.6,
                )
                results.append(CorrelationResult(
                    correlation_id=f"corr_{token_hex(8)}", project_id=project,
                    events=[left.id, right.id], relationship=relationship.value,
                    confidence=breakdown.score, evidence=[left.id, right.id],
                    event_details=[
                        {"observation_id": left.id, "type": left.type.value, "timestamp": left.timestamp},
                        {"observation_id": right.id, "type": right.type.value, "timestamp": right.timestamp},
                    ],
                ))
        return results

    def correlate(self, project: str, observations: Iterable[Observation]) -> list[CorrelationResult]:
        return self.analyze(project, observations)

    def analyze_and_store(self, project: str, observations: Iterable[Observation]) -> list[CorrelationResult]:
        results = self.analyze(project, observations)
        if self.store is not None:
            self.store.save_many(results)
        return results


CorrelationEngine = FailureCorrelationEngine
