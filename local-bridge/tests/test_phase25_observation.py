from __future__ import annotations

from app.config import get_settings
from app.intelligence.observation import ObservationStore, ObservationType


def test_observation_store_persists_and_is_project_scoped(bridge):
    store = ObservationStore(get_settings().intelligence_db_path)
    first = store.record(project_id="demo", type=ObservationType.TEST_RESULT, source="pytest", summary="test failed", metadata={"status": "failed"}, risk_level="high")
    store.record(project_id="other", type=ObservationType.BUILD_RESULT, source="ci", summary="build failed")
    assert store.get(first.id, "demo").project_id == "demo"
    assert [item.project_id for item in store.list("demo")] == ["demo"]
    assert store.list("other")[0].project_id == "other"
    assert store.audit_entries("demo")


def test_observation_metadata_is_secret_scrubbed(bridge):
    store = ObservationStore(get_settings().intelligence_db_path)
    item = store.record(project_id="demo", type="error_event", source="runner", summary="request failed with token=SUPER_SECRET", metadata={"token": "SUPER_SECRET", "nested": {"password": "pw"}, "safe": "kept"})
    payload = item.as_dict()
    assert "SUPER_SECRET" not in str(payload)
    assert payload["metadata"]["token"] == "[REDACTED]"
    assert payload["metadata"]["safe"] == "kept"


def test_observation_api_stays_pending_until_human_approval(bridge):
    pending = bridge.client.post("/intelligence/observations/record", json={"project_id": "demo", "type": "code_change", "source": "git", "summary": "changed parser", "metadata": {"token": "NO_LEAK"}})
    assert pending.status_code == 202
    assert bridge.client.get("/intelligence/observations", params={"project": "demo"}).json()["observations"] == []
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    rows = bridge.client.get("/intelligence/observations", params={"project": "demo"}).json()["observations"]
    assert len(rows) == 1 and "NO_LEAK" not in str(rows)
    assert bridge.client.get("/memory/intelligence/history", params={"project": "demo"}).status_code in {200, 404}
