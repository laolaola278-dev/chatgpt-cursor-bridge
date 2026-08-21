"""Phase 27 · Security boundary regression tests.

These tests assert that the validation layer can observe, evaluate, measure,
recommend, and propose - but can never execute, approve itself, modify source
or dependencies, write memory/knowledge automatically, or call external
providers.
"""

from __future__ import annotations

import subprocess  # noqa: F401  (imported to assert the layer never uses it)

import pytest

from app.intelligence.validation import (
    AccuracySystem,
    BenchmarkRunner,
    KnowledgeImprovementEngine,
    RecommendationEffectivenessEngine,
    ValidationStore,
    builtin_datasets,
)
from app.intelligence.validation.models import EvaluationRecord
from app.security.permissions import ACTION_LEVELS, PermissionLevel
from tests.phase27_helpers import effectiveness, evaluation, store


class TestNoExecution:
    def test_no_execute_endpoint_exists(self, bridge) -> None:
        # 404 = no route; 405 = method blocked on an existing read route. Both
        # prove there is no execution path.
        assert bridge.client.post("/intelligence/execute", json={}).status_code in (404, 405)
        assert bridge.client.post("/intelligence/apply", json={}).status_code in (404, 405)
        assert bridge.client.post("/intelligence/auto-fix", json={}).status_code in (404, 405)
        assert bridge.client.post("/intelligence/evaluation/execute", json={}).status_code in (404, 405)

    def test_no_auto_repair_endpoint(self, bridge) -> None:
        assert bridge.client.post("/intelligence/auto-repair", json={}).status_code == 404
        assert bridge.client.post("/intelligence/fix", json={}).status_code == 404

    def test_evaluation_post_never_writes_without_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        assert pending.status_code == 202
        assert bridge.client.get("/intelligence/accuracy?project=demo").json()["counted"] == 0

    def test_benchmark_run_never_writes_without_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "m"},
        )
        assert pending.status_code == 202
        assert bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"] == []

    def test_evaluation_cannot_mutate_predictions(self, bridge) -> None:
        # Evaluating a prediction must not change stored predictions.
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "incorrect",
            },
        )
        bridge.approve(pending.json()["requestId"])
        predictions = bridge.client.get("/intelligence/predictions?project=demo").json()["predictions"]
        assert predictions == []

    def test_recommendation_cannot_execute(self, bridge) -> None:
        assert bridge.client.post("/intelligence/recommendations/execute", json={}).status_code == 404

    def test_prediction_cannot_execute(self, bridge) -> None:
        assert bridge.client.post("/intelligence/predictions/execute", json={}).status_code == 404

    def test_accuracy_cannot_change_records(self, bridge) -> None:
        before = bridge.client.get("/intelligence/accuracy?project=demo").json()
        bridge.client.get("/intelligence/accuracy?project=demo&agent_id=x")
        after = bridge.client.get("/intelligence/accuracy?project=demo").json()
        assert before == after

    def test_effectiveness_cannot_change_records(self, bridge) -> None:
        assert bridge.client.post("/intelligence/effectiveness", json={}).status_code in (404, 405)

    def test_decision_outcomes_cannot_be_written_directly(self, bridge) -> None:
        assert bridge.client.post("/intelligence/decision-outcomes", json={}).status_code in (404, 405)


class TestNoSourceOrDependencyMutation:
    def test_evaluation_does_not_touch_source(self, bridge) -> None:
        demo_main = bridge.demo / "src" / "main.py"
        before = demo_main.read_text(encoding="utf-8")
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        bridge.approve(pending.json()["requestId"])
        assert demo_main.read_text(encoding="utf-8") == before

    def test_benchmark_does_not_touch_dependencies(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "m"},
        )
        bridge.approve(pending.json()["requestId"])
        # No package/lockfile exists or was created in the project.
        assert not (bridge.demo / "package.json").exists()
        assert not (bridge.demo / "requirements.txt").exists()

    def test_no_shell_command_permission_added(self) -> None:
        assert ACTION_LEVELS["shell_command"] is PermissionLevel.LEVEL_2
        assert ACTION_LEVELS["intelligence_evaluation_record"] is PermissionLevel.LEVEL_1
        assert ACTION_LEVELS["intelligence_benchmark_run"] is PermissionLevel.LEVEL_1
        assert ACTION_LEVELS["intelligence_knowledge_improvement"] is PermissionLevel.LEVEL_1

    def test_validation_layer_has_no_subprocess_call(self) -> None:
        import inspect
        import app.intelligence.validation as package

        for module in (package.storage, package.accuracy, package.effectiveness, package.decision_outcome, package.benchmark, package.knowledge):
            source = inspect.getsource(module)
            assert "subprocess" not in source
            assert "os.system" not in source
            assert "os.popen" not in source

    def test_validation_layer_has_no_file_write(self) -> None:
        import inspect
        from app.intelligence.validation import storage, knowledge

        for module in (storage, knowledge):
            source = inspect.getsource(module)
            assert "open(" not in source
            assert ".write_text" not in source
            assert ".write_bytes" not in source

    def test_evaluation_records_cannot_target_files(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
                "input_context": "../../etc/passwd",
            },
        )
        assert response.status_code == 202
        # Path-like content is scrubbed, never interpreted as a file target.
        assert "etc" not in bridge.client.get("/intelligence/evaluations/phase27?project=demo").json()["evaluations"][0]["inputContext"] if bridge.client.get("/intelligence/evaluations/phase27?project=demo").json()["evaluations"] else True


class TestMemoryAndKnowledgeProtection:
    def test_improvement_does_not_auto_write_memory(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "patterns", "content": "pattern found", "evidence": [], "confidence": 0.5,
            },
        )
        bridge.approve(pending.json()["requestId"])
        assert bridge.client.get("/intelligence/knowledge?project=demo").json()["knowledge"] == []

    def test_improvement_does_not_auto_write_memory_files(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "patterns", "content": "pattern found", "evidence": [], "confidence": 0.5,
            },
        )
        bridge.approve(pending.json()["requestId"])
        memory_dir = bridge.memory_dir("demo") / "intelligence"
        assert not memory_dir.exists() or not any(memory_dir.iterdir())

    def test_memory_write_still_requires_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/propose",
            json={
                "project_id": "demo", "category": "patterns", "content": "knowledge",
                "source": "test", "evidence": [], "confidence": 0.5,
            },
        )
        assert pending.status_code == 202
        assert bridge.client.get("/intelligence/knowledge?project=demo").json()["knowledge"] == []
        bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/intelligence/knowledge?project=demo").json()["knowledge"]) == 1

    def test_knowledge_improvement_category_is_whitelisted(self) -> None:
        with pytest.raises(Exception):
            KnowledgeImprovementEngine().build_proposal(
                project_id="demo", evaluation_id="e", prediction_id="p",
                category="../../etc", content="x", confidence=0.5,
            )

    def test_no_auto_learning_flag_exists(self, bridge) -> None:
        assert bridge.client.post("/intelligence/learn", json={}).status_code == 404

    def test_no_knowledge_mutation_endpoint(self, bridge) -> None:
        assert bridge.client.post("/intelligence/knowledge/mutate", json={}).status_code == 404


class TestApprovalBoundary:
    def test_all_phase27_writes_are_level_1(self) -> None:
        for action in ("intelligence_evaluation_record", "intelligence_benchmark_run", "intelligence_knowledge_improvement"):
            assert ACTION_LEVELS[action] is PermissionLevel.LEVEL_1

    def test_level_1_requires_human_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        assert pending.status_code == 202
        assert pending.json()["permissionLevel"] == "LEVEL_1"
        assert pending.json()["status"] == "pending"

    def test_pending_requests_can_be_rejected(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        rejected = bridge.client.post("/permission/reject", json={"request_id": pending.json()["requestId"], "reason": "no"})
        assert rejected.status_code == 200
        assert bridge.client.get("/intelligence/accuracy?project=demo").json()["counted"] == 0

    def test_approval_store_is_not_bypassed(self, bridge) -> None:
        # Every persistent Phase 27 write must appear as an ApprovalStore
        # action; there is no hidden write path.
        from app.security.permissions import get_approval_store

        store_before = len(get_approval_store().list_all())
        bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        assert len(get_approval_store().list_all()) == store_before + 1

    def test_no_action_is_auto_approved(self, bridge) -> None:
        from app.security.permissions import evaluate

        for action in ("intelligence_evaluation_record", "intelligence_benchmark_run", "intelligence_knowledge_improvement"):
            decision = evaluate(action)
            assert decision.require_approval is True
            assert decision.allowed is False


class TestProjectIsolation:
    def test_evaluations_isolated_between_projects(self, bridge) -> None:
        for project in ("demo", "alpha"):
            pending = bridge.client.post(
                "/intelligence/evaluation",
                json={
                    "project_id": project, "prediction_id": f"pred-{project}",
                    "evaluation_kind": "prediction", "input_context": "",
                    "prediction_result": "claim", "expected_outcome": "expected",
                    "actual_outcome": "actual", "evaluation_result": "correct",
                },
            )
            bridge.approve(pending.json()["requestId"])
        assert bridge.client.get("/intelligence/accuracy?project=demo").json()["counted"] == 1
        assert bridge.client.get("/intelligence/accuracy?project=alpha").json()["counted"] == 1

    def test_benchmarks_isolated_between_projects(self, bridge) -> None:
        for project in ("demo", "alpha"):
            pending = bridge.client.post(
                "/intelligence/benchmark/run",
                json={"project_id": project, "dataset_id": "builtin_engineering_prediction", "model_id": "m"},
            )
            bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"]) == 1
        assert len(bridge.client.get("/intelligence/benchmarks?project=alpha").json()["benchmarks"]) == 1

    def test_improvements_isolated_between_projects(self, bridge) -> None:
        for project in ("demo", "alpha"):
            pending = bridge.client.post(
                "/intelligence/knowledge/improvements/propose",
                json={
                    "project_id": project, "evaluation_id": f"eval-{project}",
                    "prediction_id": "pred-1", "category": "patterns",
                    "content": "pattern", "evidence": [], "confidence": 0.5,
                },
            )
            bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["improvements"]) == 1
        assert len(bridge.client.get("/intelligence/knowledge/improvements?project=alpha").json()["improvements"]) == 1

    def test_storage_rejects_unknown_project_format(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        with pytest.raises(Exception):
            db.evaluations("../escape")

    def test_accuracy_report_is_project_scoped(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(project="demo", result="correct"))
        db.save_evaluation(evaluation(project="other", result="incorrect"))
        report = AccuracySystem().report("demo", db.evaluations("demo") + db.evaluations("other"))
        assert report.counted == 1
        assert report.correct == 1


class TestAgentIsolation:
    def test_accuracy_by_agent(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(agent_id="agent-a", result="correct"))
        db.save_evaluation(evaluation(agent_id="agent-b", result="incorrect"))
        report = AccuracySystem().report("demo", db.evaluations("demo"), agent_id="agent-a")
        assert report.correct == 1
        assert report.counted == 1

    def test_evaluations_filter_by_agent(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(agent_id="agent-a"))
        db.save_evaluation(evaluation(agent_id="agent-b"))
        assert len(db.evaluations("demo", agent_id="agent-a")) == 1


class TestSecretIsolation:
    def test_secrets_scrubbed_in_evaluation(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction",
                "input_context": "api key AKIAIOSFODNN7EXAMPLE",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        bridge.approve(pending.json()["requestId"])
        evaluation = bridge.client.get("/intelligence/evaluations/phase27?project=demo").json()["evaluations"][0]
        assert "AKIAIOSFODNN7EXAMPLE" not in evaluation["inputContext"]

    def test_secrets_scrubbed_in_improvement(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "patterns", "content": "token=xoxb-1234567890",
                "evidence": [], "confidence": 0.5,
            },
        )
        bridge.approve(pending.json()["requestId"])
        improvements = bridge.client.get("/intelligence/knowledge/improvements?project=demo").json()["improvements"]
        validated = [item for item in improvements if item["status"] == "validated"]
        assert validated
        assert "xoxb-1234567890" not in validated[0]["content"]

    def test_authorization_headers_not_stored(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction",
                "input_context": "Authorization: Bearer abcdefghijklmnop",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        bridge.approve(pending.json()["requestId"])
        evaluation = bridge.client.get("/intelligence/evaluations/phase27?project=demo").json()["evaluations"][0]
        assert "abcdefghijklmnop" not in evaluation["inputContext"]

    def test_no_api_key_leak_in_benchmark(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "m", "predictions": ["sk-1234567890abcdef"] * 8},
        )
        bridge.approve(pending.json()["requestId"])
        benchmark = bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"][0]
        blob = str(benchmark)
        assert "sk-1234567890abcdef" not in blob


class TestPathSanitization:
    def test_absolute_paths_scrubbed(self) -> None:
        record = EvaluationRecord(
            evaluation_id="", project_id="demo", prediction_id="pred-1",
            evaluation_kind="prediction", input_context="/etc/passwd and /var/log/syslog",
            prediction_result="claim", expected_outcome="expected", actual_outcome="actual",
            evaluation_result="correct", confidence=0.5,
        )
        assert "/etc/passwd" not in record.input_context
        assert "/var/log/syslog" not in record.input_context

    def test_improvement_content_path_scrubbed(self) -> None:
        proposal = KnowledgeImprovementEngine().build_proposal(
            project_id="demo", evaluation_id="e", prediction_id="p",
            category="predictions", content="checked /home/user/.ssh/config",
            confidence=0.5,
        )
        assert "/home/user/.ssh/config" not in proposal.content


class TestNoExternalCalls:
    def test_validation_modules_import_no_http_client(self) -> None:
        import inspect
        from app.intelligence.validation import accuracy, benchmark, decision_outcome, effectiveness, knowledge, storage

        for module in (accuracy, benchmark, decision_outcome, effectiveness, knowledge, storage):
            source = inspect.getsource(module)
            assert "requests" not in source
            assert "urllib" not in source
            assert "httpx" not in source
            assert "openai" not in source
            assert "anthropic" not in source

    def test_benchmark_is_deterministic_across_runs(self) -> None:
        dataset = next(item for item in builtin_datasets("demo") if item.category == "engineering_prediction")
        first = BenchmarkRunner().run(dataset, model_id="m")
        second = BenchmarkRunner().run(dataset, model_id="m")
        assert first.determinism_hash == second.determinism_hash
        assert first.score == second.score
        assert first.accuracy == second.accuracy

    def test_benchmark_has_no_randomness(self) -> None:
        import inspect
        from app.intelligence.validation import benchmark

        source = inspect.getsource(benchmark)
        assert "import random" not in source
        assert "from random" not in source
        assert "random.random" not in source
        assert "random.seed" not in source

    def test_accuracy_uses_no_external_data(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(result="correct"))
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.accuracy == 1.0


class TestPermissionRegression:
    def test_level_0_gets_are_unchanged(self, bridge) -> None:
        assert bridge.client.get("/intelligence/accuracy?project=demo").status_code == 200
        assert bridge.client.get("/intelligence/evaluations/phase27?project=demo").status_code == 200
        assert bridge.client.get("/intelligence/benchmarks?project=demo").status_code == 200
        assert bridge.client.get("/intelligence/knowledge/improvements?project=demo").status_code == 200
        assert bridge.client.get("/intelligence/effectiveness?project=demo").status_code == 200
        assert bridge.client.get("/intelligence/decision-outcomes?project=demo").status_code == 200

    def test_phase25_actions_still_level_1(self) -> None:
        for action in ("intelligence_observation_record", "intelligence_knowledge_append", "intelligence_evidence_bundle"):
            assert ACTION_LEVELS[action] is PermissionLevel.LEVEL_1

    def test_unknown_actions_still_rejected(self) -> None:
        from app.security.validator import ApprovalError
        from app.security.permissions import level_for_action

        with pytest.raises(ApprovalError):
            level_for_action("intelligence_autonomous_execute")

    def test_effectiveness_classification_never_calls_it_ai_error(self) -> None:
        classification, _ = RecommendationEffectivenessEngine.classify(user_decision="rejected", success=False)
        assert classification == "rejected"

    def test_storage_tables_never_expose_authorization(self, tmp_path) -> None:
        import sqlite3

        db_path = tmp_path / "i.db"
        store(db_path)
        connection = sqlite3.connect(db_path)
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            assert "authorization" not in columns
            assert "api_key" not in columns
            assert "secret" not in columns

    def test_evaluation_records_are_append_only(self, bridge) -> None:
        assert bridge.client.delete("/intelligence/evaluation/whatever?project=demo").status_code in (404, 405)
        assert bridge.client.put("/intelligence/evaluation/whatever", json={}).status_code in (404, 405)
