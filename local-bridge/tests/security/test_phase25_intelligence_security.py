from __future__ import annotations

import inspect

from app.intelligence.observation import ObservationStore
from app.intelligence.pattern_intelligence import PatternIntelligence
from app.intelligence.risk_prediction import PredictionEngine
from app.memory.intelligence import IntelligenceMemory


def test_intelligence_components_have_no_command_execution_path():
    sources = "".join(inspect.getsource(item) for item in (ObservationStore, PatternIntelligence, PredictionEngine, IntelligenceMemory))
    assert "subprocess" not in sources
    assert "shell" not in sources.lower()
    assert "mark_approved" not in sources
    assert "ControlledExecutor" not in sources


def test_prediction_and_recommendation_are_not_actions(bridge):
    pending = bridge.client.post("/intelligence/observations/record", json={"project_id": "demo", "type": "error_event", "source": "test", "summary": "failure token=SECRET_VALUE", "metadata": {"api_key": "SECRET_VALUE"}})
    assert pending.status_code == 202
    assert bridge.client.get("/intelligence/observations", params={"project": "demo"}).json()["observations"] == []
    assert "SECRET_VALUE" not in str(bridge.client.get("/intelligence/predictions", params={"project": "demo"}).json())
    assert "SECRET_VALUE" not in str(bridge.client.get("/intelligence/knowledge", params={"project": "demo"}).json())


def test_project_isolation_applies_to_all_new_reads(bridge):
    store = ObservationStore(__import__("app.config", fromlist=["get_settings"]).get_settings().intelligence_db_path)
    store.record(project_id="demo", type="error_event", source="test", summary="demo failure", metadata={"safe": True})
    assert bridge.client.get("/intelligence/observations", params={"project": "other"}).json()["observations"] == []
    assert bridge.client.get("/intelligence/patterns", params={"project": "other"}).json()["patterns"] == []
    assert bridge.client.get("/intelligence/predictions", params={"project": "other"}).json()["predictions"] == []
    assert bridge.client.get("/intelligence/knowledge", params={"project": "other"}).json()["knowledge"] == []


def test_knowledge_never_writes_from_observation_or_prediction(bridge):
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    store = ObservationStore(settings.intelligence_db_path)
    store.record(project_id="demo", type="test_result", source="pytest", summary="test failure", metadata={"status": "failed"})
    store.record(project_id="demo", type="test_result", source="pytest", summary="test failure", metadata={"status": "failed"})
    patterns = PatternIntelligence().detect("demo", store.list("demo"))
    PredictionEngine().predict("demo", patterns, store.list("demo"))
    assert IntelligenceMemory(settings).list("demo") == []
