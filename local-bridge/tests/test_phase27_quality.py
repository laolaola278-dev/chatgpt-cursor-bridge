"""Phase 27 · Intelligence Quality Gate 13.0 and snapshot tests."""

from __future__ import annotations

import pytest

from app.intelligence.phase27 import build_phase27_snapshot
from app.quality.gate13 import QualityGate13Evaluator


class TestQualityGate13:
    def test_defaults_warn_without_data(self) -> None:
        # No evaluation/accuracy records yet: gate 13 follows the gate 11
        # convention and warns rather than passing empty.
        report = QualityGate13Evaluator().evaluate()
        assert report["status"] == "WARN"

    def test_full_data_passes(self) -> None:
        report = QualityGate13Evaluator().evaluate(
            prediction_traceable=True, prediction_count=3,
            evaluation_traceable=True, evaluation_count=3,
            outcome_traceable=True, outcome_count=3,
            accuracy_computable=True, accuracy_count=3,
            recommendation_effectiveness_computable=True, effectiveness_count=2,
            benchmark_runnable=True, benchmark_count=1,
            knowledge_improvement_audited=True, improvement_count=1,
            no_auto_knowledge_write=True, no_permission_bypass=True,
        )
        assert report["status"] == "PASS"
        assert report["quality"] == 100

    def test_has_nine_checks(self) -> None:
        report = QualityGate13Evaluator().evaluate()
        assert len(report["checks"]) == 9
        for check in ("predictionTraceable", "evaluationTraceable", "outcomeTraceable", "accuracyComputable", "recommendationEffectivenessComputable", "benchmarkRunnable", "knowledgeImprovementAudited", "noAutoKnowledgeWrite", "noPermissionBypass"):
            assert check in report["checks"]

    def test_block_on_unverifiable_prediction(self) -> None:
        report = QualityGate13Evaluator().evaluate(prediction_traceable=False, prediction_count=3)
        assert report["status"] == "BLOCK"
        assert "prediction_not_traceable" in report["blockingIssues"]

    def test_block_on_unverifiable_evaluation(self) -> None:
        report = QualityGate13Evaluator().evaluate(evaluation_traceable=False, evaluation_count=2)
        assert report["status"] == "BLOCK"
        assert "evaluation_not_traceable" in report["blockingIssues"]

    def test_block_on_missing_outcome(self) -> None:
        report = QualityGate13Evaluator().evaluate(outcome_traceable=False, outcome_count=1)
        assert report["status"] == "BLOCK"
        assert "outcome_not_traceable" in report["blockingIssues"]

    def test_block_when_accuracy_not_computable(self) -> None:
        report = QualityGate13Evaluator().evaluate(accuracy_computable=False, accuracy_count=5)
        assert report["status"] == "BLOCK"
        assert "accuracy_not_computable" in report["blockingIssues"]

    def test_block_when_effectiveness_not_computable(self) -> None:
        report = QualityGate13Evaluator().evaluate(recommendation_effectiveness_computable=False, effectiveness_count=2)
        assert report["status"] == "BLOCK"

    def test_block_when_benchmark_not_runnable(self) -> None:
        report = QualityGate13Evaluator().evaluate(benchmark_runnable=False, benchmark_count=1)
        assert report["status"] == "BLOCK"

    def test_block_when_improvement_not_audited(self) -> None:
        report = QualityGate13Evaluator().evaluate(knowledge_improvement_audited=False, improvement_count=2)
        assert report["status"] == "BLOCK"

    def test_block_on_auto_knowledge_write(self) -> None:
        report = QualityGate13Evaluator().evaluate(no_auto_knowledge_write=False)
        assert report["status"] == "BLOCK"
        assert "automatic_knowledge_write" in report["blockingIssues"]

    def test_block_on_permission_bypass(self) -> None:
        report = QualityGate13Evaluator().evaluate(no_permission_bypass=False)
        assert report["status"] == "BLOCK"
        assert "permission_bypass" in report["blockingIssues"]

    def test_zero_counts_do_not_block(self) -> None:
        # Flags only block when there are records to verify.
        report = QualityGate13Evaluator().evaluate(prediction_traceable=False, prediction_count=0)
        assert report["status"] == "WARN"

    def test_warn_when_no_evaluations(self) -> None:
        report = QualityGate13Evaluator().evaluate(evaluation_count=0)
        assert report["status"] == "WARN"
        assert "no_evaluations_recorded" in report["warnings"]

    def test_warn_when_no_accuracy_data(self) -> None:
        report = QualityGate13Evaluator().evaluate(accuracy_count=0)
        assert "no_accuracy_data" in report["warnings"]

    def test_blocking_issues_are_deduplicated(self) -> None:
        report = QualityGate13Evaluator().evaluate(blocking_issues=["x", "x", "y"])
        assert report["blockingIssues"].count("x") == 1

    def test_quality_score_counts_checks(self) -> None:
        report = QualityGate13Evaluator().evaluate(no_auto_knowledge_write=False)
        assert report["quality"] == 89

    def test_counts_are_reported(self) -> None:
        report = QualityGate13Evaluator().evaluate(
            prediction_count=3, evaluation_count=4, outcome_count=5,
            accuracy_count=6, effectiveness_count=7, benchmark_count=8, improvement_count=9,
        )
        assert report["predictionCount"] == 3
        assert report["evaluationCount"] == 4
        assert report["outcomeCount"] == 5
        assert report["accuracyCount"] == 6
        assert report["effectivenessCount"] == 7
        assert report["benchmarkCount"] == 8
        assert report["improvementCount"] == 9

    def test_gate_version_is_13(self) -> None:
        assert QualityGate13Evaluator().evaluate()["gate"] == "13.0"

    def test_read_only_flag(self) -> None:
        assert QualityGate13Evaluator().evaluate()["readOnly"] is True

    def test_extra_blocking_issue_causes_block(self) -> None:
        report = QualityGate13Evaluator().evaluate(blocking_issues=["manual_block"])
        assert report["status"] == "BLOCK"
        assert "manual_block" in report["blockingIssues"]

    def test_extra_warning_causes_warn(self) -> None:
        report = QualityGate13Evaluator().evaluate(warnings=["note"])
        assert report["status"] == "WARN"


class TestQuality13Api:
    def test_empty_project_warns(self, bridge) -> None:
        report = bridge.client.get("/quality/v13/demo").json()
        assert report["gate"] == "13.0"
        assert report["status"] == "WARN"
        assert report["evaluationCount"] == 0

    def test_with_evaluations_reports_accuracy(self, bridge) -> None:
        for result in ("correct", "correct", "incorrect"):
            pending = bridge.client.post(
                "/intelligence/evaluation",
                json={
                    "project_id": "demo", "prediction_id": f"pred-{result}",
                    "evaluation_kind": "prediction", "input_context": "",
                    "prediction_result": "claim", "expected_outcome": "expected",
                    "actual_outcome": "actual", "evaluation_result": result,
                    "confidence": 0.7,
                },
            )
            bridge.approve(pending.json()["requestId"])
        report = bridge.client.get("/quality/v13/demo").json()
        assert report["evaluationCount"] == 3
        assert report["accuracyCount"] == 3
        assert report["status"] in ("PASS", "WARN")

    def test_is_project_scoped(self, bridge) -> None:
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
        assert bridge.client.get("/quality/v13/demo").json()["evaluationCount"] == 1
        assert bridge.client.get("/quality/v13/other").json()["evaluationCount"] == 0

    def test_benchmarks_are_counted(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "m"},
        )
        bridge.approve(pending.json()["requestId"])
        report = bridge.client.get("/quality/v13/demo").json()
        assert report["benchmarkCount"] == 1

    def test_improvements_are_counted(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/knowledge/improvements/propose",
            json={
                "project_id": "demo", "evaluation_id": "eval-1", "prediction_id": "pred-1",
                "category": "patterns", "content": "pattern", "evidence": [], "confidence": 0.5,
            },
        )
        bridge.approve(pending.json()["requestId"])
        report = bridge.client.get("/quality/v13/demo").json()
        assert report["improvementCount"] == 1


class TestPhase27Snapshot:
    def test_snapshot_is_read_only_composition(self, bridge) -> None:
        from app.config import get_settings

        snapshot = build_phase27_snapshot(get_settings(), "demo")
        data = snapshot.as_dict()
        assert data["project"] == "demo"
        assert data["readOnly"] is True
        assert data["accuracy"]["counted"] == 0
        assert data["effectivenessSummary"]["total"] == 0
        assert len(data["builtinDatasets"]) == 3

    def test_snapshot_reflects_approved_records(self, bridge) -> None:
        from app.config import get_settings

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
        data = build_phase27_snapshot(get_settings(), "demo").as_dict()
        assert data["accuracy"]["counted"] == 1
        assert data["accuracy"]["accuracy"] == 1.0

    def test_snapshot_has_quality_gate(self, bridge) -> None:
        from app.config import get_settings

        data = build_phase27_snapshot(get_settings(), "demo").as_dict()
        assert data["quality13"]["gate"] == "13.0"

    def test_snapshot_contains_failed_predictions(self, bridge) -> None:
        from app.config import get_settings

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
        data = build_phase27_snapshot(get_settings(), "demo").as_dict()
        assert len(data["failedPredictions"]) == 1

    def test_snapshot_is_project_scoped(self, bridge) -> None:
        from app.config import get_settings

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
        assert build_phase27_snapshot(get_settings(), "demo").as_dict()["accuracy"]["counted"] == 1
        assert build_phase27_snapshot(get_settings(), "other").as_dict()["accuracy"]["counted"] == 0
