"""Phase 28 · Intelligence Trend Analysis.

Trends are computed exclusively from historical evaluation / governance
records. A trend is only classified with confidence when multiple evidence
buckets exist; a single event never produces a deterministic trend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.intelligence.common import bounded_confidence, utc_now
from app.intelligence.governance.models import GovernanceTrend
from app.intelligence.validation.models import EvaluationRecord, RecommendationEffectiveness, DecisionOutcome
from app.intelligence.validation.storage import ValidationStore

PERIODS = ("daily", "weekly", "monthly")


def _bucket_of(timestamp: str, period: str) -> str:
    try:
        value = datetime.fromisoformat((timestamp or "").replace("Z", "+00:00"))
    except ValueError:
        value = datetime.now()
    if period == "daily":
        return value.date().isoformat()
    if period == "weekly":
        iso = value.date().isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if period == "monthly":
        return value.date().strftime("%Y-%m")
    return value.date().isoformat()


def _direction(change_rate: float, *, higher_is_better: bool) -> str:
    if abs(change_rate) < 0.02:
        return "stable"
    if higher_is_better:
        return "improving" if change_rate > 0 else "declining"
    return "increasing" if change_rate > 0 else "decreasing"


def _trend_confidence(bucket_count: int, sample_count: int) -> float:
    if bucket_count <= 1:
        return 0.3
    value = 0.35 + 0.1 * min(bucket_count, 5) + 0.05 * min(sample_count / 10.0, 5.0)
    return bounded_confidence(min(0.9, value))


class GovernanceTrendAnalyzer:
    def __init__(self, validation_store: ValidationStore) -> None:
        self._validation = validation_store

    # -- generic helpers ----------------------------------------------------

    def _bucketed(
        self,
        project: str,
        records: list[Any],
        *,
        value_of: Callable[[Any], float | None],
        period: str,
        timestamp_attr: str = "evaluated_at",
    ) -> list[tuple[str, float, int]]:
        buckets: dict[str, list[float]] = {}
        for record in records:
            value = value_of(record)
            if value is None:
                continue
            timestamp = getattr(record, timestamp_attr, None) or utc_now()
            key = _bucket_of(timestamp, period)
            buckets.setdefault(key, []).append(float(value))
        ordered = sorted(buckets.items())
        return [(key, round(sum(values) / len(values), 4), len(values)) for key, values in ordered]

    def _trend(
        self,
        project: str,
        metric: str,
        buckets: list[tuple[str, float, int]],
        *,
        higher_is_better: bool,
        period: str,
    ) -> GovernanceTrend:
        evidence = [f"{key}={value}(n={count})" for key, value, count in buckets]
        if len(buckets) < 2:
            return GovernanceTrend(
                trend_id="",
                project_id=project,
                metric=metric,
                period=period,
                direction="stable",
                change_rate=0.0,
                confidence=_trend_confidence(len(buckets), sum(count for _, _, count in buckets)),
                evidence=evidence or ["insufficient_data_for_trend"],
                sample_count=sum(count for _, _, count in buckets),
            )
        midpoint = len(buckets) // 2
        first = buckets[:midpoint]
        second = buckets[midpoint:] if len(buckets) % 2 == 0 else buckets[midpoint + 1 :]
        if not first or not second:
            return self._trend(project, metric, buckets[: len(buckets) - 1], higher_is_better=higher_is_better, period=period)
        first_mean = sum(value for _, value, _ in first) / len(first)
        second_mean = sum(value for _, value, _ in second) / len(second)
        change_rate = round(second_mean - first_mean, 4)
        return GovernanceTrend(
            trend_id="",
            project_id=project,
            metric=metric,
            period=period,
            direction=_direction(change_rate, higher_is_better=higher_is_better),
            change_rate=change_rate,
            confidence=_trend_confidence(len(buckets), sum(count for _, _, count in buckets)),
            evidence=evidence,
            sample_count=sum(count for _, _, count in buckets),
        )

    # -- individual metrics -------------------------------------------------

    def accuracy_trend(self, project: str, *, period: str = "weekly", agent_id: str | None = None, model_id: str | None = None) -> GovernanceTrend:
        records = self._validation.evaluations(project, agent_id=agent_id, model_id=model_id, limit=5000)
        buckets = self._bucketed(
            project, records,
            value_of=lambda record: (1.0 if record.evaluation_result == "correct" else 0.0) if record.counted else None,
            period=period,
        )
        return self._trend(project, "accuracy", buckets, higher_is_better=True, period=period)

    def effectiveness_trend(self, project: str, *, period: str = "weekly") -> GovernanceTrend:
        records = self._validation.effectiveness(project, limit=5000)
        buckets = self._bucketed(
            project, records,
            value_of=lambda record: float(record.effectiveness_score) if record.classification != "rejected" else None,
            period=period,
        )
        return self._trend(project, "recommendation_effectiveness", buckets, higher_is_better=True, period=period)

    def decision_success_trend(self, project: str, *, period: str = "weekly") -> GovernanceTrend:
        records = self._validation.decision_outcomes(project, limit=5000)
        buckets = self._bucketed(
            project, records,
            value_of=lambda record: 1.0 if record.status == "SUCCESS" else (0.5 if record.status == "PARTIAL" else 0.0),
            period=period,
        )
        return self._trend(project, "decision_success", buckets, higher_is_better=True, period=period)

    def risk_trend(self, project: str, records: list[Any], *, period: str = "weekly") -> GovernanceTrend:
        """Risk score trend from governance records (lower is better)."""
        buckets = self._bucketed(
            project, records,
            value_of=lambda record: float(getattr(record, "risk_score", 0.0)),
            period=period,
            timestamp_attr="created_at",
        )
        return self._trend(project, "risk_score", buckets, higher_is_better=False, period=period)

    def confidence_trend(self, project: str, *, period: str = "weekly") -> GovernanceTrend:
        records = self._validation.evaluations(project, limit=5000)
        buckets = self._bucketed(
            project, records,
            value_of=lambda record: float(record.confidence),
            period=period,
        )
        return self._trend(project, "confidence", buckets, higher_is_better=True, period=period)

    def model_trend(self, project: str, model_id: str, *, period: str = "weekly") -> GovernanceTrend:
        return self.accuracy_trend(project, period=period, model_id=model_id)

    def agent_trend(self, project: str, agent_id: str, *, period: str = "weekly") -> GovernanceTrend:
        return self.accuracy_trend(project, period=period, agent_id=agent_id)

    # -- combined view ------------------------------------------------------

    def overall(
        self,
        project: str,
        *,
        period: str = "weekly",
        agent_id: str | None = None,
        model_id: str | None = None,
        governance_records: list[Any] | None = None,
    ) -> list[GovernanceTrend]:
        period = period if period in PERIODS else "weekly"
        trends = [
            self.accuracy_trend(project, period=period, agent_id=agent_id, model_id=model_id),
            self.effectiveness_trend(project, period=period),
            self.decision_success_trend(project, period=period),
            self.confidence_trend(project, period=period),
        ]
        if governance_records:
            trends.append(self.risk_trend(project, governance_records, period=period))
        return trends

    def detected(self, trends: list[GovernanceTrend]) -> list[dict[str, str]]:
        """Identify quality degradation / regression / risk escalation signals."""
        signals: list[dict[str, str]] = []
        by_metric = {trend.metric: trend for trend in trends}
        accuracy = by_metric.get("accuracy")
        if accuracy and accuracy.direction == "declining" and accuracy.change_rate <= -0.05:
            signals.append({"signal": "quality_degradation", "metric": "accuracy", "detail": f"change_rate={accuracy.change_rate}"})
        if accuracy and accuracy.change_rate <= -0.15:
            signals.append({"signal": "regression", "metric": "accuracy", "detail": f"change_rate={accuracy.change_rate}"})
        risk = by_metric.get("risk_score")
        if risk and risk.direction == "increasing" and risk.change_rate >= 5.0:
            signals.append({"signal": "risk_escalation", "metric": "risk_score", "detail": f"change_rate={risk.change_rate}"})
        for model_trend in [trend for trend in trends if trend.metric.startswith("model:")]:
            if model_trend.direction == "declining" and model_trend.change_rate <= -0.05:
                signals.append({"signal": "model_degradation", "metric": model_trend.metric, "detail": f"change_rate={model_trend.change_rate}"})
        return signals


GovernanceTrends = GovernanceTrendAnalyzer
