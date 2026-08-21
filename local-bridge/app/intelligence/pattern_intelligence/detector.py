from __future__ import annotations

from collections import defaultdict
from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import bounded_confidence, similarity, tokens
from app.intelligence.observation.models import Observation, ObservationType

from .models import PatternResult, PatternType
from .storage import PatternStore


_FAILURE_TYPES = {ObservationType.ERROR_EVENT, ObservationType.TEST_RESULT, ObservationType.BUILD_RESULT}


class PatternIntelligence:
    """Read-only detector. ``detect`` never persists and never runs a command."""

    def __init__(self, store: PatternStore | None = None) -> None:
        self.store = store

    @staticmethod
    def _pattern(project: str, kind: PatternType, evidence: list[str], history: list[dict[str, Any]], summary: str, confidence: float) -> PatternResult:
        return PatternResult(
            pattern_id=f"pat_{token_hex(8)}", project_id=project, pattern_type=kind,
            evidence=evidence, similar_history=history, confidence=confidence, summary=summary,
        )

    @staticmethod
    def _fingerprint(observation: Observation) -> str:
        metadata = observation.metadata
        value = metadata.get("fingerprint") or metadata.get("file") or metadata.get("module") or observation.source
        return " ".join(sorted(tokens(observation.type.value, value, observation.summary)))

    def historical_similarity(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        ordered = list(observations)
        results: list[PatternResult] = []
        for index, current in enumerate(ordered):
            current_tokens = tokens(current.type.value, current.source, current.summary, current.metadata.get("file"), current.metadata.get("module"))
            matches: list[dict[str, Any]] = []
            for previous in ordered[index + 1 :]:
                if previous.type is not current.type:
                    continue
                score = similarity(current_tokens, tokens(previous.type.value, previous.source, previous.summary, previous.metadata.get("file"), previous.metadata.get("module")))
                if score >= 0.45:
                    matches.append({"observation_id": previous.id, "observationId": previous.id, "similarity": score, "timestamp": previous.timestamp})
            if matches:
                evidence = [current.id] + [item["observation_id"] for item in matches]
                results.append(self._pattern(project, PatternType.HISTORICAL_SIMILARITY, evidence, matches, "Similar historical observation detected", min(0.9, 0.45 + len(matches) * 0.08)))
        return results

    def detect_repeated_failures(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        groups: dict[str, list[Observation]] = defaultdict(list)
        for item in observations:
            failed = item.type in _FAILURE_TYPES and any(word in (item.summary + " " + str(item.metadata)).lower() for word in ("fail", "error", "regression", "broken", "timeout"))
            if failed:
                groups[self._fingerprint(item)].append(item)
        return [self._pattern(project, PatternType.REPEATED_FAILURE, [item.id for item in items], [{"observation_id": item.id, "timestamp": item.timestamp} for item in items[1:]], "Repeated engineering failure pattern", min(0.95, 0.5 + 0.1 * len(items))) for items in groups.values() if len(items) >= 2]

    def detect_repeated_changes(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        groups: dict[str, list[Observation]] = defaultdict(list)
        for item in observations:
            if item.type in {ObservationType.CODE_CHANGE, ObservationType.GIT_DIFF}:
                groups[self._fingerprint(item)].append(item)
        return [self._pattern(project, PatternType.REPEATED_CHANGE, [item.id for item in items], [{"observation_id": item.id} for item in items[1:]], "Repeated change pattern detected", min(0.9, 0.45 + 0.1 * len(items))) for items in groups.values() if len(items) >= 2]

    def detect_regressions(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        ordered = sorted(list(observations), key=lambda item: item.timestamp)
        results: list[PatternResult] = []
        changes = [item for item in ordered if item.type in {ObservationType.CODE_CHANGE, ObservationType.GIT_DIFF}]
        failures = [item for item in ordered if item.type in {ObservationType.TEST_RESULT, ObservationType.BUILD_RESULT} and any(word in (item.summary + " " + str(item.metadata)).lower() for word in ("fail", "error", "regression", "broken"))]
        for failure in failures:
            previous = [change for change in changes if change.timestamp <= failure.timestamp]
            if previous:
                change = previous[-1]
                evidence = [change.id, failure.id]
                results.append(self._pattern(project, PatternType.REGRESSION, evidence, [{"observation_id": change.id, "relation": "preceded_failure"}], "Failure followed a recorded code or diff change", 0.55))
        return results

    def detect_dependencies(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        items = [item for item in observations if item.type is ObservationType.DEPENDENCY_CHANGE]
        if not items:
            return []
        risky = [item for item in items if any(word in (item.summary + " " + str(item.metadata)).lower() for word in ("major", "removed", "vulnerable", "breaking", "risk"))]
        selected = risky or items
        return [self._pattern(project, PatternType.DEPENDENCY, [item.id for item in selected], [{"observation_id": item.id} for item in items if item not in selected], "Dependency change pattern requires review", min(0.92, 0.48 + len(selected) * 0.08))]

    def detect_performance(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        items = [item for item in observations if item.type is ObservationType.PERFORMANCE_EVENT and any(word in (item.summary + " " + str(item.metadata)).lower() for word in ("degrad", "slow", "latency", "regression", "increase"))]
        if len(items) < 1:
            return []
        return [self._pattern(project, PatternType.PERFORMANCE_DEGRADATION, [item.id for item in items], [{"observation_id": item.id} for item in items[1:]], "Performance degradation signal detected", min(0.9, 0.5 + len(items) * 0.08))]

    def detect(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        items = list(observations)
        results: list[PatternResult] = []
        results.extend(self.historical_similarity(project, items))
        results.extend(self.detect_repeated_failures(project, items))
        results.extend(self.detect_repeated_changes(project, items))
        results.extend(self.detect_regressions(project, items))
        results.extend(self.detect_dependencies(project, items))
        results.extend(self.detect_performance(project, items))
        return results

    def analyze(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        return self.detect(project, observations)

    def analyze_and_store(self, project: str, observations: Iterable[Observation]) -> list[PatternResult]:
        results = self.detect(project, observations)
        if self.store is not None:
            self.store.save_many(results)
        return results


PatternIntelligenceEngine = PatternIntelligence
