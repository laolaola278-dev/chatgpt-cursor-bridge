from __future__ import annotations

from app.config import get_settings
from app.memory.intelligence import IntelligenceMemory


def test_knowledge_preview_does_not_write(bridge):
    memory = IntelligenceMemory(get_settings())
    preview = memory.preview("demo", "patterns", "Repeated failure", source="test_result", evidence=["obs_1"], confidence=0.7)
    assert "proposal" in preview
    assert memory.list("demo") == []


def test_knowledge_categories_store_source_evidence_confidence(bridge):
    memory = IntelligenceMemory(get_settings())
    for category in ("patterns", "predictions", "strategies", "outcomes"):
        memory.append_after_approval("demo", category, f"{category} record", source="human_review", evidence=[f"{category}_1"], confidence=0.8)
    records = memory.list("demo")
    assert {item["category"] for item in records} == {"patterns", "predictions", "strategies", "outcomes"}
    assert all(item["source"] == "human_review" and item["confidence"] == 0.8 for item in records)


def test_knowledge_api_needs_second_approval(bridge):
    body = {"project_id": "demo", "category": "patterns", "content": "approved pattern", "source": "human", "evidence": ["obs_1"], "confidence": 0.8}
    pending = bridge.client.post("/intelligence/knowledge/propose", json=body)
    assert pending.status_code == 202
    assert bridge.client.get("/intelligence/knowledge", params={"project": "demo"}).json()["knowledge"] == []
    assert bridge.approve(pending.json()["requestId"]).status_code == 200
    assert bridge.client.get("/intelligence/knowledge", params={"project": "demo"}).json()["knowledge"][0]["source"] == "human"
