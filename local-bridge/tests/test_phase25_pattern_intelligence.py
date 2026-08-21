from __future__ import annotations

from app.config import get_settings
from app.intelligence.observation import ObservationStore
from app.intelligence.pattern_intelligence import PatternIntelligence, PatternStore, PatternType


def observations(bridge):
    store = ObservationStore(get_settings().intelligence_db_path)
    store.record(project_id="demo", type="code_change", source="src/auth.py", summary="change authentication boundary", metadata={"file": "src/auth.py"}, timestamp="2026-01-01T00:00:00+00:00")
    store.record(project_id="demo", type="test_result", source="pytest", summary="authentication regression failure", metadata={"status": "failed", "file": "src/auth.py"}, timestamp="2026-01-02T00:00:00+00:00")
    store.record(project_id="demo", type="test_result", source="pytest", summary="authentication regression failure", metadata={"status": "failed", "file": "src/auth.py"}, timestamp="2026-01-03T00:00:00+00:00")
    store.record(project_id="demo", type="dependency_change", source="lockfile", summary="major dependency breaking change", metadata={"package": "demo-lib"})
    store.record(project_id="demo", type="performance_event", source="benchmark", summary="latency degradation increase", metadata={"p95": 900})
    return store.list("demo", limit=100)


def test_pattern_detector_links_every_result_to_observations(bridge):
    items = observations(bridge)
    results = PatternIntelligence().detect("demo", items)
    assert results
    assert all(result.project_id == "demo" and result.evidence for result in results)
    assert any(result.pattern_type is PatternType.REPEATED_FAILURE for result in results)
    assert any(result.pattern_type is PatternType.REGRESSION for result in results)
    assert any(result.pattern_type is PatternType.DEPENDENCY for result in results)
    assert any(result.pattern_type is PatternType.PERFORMANCE_DEGRADATION for result in results)


def test_pattern_store_roundtrip_and_isolation(bridge):
    items = observations(bridge)
    store = PatternStore(get_settings().intelligence_db_path)
    results = PatternIntelligence(store).analyze_and_store("demo", items)
    assert store.list("demo")
    assert store.list("other") == []
    assert store.get(results[0].pattern_id, "other") is None


def test_pattern_detection_is_read_only(bridge):
    items = observations(bridge)
    before = (bridge.demo / "src" / "main.py").read_bytes()
    PatternIntelligence().detect("demo", items)
    assert (bridge.demo / "src" / "main.py").read_bytes() == before
