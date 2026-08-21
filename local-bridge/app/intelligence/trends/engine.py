from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from secrets import token_hex
from typing import Iterable

from app.intelligence.common import ensure_project, sanitize_text
from app.intelligence.confidence import derive_confidence
from app.intelligence.observation.models import Observation, ObservationType

from .models import TrendDirection, TrendMetric, TrendResult
from .storage import TrendStore


_METRICS = tuple(item.value for item in TrendMetric)
_FAILURE_WORDS = ("fail", "error", "broken", "timeout", "regression", "degrad")


class EngineeringTrendEngine:
    """Pure trend analysis. It requires multiple time buckets and never edits source."""

    metrics = _METRICS

    def __init__(self, store: TrendStore | None = None) -> None:
        self.store = store

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.astimezone()
        except (TypeError, ValueError):
            return None

    @classmethod
    def _bucket(cls, timestamp: str, period: str) -> str:
        parsed = cls._parse_time(timestamp)
        if parsed is None:
            return "unknown"
        day = parsed.date()
        if period.lower() in {"week", "weekly"}:
            day -= timedelta(days=day.weekday())
        return day.isoformat()

    @staticmethod
    def _failed(item: Observation) -> bool:
        text = f"{item.summary} {item.metadata}".lower()
        return any(word in text for word in _FAILURE_WORDS)

    @classmethod
    def _value(cls, metric: str, item: Observation) -> float | None:
        if metric == TrendMetric.TEST_FAILURE.value:
            return 1.0 if item.type is ObservationType.TEST_RESULT and cls._failed(item) else None
        if metric == TrendMetric.BUILD_FAILURE.value:
            return 1.0 if item.type is ObservationType.BUILD_RESULT and cls._failed(item) else None
        if metric == TrendMetric.ERROR_FREQUENCY.value:
            return 1.0 if item.type is ObservationType.ERROR_EVENT else None
        if metric == TrendMetric.DEPENDENCY_CHANGES.value:
            return 1.0 if item.type is ObservationType.DEPENDENCY_CHANGE else None
        if metric == TrendMetric.CODE_CHANGES.value:
            return 1.0 if item.type in {ObservationType.CODE_CHANGE, ObservationType.GIT_DIFF} else None
        if metric == TrendMetric.REGRESSION.value:
            return 1.0 if cls._failed(item) and "regression" in f"{item.summary} {item.metadata}".lower() else None
        if metric == TrendMetric.RISK.value:
            weights = {"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}
            return weights.get(item.risk_level, 1.0)
        if metric == TrendMetric.PERFORMANCE.value:
            if item.type is not ObservationType.PERFORMANCE_EVENT:
                return None
            for key in ("value", "latency", "p95", "duration_ms", "duration"):
                raw = item.metadata.get(key)
                if isinstance(raw, (int, float)):
                    return float(raw)
            return 1.0
        return None

    @staticmethod
    def _direction(values: list[float]) -> TrendDirection:
        if len(values) < 2:
            return TrendDirection.STABLE
        deltas = [right - left for left, right in zip(values, values[1:])]
        signs = {1 if delta > 0 else -1 if delta < 0 else 0 for delta in deltas}
        if 1 in signs and -1 in signs:
            return TrendDirection.VOLATILE
        if abs(values[-1] - values[0]) < 0.0001:
            return TrendDirection.STABLE
        return TrendDirection.INCREASING if values[-1] > values[0] else TrendDirection.DECREASING

    def analyze(
        self,
        project: str,
        observations: Iterable[Observation],
        *,
        metric: str | None = None,
        period: str = "daily",
    ) -> list[TrendResult]:
        project = ensure_project(project)
        if period.lower() not in {"day", "daily", "week", "weekly"}:
            raise ValueError("Trend period must be daily or weekly")
        selected = [item for item in observations if item.project_id == project]
        metrics = [metric] if metric else list(_METRICS)
        unknown = [item for item in metrics if item not in _METRICS]
        if unknown:
            raise ValueError(f"Unsupported trend metric: {unknown[0]}")
        results: list[TrendResult] = []
        for current_metric in metrics:
            buckets: dict[str, list[tuple[Observation, float]]] = defaultdict(list)
            for item in selected:
                value = self._value(current_metric, item)
                if value is not None:
                    buckets[self._bucket(item.timestamp, period)].append((item, value))
            if len(buckets) < 2:
                # A single event or a single period is not a trend.
                continue
            ordered = sorted((key, items) for key, items in buckets.items() if key != "unknown")
            if len(ordered) < 2:
                continue
            values = [sum(value for _, value in items) / len(items) for _, items in ordered]
            evidence = [item.id for _, items in ordered for item, _ in items]
            direction = self._direction(values)
            baseline = max(abs(values[0]), 1.0)
            change_rate = (values[-1] - values[0]) / baseline
            consistency = 0.9 if direction is not TrendDirection.VOLATILE else 0.35
            breakdown = derive_confidence(
                evidence_count=len(evidence),
                latest_timestamp=max(item.timestamp for _, items in ordered for item, _ in items),
                historical_similarity=min(1.0, (len(ordered) - 1) / 4.0),
                pattern_consistency=consistency,
            )
            results.append(TrendResult(
                trend_id=f"trend_{token_hex(8)}", project_id=project,
                metric=current_metric, period=period, direction=direction,
                change_rate=change_rate, confidence=breakdown.score,
                evidence=evidence, sample_count=len(evidence),
                values=[{"period": key, "value": round(value, 4), "samples": len(items)} for (key, items), value in zip(ordered, values)],
                confidence_sources=breakdown.as_dict(),
                confidence_explanation=breakdown.explanation(),
            ))
        return results

    def analyze_and_store(self, project: str, observations: Iterable[Observation], **kwargs: object) -> list[TrendResult]:
        results = self.analyze(project, observations, **kwargs)
        if self.store is not None:
            self.store.save_many(results)
        return results


TrendEngine = EngineeringTrendEngine
