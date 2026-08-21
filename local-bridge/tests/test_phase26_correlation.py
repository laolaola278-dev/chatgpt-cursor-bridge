from __future__ import annotations

import pytest

from app.intelligence.correlation import CorrelationRelationship, CorrelationStore, FailureCorrelationEngine
from app.intelligence.observation import ObservationStore, ObservationType
from tests.phase26_helpers import observations


@pytest.mark.parametrize("max_gap", list(range(1, 31)))
def test_correlation_window_matrix_is_evidence_backed(tmp_path, max_gap):
    db = tmp_path / f"corr-{max_gap}.db"
    rows = observations(db)
    result = FailureCorrelationEngine(max_gap_days=max_gap).analyze("demo", rows)
    assert all(item.project_id == "demo" for item in result)
    assert all(item.events and item.evidence for item in result)
    assert all(item.causation_claim is False and item.interpretation == "correlation_only" for item in result)


def test_dependency_change_followed_by_failure_is_correlation_only(tmp_path):
    rows = observations(tmp_path / "dependency.db")
    result = FailureCorrelationEngine().analyze("demo", rows)
    assert any(item.relationship == CorrelationRelationship.DEPENDENCY_CHANGE_FOLLOWED_FAILURE.value for item in result)
    assert not any(item.causation_claim for item in result)


def test_test_failure_and_build_failure_relationship(tmp_path):
    store = ObservationStore(tmp_path / "test-build.db")
    left = store.record(project_id="demo", type=ObservationType.TEST_RESULT, source="pytest", summary="test failed", timestamp="2026-01-01T00:00:00+00:00")
    right = store.record(project_id="demo", type=ObservationType.BUILD_RESULT, source="ci", summary="build failed", timestamp="2026-01-02T00:00:00+00:00")
    result = FailureCorrelationEngine().analyze("demo", [left, right])
    assert result[0].relationship == CorrelationRelationship.TEST_FAILURE_FOLLOWED_BUILD_FAILURE.value


def test_unrelated_project_is_ignored(tmp_path):
    rows = observations(tmp_path / "isolation.db")
    other = ObservationStore(tmp_path / "isolation.db").record(project_id="other", type=ObservationType.ERROR_EVENT, source="runner", summary="error", timestamp="2026-01-02T00:00:00+00:00")
    result = FailureCorrelationEngine().analyze("demo", [*rows, other])
    assert all(other.id not in item.events for item in result)


def test_correlation_store_round_trip(tmp_path):
    db = tmp_path / "roundtrip.db"
    rows = observations(db)
    store = CorrelationStore(db)
    result = FailureCorrelationEngine(store).analyze_and_store("demo", rows)
    assert result and store.list("demo")[0].correlation_id in {item.correlation_id for item in result}
    assert store.list("other") == []
