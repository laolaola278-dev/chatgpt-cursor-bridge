from __future__ import annotations

import inspect

import pytest

from app.intelligence import correlation, dependency, evaluation, evidence_graph, impact_prediction, trends
from app.intelligence.common import sanitize_metadata, sanitize_text
from app.intelligence.observation import ObservationStore
from app.memory.intelligence import IntelligenceMemory
from app.config import get_settings


@pytest.mark.parametrize("index", list(range(110)))
def test_secret_corpus_never_enters_phase26_observation_or_results(bridge, index):
    secret = f"SECRET_PHASE26_{index}_token"
    pending = bridge.client.post("/intelligence/observations/record", json={"project_id": "demo", "type": "error_event", "source": "security", "summary": f"token={secret}", "metadata": {f"secret_{index}": secret, "nested": {"api_key": secret}}})
    assert pending.status_code == 202
    assert secret not in str(bridge.client.get("/intelligence/trends", params={"project": "demo"}).json())
    assert secret not in str(bridge.client.get("/intelligence/correlations", params={"project": "demo"}).json())
    assert secret not in str(bridge.client.get("/intelligence/impact", params={"project": "demo"}).json())
    assert secret not in str(bridge.client.get("/intelligence/dependencies", params={"project": "demo"}).json())
    assert secret not in str(bridge.client.get("/intelligence/evidence/graph", params={"project": "demo"}).json())


def test_phase26_modules_have_no_shell_or_executor_imports():
    components = [trends.EngineeringTrendEngine, correlation.FailureCorrelationEngine, dependency.DependencyRiskAnalyzer, evaluation.PredictionEvaluator, evidence_graph.IntelligenceEvidenceGraph, impact_prediction.ChangeImpactPredictionEngine]
    source = "".join(inspect.getsource(item) for item in components).lower()
    assert "subprocess" not in source
    assert "controlledexecutor" not in source
    assert "mark_approved" not in source
    assert "shell" not in source


def test_prediction_and_recommendation_do_not_create_pending_actions(bridge):
    before = len(bridge.client.get("/permission/pending").json()["pending"])
    bridge.client.get("/intelligence/trends", params={"project": "demo"})
    bridge.client.get("/intelligence/recommendations/ranking", params={"project": "demo"})
    bridge.client.get("/intelligence/evidence/graph", params={"project": "demo"})
    after = len(bridge.client.get("/permission/pending").json()["pending"])
    assert before == after


def test_memory_categories_are_not_written_by_reads(bridge):
    settings = get_settings()
    before = IntelligenceMemory(settings).list("demo")
    bridge.client.get("/intelligence/trends", params={"project": "demo"})
    bridge.client.get("/intelligence/evaluations", params={"project": "demo"})
    bridge.client.get("/intelligence/evidence/graph", params={"project": "demo"})
    assert IntelligenceMemory(settings).list("demo") == before


def test_memory_proposal_still_requires_approval(bridge):
    response = bridge.client.post("/intelligence/knowledge/propose", json={"project_id": "demo", "category": "trends", "content": "trend evidence", "source": "phase26", "evidence": ["obs-1"], "confidence": 0.5})
    assert response.status_code == 202
    assert IntelligenceMemory(get_settings()).list("demo") == []


def test_project_isolation_for_stored_phase25_observations(bridge):
    store = ObservationStore(get_settings().intelligence_db_path)
    store.record(project_id="demo", type="error_event", source="runner", summary="demo error")
    assert bridge.client.get("/intelligence/trends", params={"project": "other"}).json()["trends"] == []
    assert bridge.client.get("/intelligence/evidence/graph", params={"project": "other"}).json()["nodes"] == []


def test_path_and_authorization_like_inputs_are_sanitized():
    assert "<internal-path>" in sanitize_text("/home/daytona/workspace/projects/demo/src/main.py")
    cleaned = sanitize_metadata({"authorization": "Bearer SECRET", "path": "/home/daytona/private/file.py", "safe": "value"})
    assert cleaned["authorization"] == "[REDACTED]"
    assert "SECRET" not in str(cleaned)
    assert "<internal-path>" in cleaned["path"]


def test_graph_is_metadata_only():
    source = inspect.getsource(evidence_graph.IntelligenceEvidenceGraph)
    assert "open(" not in source
    assert "execute(" not in source
    assert "save(" not in source
    assert "connection" not in source


def test_evaluation_does_not_mutate_prediction():
    from app.intelligence.evaluation import PredictionEvaluator
    from app.intelligence.outcome import OutcomeStore
    from app.intelligence.risk_prediction import PredictionResult, PredictionType
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory() as directory:
        prediction = PredictionResult("p", "demo", PredictionType.TEST_FAILURE_RISK, "risk", 0.7, ["obs"], ["obs"], "high")
        before = prediction.as_dict()
        outcome = OutcomeStore(Path(directory) / "out.db").record(project_id="demo", strategy_id="s", status="FAILURE", expected_outcome="pass", actual_outcome="fail")
        PredictionEvaluator().evaluate(prediction, outcome)
        assert prediction.as_dict() == before
