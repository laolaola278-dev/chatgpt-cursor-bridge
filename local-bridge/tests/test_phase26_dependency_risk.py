from __future__ import annotations

import pytest

from app.intelligence.dependency import DependencyRiskAnalyzer, DependencyRiskLevel, DependencyRiskStore
from app.intelligence.observation import ObservationStore, ObservationType
from tests.phase26_helpers import observations


@pytest.mark.parametrize("change_type", ["added", "updated", "removed", "major", "breaking", "transitive", "vulnerable", "minor", "patch", "unknown"] * 3)
def test_dependency_change_matrix_is_read_only_and_bounded(tmp_path, change_type):
    db = tmp_path / f"dependency-{change_type}.db"
    store = ObservationStore(db)
    item = store.record(project_id="demo", type=ObservationType.DEPENDENCY_CHANGE, source="manifest", summary=f"{change_type} dependency change", metadata={"dependency": "pkg-x", "change_type": change_type, "affected_components": ["src/service.py"], "old_version": "1.0", "new_version": "2.0"})
    result = DependencyRiskAnalyzer().analyze("demo", [item], historical_failures=[])
    assert result and result[0].dependency == "pkg-x"
    assert result[0].risk in {item.value for item in DependencyRiskLevel}
    assert 0 <= result[0].confidence <= 0.95
    assert "package.json" not in str(result[0].as_dict())


def test_major_change_with_matching_failure_is_high_signal(tmp_path):
    db = tmp_path / "high.db"
    store = ObservationStore(db)
    change = store.record(project_id="demo", type=ObservationType.DEPENDENCY_CHANGE, source="manifest", summary="major breaking dependency change", metadata={"dependency": "pkg-x", "new_version": "3.0"}, timestamp="2026-01-01T00:00:00+00:00")
    failure = store.record(project_id="demo", type=ObservationType.TEST_RESULT, source="pytest", summary="pkg-x regression failure", metadata={"dependency": "pkg-x"}, timestamp="2026-01-02T00:00:00+00:00")
    result = DependencyRiskAnalyzer().analyze("demo", [change], historical_failures=[failure])
    assert result[0].historical_evidence == [failure.id]
    assert result[0].risk in {DependencyRiskLevel.HIGH.value, DependencyRiskLevel.CRITICAL.value}


def test_fixture_dependencies_are_project_scoped(tmp_path):
    db = tmp_path / "fixture.db"
    rows = observations(db)
    result = DependencyRiskAnalyzer().analyze("demo", rows, historical_failures=rows)
    assert result and all(item.project_id == "demo" for item in result)
    assert DependencyRiskAnalyzer().analyze("other", rows) == []


def test_dependency_store_round_trip(tmp_path):
    db = tmp_path / "store.db"
    rows = observations(db)
    store = DependencyRiskStore(db)
    result = DependencyRiskAnalyzer(store).analyze_and_store("demo", rows, historical_failures=rows)
    assert store.list("demo") and store.list("demo")[0].risk_id in {item.risk_id for item in result}
    assert store.list("other") == []


def test_transitive_and_coupling_values_are_bounded(tmp_path):
    db = tmp_path / "bounds.db"
    source = ObservationStore(db).record(project_id="demo", type=ObservationType.DEPENDENCY_CHANGE, source="manifest", summary="transitive change", metadata={"dependency": "pkg", "transitive": True, "concentration": 9, "coupling": -3})
    result = DependencyRiskAnalyzer().analyze("demo", [source])[0]
    assert result.transitive is True
    assert result.concentration == 1.0 and result.coupling == 0.0
