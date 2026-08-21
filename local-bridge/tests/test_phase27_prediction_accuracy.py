"""Phase 27 · Prediction Accuracy System tests."""

from __future__ import annotations

import pytest

from app.intelligence.validation import AccuracySystem, ValidationStore
from app.intelligence.validation.models import EvaluationRecord
from tests.phase27_helpers import evaluation, store


def _seed(db, rows) -> None:
    for index, row in enumerate(rows):
        db.save_evaluation(evaluation(**row, prediction_id=f"pred-{index}"))


class TestAccuracyMetrics:
    def test_empty_project_has_zero_metrics(self, tmp_path) -> None:
        report = AccuracySystem().report("demo", [])
        assert report.counted == 0
        assert report.accuracy == 0.0
        assert report.precision == 0.0
        assert report.recall == 0.0

    def test_all_correct(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct", "confidence": 0.8}] * 4)
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.counted == 4
        assert report.correct == 4
        assert report.accuracy == 1.0

    def test_accuracy_is_correct_over_counted(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct"}, {"result": "correct"}, {"result": "incorrect"}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.counted == 3
        assert report.correct == 2
        assert report.accuracy == pytest.approx(2 / 3, abs=0.001)

    def test_partial_counts_as_incorrect_but_is_tracked(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct"}, {"result": "partial"}, {"result": "incorrect"}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.counted == 3
        assert report.correct == 1
        assert report.partial == 1

    def test_unknown_is_excluded_from_denominator(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct"}, {"result": "unknown"}, {"result": "unknown"}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.predictions == 3
        assert report.counted == 1
        assert report.accuracy == 1.0
        assert report.unknown == 2

    def test_precision_and_recall(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [
            {"result": "correct", "confidence": 0.9},  # TP
            {"result": "correct", "confidence": 0.9},  # TP
            {"result": "incorrect", "confidence": 0.9},  # FP
            {"result": "incorrect", "confidence": 0.2},  # FN
        ])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.false_positive == 1
        assert report.false_negative == 1
        assert report.precision == pytest.approx(2 / 3, abs=0.001)
        assert report.recall == pytest.approx(2 / 3, abs=0.001)

    def test_false_positive_and_negative_rates(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [
            {"result": "correct", "confidence": 0.9},
            {"result": "correct", "confidence": 0.1},
            {"result": "incorrect", "confidence": 0.9},
        ])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.false_positive_rate == pytest.approx(1 / 2, abs=0.001)
        assert report.false_negative_rate == pytest.approx(0.0, abs=0.001)

    def test_success_rate_matches_accuracy(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct"}] * 3 + [{"result": "incorrect"}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.success_rate == pytest.approx(0.75, abs=0.001)
        assert report.success_rate == report.accuracy

    def test_report_is_project_scoped(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct"}] * 3)
        db.save_evaluation(evaluation(project="other", result="incorrect"))
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.counted == 3
        assert report.accuracy == 1.0

    def test_by_kind_breakdown(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"kind": "prediction", "result": "correct"}, {"kind": "prediction", "result": "incorrect"}, {"kind": "failure_prediction", "result": "correct"}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert report.by_kind["prediction"]["counted"] == 2
        assert report.by_kind["prediction"]["accuracy"] == pytest.approx(0.5, abs=0.001)
        assert report.by_kind["failure_prediction"]["accuracy"] == 1.0


class TestConfidenceCalibration:
    def test_calibration_bins_exist(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct", "confidence": 0.5}] * 2)
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        assert len(report.calibration) == 5

    def test_bin_counts_and_accuracy(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct", "confidence": 0.9}] * 2 + [{"result": "incorrect", "confidence": 0.9}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        high = [bin_ for bin_ in report.calibration if bin_.lower == 0.8][0]
        assert high.count == 3
        assert high.correct == 2
        assert high.bin_accuracy == pytest.approx(2 / 3, abs=0.001)

    def test_calibration_error_is_zero_when_perfectly_calibrated(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct", "confidence": 0.9}] * 9 + [{"result": "incorrect", "confidence": 0.9}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        high = [bin_ for bin_ in report.calibration if bin_.lower == 0.8][0]
        assert report.calibration_error == pytest.approx(abs(high.bin_accuracy - high.bin_mean_confidence), abs=0.001)

    def test_calibration_error_zero_when_empty(self, tmp_path) -> None:
        report = AccuracySystem().report("demo", [])
        assert report.calibration_error == 0.0

    def test_bin_confidence_is_mean_of_records(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct", "confidence": 0.6}, {"result": "correct", "confidence": 0.7}])
        report = AccuracySystem().report("demo", db.evaluations("demo"))
        mid = [bin_ for bin_ in report.calibration if bin_.lower == 0.6][0]
        assert mid.bin_mean_confidence == pytest.approx(0.65)


class TestAccuracyFilters:
    def test_filter_by_agent(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(agent_id="agent-1", result="correct"))
        db.save_evaluation(evaluation(agent_id="agent-2", result="incorrect"))
        records = db.evaluations("demo")
        report = AccuracySystem().report("demo", records, agent_id="agent-1")
        assert report.counted == 1
        assert report.correct == 1

    def test_filter_by_model(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(model_id="router", result="correct"))
        db.save_evaluation(evaluation(model_id="coder", result="incorrect"))
        report = AccuracySystem().report("demo", db.evaluations("demo"), model_id="coder")
        assert report.counted == 1
        assert report.correct == 0

    def test_filter_by_kind(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(kind="prediction", result="correct"))
        db.save_evaluation(evaluation(kind="failure_prediction", result="incorrect"))
        report = AccuracySystem().report("demo", db.evaluations("demo"), kind="failure_prediction")
        assert report.counted == 1
        assert report.correct == 0

    def test_filter_by_time_range(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        old = evaluation(result="correct")
        old = EvaluationRecord(
            evaluation_id="", project_id=old.project_id, prediction_id=old.prediction_id,
            evaluation_kind=old.evaluation_kind, input_context=old.input_context,
            prediction_result=old.prediction_result, expected_outcome=old.expected_outcome,
            actual_outcome=old.actual_outcome, evaluation_result=old.evaluation_result,
            confidence=old.confidence, evaluated_at="2026-01-01T00:00:00+00:00",
        )
        db.save_evaluation(old)
        db.save_evaluation(evaluation(result="incorrect"))
        records = db.evaluations("demo")
        report = AccuracySystem().report("demo", records, since="2026-01-02T00:00:00+00:00")
        assert report.counted == 1
        assert report.correct == 0
        assert report.accuracy == 0.0

    def test_filter_until(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        old = evaluation(result="correct")
        old = EvaluationRecord(
            evaluation_id="", project_id=old.project_id, prediction_id=old.prediction_id,
            evaluation_kind=old.evaluation_kind, input_context=old.input_context,
            prediction_result=old.prediction_result, expected_outcome=old.expected_outcome,
            actual_outcome=old.actual_outcome, evaluation_result=old.evaluation_result,
            confidence=old.confidence, evaluated_at="2026-01-01T00:00:00+00:00",
        )
        db.save_evaluation(old)
        db.save_evaluation(evaluation(result="incorrect"))
        report = AccuracySystem().report("demo", db.evaluations("demo"), until="2026-01-02T00:00:00+00:00")
        assert report.counted == 1
        assert report.correct == 1

    def test_filters_reported_in_output(self, tmp_path) -> None:
        report = AccuracySystem().report("demo", [], agent_id="a", model_id="m", kind="prediction", since="s", until="u")
        assert report.filters["agentId"] == "a"
        assert report.filters["modelId"] == "m"

    def test_mixed_filters_combine(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(agent_id="a", model_id="m", result="correct"))
        db.save_evaluation(evaluation(agent_id="a", model_id="x", result="incorrect"))
        db.save_evaluation(evaluation(agent_id="b", model_id="m", result="incorrect"))
        report = AccuracySystem().report("demo", db.evaluations("demo"), agent_id="a", model_id="m")
        assert report.counted == 1
        assert report.correct == 1


class TestFailedPredictions:
    def test_failed_predictions_returns_incorrect_only(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "correct"}, {"result": "incorrect"}, {"result": "partial"}])
        failed = AccuracySystem().failed_predictions(db.evaluations("demo"))
        assert len(failed) == 2

    def test_failed_predictions_orders_newest_first(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        first = evaluation(result="incorrect")
        first = EvaluationRecord(
            evaluation_id="", project_id=first.project_id, prediction_id=first.prediction_id,
            evaluation_kind=first.evaluation_kind, input_context=first.input_context,
            prediction_result=first.prediction_result, expected_outcome=first.expected_outcome,
            actual_outcome=first.actual_outcome, evaluation_result=first.evaluation_result,
            confidence=first.confidence, evaluated_at="2026-01-01T00:00:00+00:00",
        )
        second = evaluation(result="incorrect")
        second = EvaluationRecord(
            evaluation_id="", project_id=second.project_id, prediction_id=second.prediction_id,
            evaluation_kind=second.evaluation_kind, input_context=second.input_context,
            prediction_result=second.prediction_result, expected_outcome=second.expected_outcome,
            actual_outcome=second.actual_outcome, evaluation_result=second.evaluation_result,
            confidence=second.confidence, evaluated_at="2026-01-02T00:00:00+00:00",
        )
        db.save_evaluation(first)
        db.save_evaluation(second)
        failed = AccuracySystem().failed_predictions(db.evaluations("demo"))
        assert failed[0]["evaluationId"] == second.evaluation_id
        assert failed[1]["evaluationId"] == first.evaluation_id

    def test_failed_predictions_respects_limit(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        _seed(db, [{"result": "incorrect"}] * 5)
        assert len(AccuracySystem().failed_predictions(db.evaluations("demo"), limit=2)) == 2

    def test_failed_predictions_are_read_only_dicts(self, tmp_path) -> None:
        db = store(tmp_path / "i.db")
        db.save_evaluation(evaluation(result="incorrect"))
        item = AccuracySystem().failed_predictions(db.evaluations("demo"))[0]
        assert item["readOnly"] is True
        assert item["predictionId"] == "pred-1"


class TestAccuracyApi:
    def test_accuracy_endpoint_empty(self, bridge) -> None:
        data = bridge.client.get("/intelligence/accuracy?project=demo").json()
        assert data["counted"] == 0
        assert data["readOnly"] is True

    def test_accuracy_endpoint_reflects_records(self, bridge) -> None:
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
        data = bridge.client.get("/intelligence/accuracy?project=demo").json()
        assert data["counted"] == 3
        assert data["correct"] == 2
        assert data["accuracy"] == pytest.approx(2 / 3, abs=0.001)

    def test_accuracy_endpoint_project_isolation(self, bridge) -> None:
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
        assert bridge.client.get("/intelligence/accuracy?project=demo").json()["counted"] == 1
        assert bridge.client.get("/intelligence/accuracy?project=other").json()["counted"] == 0

    def test_accuracy_endpoint_filters(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
                "agent_id": "agent-1", "model_id": "router",
            },
        )
        bridge.approve(pending.json()["requestId"])
        filtered = bridge.client.get("/intelligence/accuracy?project=demo&agent_id=agent-1&model_id=router").json()
        assert filtered["counted"] == 1
        none = bridge.client.get("/intelligence/accuracy?project=demo&agent_id=nobody").json()
        assert none["counted"] == 0

    def test_accuracy_endpoint_calibration_present(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
                "confidence": 0.9,
            },
        )
        bridge.approve(pending.json()["requestId"])
        data = bridge.client.get("/intelligence/accuracy?project=demo").json()
        assert len(data["calibration"]) == 5
        assert data["calibration"][-1]["count"] == 1

    def test_accuracy_endpoint_kind_filter(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/evaluation",
            json={
                "project_id": "demo", "prediction_id": "pred-1",
                "evaluation_kind": "failure_prediction", "input_context": "",
                "prediction_result": "claim", "expected_outcome": "expected",
                "actual_outcome": "actual", "evaluation_result": "correct",
            },
        )
        bridge.approve(pending.json()["requestId"])
        data = bridge.client.get("/intelligence/accuracy?project=demo&kind=failure_prediction").json()
        assert data["counted"] == 1
        assert bridge.client.get("/intelligence/accuracy?project=demo&kind=prediction").json()["counted"] == 0
