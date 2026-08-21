from __future__ import annotations

from secrets import token_hex
from typing import Iterable

from app.intelligence.common import bounded_confidence
from app.intelligence.observation.models import Observation, ObservationType
from app.intelligence.pattern_intelligence.models import PatternResult, PatternType

from .models import PredictionResult, PredictionType
from .storage import PredictionStore


class PredictionEngine:
    """Deterministic prediction engine; it only returns recommendations' inputs."""

    def __init__(self, store: PredictionStore | None = None) -> None:
        self.store = store

    @staticmethod
    def _map(pattern: PatternResult) -> PredictionType:
        return {
            PatternType.REGRESSION: PredictionType.REGRESSION_RISK,
            PatternType.REPEATED_FAILURE: PredictionType.TEST_FAILURE_RISK,
            PatternType.DEPENDENCY: PredictionType.DEPENDENCY_RISK,
            PatternType.PERFORMANCE_DEGRADATION: PredictionType.PERFORMANCE_RISK,
            PatternType.REPEATED_CHANGE: PredictionType.ARCHITECTURE_RISK,
            PatternType.HISTORICAL_SIMILARITY: PredictionType.REGRESSION_RISK,
        }[pattern.pattern_type]

    def from_pattern(self, project: str, pattern: PatternResult, observations: Iterable[Observation] = ()) -> PredictionResult:
        observation_items = list(observations)
        kind = self._map(pattern)
        evidence = list(dict.fromkeys(pattern.evidence))
        observed_types = {item.type for item in observation_items if item.id in evidence}
        if kind is PredictionType.BUILD_FAILURE_RISK or ObservationType.BUILD_RESULT in observed_types:
            if ObservationType.BUILD_RESULT in observed_types:
                kind = PredictionType.BUILD_FAILURE_RISK
        confidence = bounded_confidence(0.38 + pattern.confidence * 0.42 + min(0.15, len(evidence) * 0.025))
        risk = "high" if confidence >= 0.75 else "medium" if confidence >= 0.5 else "low"
        return PredictionResult(
            prediction_id=f"pred_{token_hex(8)}", project_id=project, prediction_type=kind,
            prediction=f"Evidence suggests elevated {kind.value.replace('_', ' ')}; human review is recommended",
            confidence=confidence, evidence=evidence, observations=evidence, risk_level=risk,
        )

    def predict(self, project: str, patterns: Iterable[PatternResult], observations: Iterable[Observation] = ()) -> list[PredictionResult]:
        return [self.from_pattern(project, pattern, observations) for pattern in patterns]

    def analyze(self, project: str, patterns: Iterable[PatternResult], observations: Iterable[Observation] = ()) -> list[PredictionResult]:
        return self.predict(project, patterns, observations)

    def predict_and_store(self, project: str, patterns: Iterable[PatternResult], observations: Iterable[Observation] = ()) -> list[PredictionResult]:
        results = self.predict(project, patterns, observations)
        if self.store is not None:
            self.store.save_many(results)
        return results


RiskPredictionEngine = PredictionEngine
