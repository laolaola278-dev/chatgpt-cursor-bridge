from __future__ import annotations

from app.config import get_settings
from app.intelligence.observation import ObservationStore
from app.intelligence.pattern_intelligence import PatternIntelligence
from app.intelligence.recommendation import IntelligenceRecommendationEngine
from app.intelligence.risk_prediction import PredictionEngine, PredictionStore, PredictionType


def test_predictions_have_explicit_bounded_confidence_and_evidence(bridge):
    store = ObservationStore(get_settings().intelligence_db_path)
    store.record(project_id="demo", type="build_result", source="ci", summary="build failure", metadata={"status": "failed"})
    store.record(project_id="demo", type="build_result", source="ci", summary="build failure", metadata={"status": "failed"})
    items = store.list("demo")
    patterns = PatternIntelligence().detect("demo", items)
    predictions = PredictionEngine().predict("demo", patterns, items)
    assert predictions
    assert all(0 < item.confidence <= 0.95 for item in predictions)
    assert all(item.evidence and set(item.evidence).issubset({obs.id for obs in items}) for item in predictions)
    assert any(item.prediction_type in {PredictionType.BUILD_FAILURE_RISK, PredictionType.TEST_FAILURE_RISK} for item in predictions)


def test_prediction_store_and_recommendations_remain_read_only(bridge):
    store = ObservationStore(get_settings().intelligence_db_path)
    store.record(project_id="demo", type="dependency_change", source="lock", summary="vulnerable dependency", metadata={"package": "x"})
    patterns = PatternIntelligence().detect("demo", store.list("demo"))
    predictions = PredictionEngine().predict("demo", patterns, store.list("demo"))
    prediction_store = PredictionStore(get_settings().intelligence_db_path)
    prediction_store.save_many(predictions)
    recommendations = IntelligenceRecommendationEngine().generate(predictions)
    assert all(item.evidence for item in recommendations)
    assert all(item.project_id == "demo" for item in prediction_store.list("demo"))
    assert prediction_store.list("other") == []
    assert not (get_settings().memory_root / "intelligence" / "demo").exists()
