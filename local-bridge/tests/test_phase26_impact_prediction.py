from __future__ import annotations

import pytest

from app.intelligence.impact_prediction import ChangeImpactPredictionEngine, ImpactPredictionStore, ImpactRiskLevel
from tests.phase26_helpers import observations


@pytest.mark.parametrize("path", [f"src/module_{index}.py" for index in range(30)])
def test_changed_file_matrix_returns_explainable_prediction(tmp_path, path):
    rows = observations(tmp_path / f"impact-{path.rsplit('/', 1)[-1]}.db")
    result = ChangeImpactPredictionEngine().predict("demo", rows, changed_files=[path], changed_symbols=[f"symbol_{path}"])
    assert result.project_id == "demo"
    assert result.changed_files == [path]
    assert result.confidence_sources and result.confidence_explanation
    assert result.risk_level in {item.value for item in ImpactRiskLevel}
    assert result.why_risky and "execute" not in str(result.as_dict()).lower()


def test_impact_links_historical_failure_evidence(tmp_path):
    rows = observations(tmp_path / "history.db")
    result = ChangeImpactPredictionEngine().predict("demo", rows, changed_files=["src/parser.py"], historical_failures=rows)
    assert result.evidence
    assert any("historical failure" in reason for reason in result.why_risky)
    assert "src/parser.py" in result.affected_files


def test_dependency_paths_are_metadata_only(tmp_path):
    rows = observations(tmp_path / "paths.db")
    result = ChangeImpactPredictionEngine().predict("demo", rows, changed_files=["src/parser.py"], dependencies=[["service-a", "lib-x", "service-b"]])
    assert result.dependency_paths == [["service-a", "lib-x", "service-b"]]
    assert result.affected_modules


def test_impact_filters_other_projects(tmp_path):
    rows = observations(tmp_path / "isolation.db")
    other = observations(tmp_path / "other.db")
    result = ChangeImpactPredictionEngine().predict("demo", [*rows, *other], changed_files=["secret-other.py"], historical_failures=other)
    assert result.project_id == "demo"
    assert "secret-other.py" in result.changed_files
    assert all(item.id in result.evidence for item in rows if item.id in result.evidence)


def test_impact_store_round_trip(tmp_path):
    db = tmp_path / "store.db"
    rows = observations(db)
    store = ImpactPredictionStore(db)
    result = ChangeImpactPredictionEngine(store).predict_and_store("demo", rows, changed_files=["src/parser.py"])
    assert store.list("demo")[0].prediction_id == result.prediction_id
    assert store.list("other") == []
