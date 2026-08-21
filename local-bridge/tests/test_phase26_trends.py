from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.intelligence.observation import ObservationStore, ObservationType
from app.intelligence.trends import EngineeringTrendEngine, TrendDirection, TrendMetric, TrendStore
from app.config import get_settings
from tests.phase26_helpers import observations


@pytest.mark.parametrize("metric", [
    TrendMetric.TEST_FAILURE.value, TrendMetric.BUILD_FAILURE.value, TrendMetric.ERROR_FREQUENCY.value,
    TrendMetric.DEPENDENCY_CHANGES.value, TrendMetric.PERFORMANCE.value, TrendMetric.RISK.value,
    TrendMetric.CODE_CHANGES.value, TrendMetric.REGRESSION.value,
] * 4)
def test_trend_metric_matrix_is_project_scoped_and_evidence_backed(tmp_path, metric):
    db = tmp_path / "trend.db"
    rows = observations(db)
    result = EngineeringTrendEngine().analyze("demo", rows, metric=metric)
    assert all(item.project_id == "demo" for item in result)
    assert all(item.evidence for item in result)
    assert all(0 <= item.confidence <= 0.95 for item in result)
    assert all(item.direction in set(TrendDirection) for item in result)


def test_single_observation_period_is_not_a_trend(tmp_path):
    store = ObservationStore(tmp_path / "single.db")
    item = store.record(project_id="demo", type=ObservationType.ERROR_EVENT, source="runner", summary="error", timestamp="2026-01-01T00:00:00+00:00")
    assert EngineeringTrendEngine().analyze("demo", [item], metric=TrendMetric.ERROR_FREQUENCY.value) == []


def test_increasing_risk_trend_has_multiple_time_buckets(tmp_path):
    store = ObservationStore(tmp_path / "risk.db")
    rows = [store.record(project_id="demo", type=ObservationType.ERROR_EVENT, source="runner", summary="error", risk_level="low", timestamp="2026-01-01T00:00:00+00:00"), store.record(project_id="demo", type=ObservationType.ERROR_EVENT, source="runner", summary="error", risk_level="critical", timestamp="2026-01-02T00:00:00+00:00")]
    result = EngineeringTrendEngine().analyze("demo", rows, metric=TrendMetric.RISK.value)
    assert len(result) == 1
    assert result[0].direction is TrendDirection.INCREASING
    assert len(result[0].evidence) == 2


def test_weekly_period_is_supported(tmp_path):
    store = ObservationStore(tmp_path / "weekly.db")
    rows = [store.record(project_id="demo", type=ObservationType.ERROR_EVENT, source="runner", summary="error", timestamp="2026-01-01T00:00:00+00:00"), store.record(project_id="demo", type=ObservationType.ERROR_EVENT, source="runner", summary="error", timestamp="2026-01-15T00:00:00+00:00")]
    result = EngineeringTrendEngine().analyze("demo", rows, metric=TrendMetric.ERROR_FREQUENCY.value, period="weekly")
    assert result and result[0].period == "weekly"


def test_invalid_period_and_metric_are_rejected(tmp_path):
    rows = observations(tmp_path / "invalid.db")
    with pytest.raises(ValueError):
        EngineeringTrendEngine().analyze("demo", rows, period="hourly")
    with pytest.raises(ValueError):
        EngineeringTrendEngine().analyze("demo", rows, metric="made_up")


def test_trend_store_persists_without_cross_project_leak(tmp_path):
    db = tmp_path / "store.db"
    rows = observations(db)
    store = TrendStore(db)
    result = EngineeringTrendEngine(store).analyze_and_store("demo", rows, metric=TrendMetric.RISK.value)
    assert store.list("demo") and store.list("other") == []
    assert store.list("demo")[0].trend_id == result[0].trend_id
