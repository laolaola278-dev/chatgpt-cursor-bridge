"""Phase 27 · Intelligence Benchmark System tests."""

from __future__ import annotations

import pytest

from app.intelligence.validation import (
    BenchmarkPlanner,
    BenchmarkRunner,
    ValidationStore,
    builtin_datasets,
    find_builtin_dataset,
)
from app.security.validator import ValidationFailed


class TestBuiltinDatasets:
    def test_three_categories_exist(self) -> None:
        datasets = builtin_datasets("demo")
        assert {item.category for item in datasets} == {"engineering_prediction", "engineering_recommendation", "context_understanding"}

    def test_every_case_has_expected_answer(self) -> None:
        for dataset in builtin_datasets("demo"):
            assert dataset.cases
            for case in dataset.cases:
                assert case.expected

    def test_dataset_ids_are_stable(self) -> None:
        assert {item.dataset_id for item in builtin_datasets("demo")} == {"builtin_engineering_prediction", "builtin_engineering_recommendation", "builtin_context_understanding"}

    def test_datasets_are_deterministic_across_calls(self) -> None:
        first = [item.as_dict() for item in builtin_datasets("demo")]
        second = [item.as_dict() for item in builtin_datasets("demo")]
        assert first == second

    def test_find_builtin_dataset(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        assert dataset is not None
        assert len(dataset.cases) >= 8

    def test_find_unknown_dataset_returns_none(self) -> None:
        assert find_builtin_dataset("builtin_missing", "demo") is None

    def test_cases_include_expected_categories(self) -> None:
        prediction = find_builtin_dataset("builtin_engineering_prediction", "demo")
        categories = {case.category for case in prediction.cases}
        assert {"bug_prediction", "failure_prediction", "test_failure_prediction", "regression_prediction"} <= categories


class TestBenchmarkScoring:
    def test_exact_match_scores_one(self) -> None:
        assert BenchmarkPlanner().score_case("regression_risk", "regression_risk") == 1.0

    def test_unrelated_answer_scores_low(self) -> None:
        score = BenchmarkPlanner().score_case("banana", "regression_risk")
        assert score < 0.5

    def test_partial_overlap_gets_partial_credit(self) -> None:
        score = BenchmarkPlanner().score_case("use_repository", "use_repository_layer")
        assert 0.0 < score < 1.0

    def test_empty_input_scores_zero(self) -> None:
        assert BenchmarkPlanner().score_case("", "regression_risk") == 0.0

    def test_empty_expected_scores_zero(self) -> None:
        assert BenchmarkPlanner().score_case("x", "") == 0.0

    def test_case_insensitive_matching(self) -> None:
        assert BenchmarkPlanner().score_case("REGRESSION_RISK", "regression_risk") == 1.0

    def test_hyphen_underscore_tokens_equivalent(self) -> None:
        assert BenchmarkPlanner().score_case("regression-risk", "regression_risk") == 1.0


class TestBenchmarkRunner:
    def test_self_consistency_baseline_is_one(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        run = BenchmarkRunner().run(dataset, model_id="deterministic")
        assert run.score == 1.0
        assert run.accuracy == 1.0

    def test_predictions_are_scored(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        wrong = ["wrong"] * len(dataset.cases)
        run = BenchmarkRunner().run(dataset, model_id="bad-model", predictions=wrong)
        assert run.score < 0.5

    def test_partially_correct_predictions(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        cases = sorted(dataset.cases, key=lambda case: case.case_id)
        # One exact answer; the rest partially overlap ("failure" matches the
        # "test_failure"/"failure_risk" tokens) so score exceeds accuracy.
        predictions = [cases[0].expected if index == 0 else "failure" for index in range(len(cases))]
        run = BenchmarkRunner().run(dataset, model_id="partial-model", predictions=predictions)
        assert run.accuracy == pytest.approx(1 / len(cases))
        assert run.score > run.accuracy

    def test_run_is_deterministic(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        first = BenchmarkRunner().run(dataset, model_id="m")
        second = BenchmarkRunner().run(dataset, model_id="m")
        assert first.determinism_hash == second.determinism_hash
        assert first.score == second.score
        assert first.accuracy == second.accuracy
        assert [case.as_dict() for case in first.cases] == [case.as_dict() for case in second.cases]

    def test_determinism_hash_changes_with_answers(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        base = BenchmarkRunner().run(dataset, model_id="m")
        altered = BenchmarkRunner().run(dataset, model_id="m", predictions=["different"] * len(dataset.cases))
        assert base.determinism_hash != altered.determinism_hash

    def test_cases_are_ordered_for_reproducibility(self) -> None:
        dataset = find_builtin_dataset("builtin_context_understanding", "demo")
        run = BenchmarkRunner().run(dataset, model_id="m")
        case_ids = [result.case.case_id for result in run.cases]
        assert case_ids == sorted(case_ids)

    def test_benchmark_id_is_generated(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        run = BenchmarkRunner().run(dataset, model_id="m")
        assert run.benchmark_id.startswith("bench_")

    def test_model_id_is_recorded(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        run = BenchmarkRunner().run(dataset, model_id="router-v2")
        assert run.model_id == "router-v2"

    def test_run_is_project_scoped(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "alpha")
        assert dataset.project_id == "alpha"
        run = BenchmarkRunner().run(dataset, model_id="m")
        assert run.project_id == "alpha"

    def test_run_never_mutates_dataset(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        before = dataset.as_dict()
        BenchmarkRunner().run(dataset, model_id="m", predictions=["x"] * len(dataset.cases))
        assert dataset.as_dict() == before

    def test_scrubs_secrets_in_predictions(self) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        predictions = ["sk-1234567890abcdef"] * len(dataset.cases)
        run = BenchmarkRunner().run(dataset, model_id="m", predictions=predictions)
        assert all("sk-1234567890abcdef" not in result.predicted for result in run.cases)


class TestBenchmarkStorage:
    def test_save_roundtrip(self, tmp_path) -> None:
        db = ValidationStore(tmp_path / "i.db")
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        run = BenchmarkRunner().run(dataset, model_id="m")
        db.save_benchmark(run)
        loaded = db.get_benchmark(run.benchmark_id, "demo")
        assert loaded is not None
        assert loaded.benchmark_id == run.benchmark_id
        assert len(loaded.cases) == len(run.cases)
        assert loaded.score == run.score

    def test_get_is_project_scoped(self, tmp_path) -> None:
        db = ValidationStore(tmp_path / "i.db")
        run = BenchmarkRunner().run(find_builtin_dataset("builtin_engineering_prediction", "demo"), model_id="m")
        db.save_benchmark(run)
        assert db.get_benchmark(run.benchmark_id, "demo") is not None
        assert db.get_benchmark(run.benchmark_id, "other") is None

    def test_list_is_project_isolated(self, tmp_path) -> None:
        db = ValidationStore(tmp_path / "i.db")
        db.save_benchmark(BenchmarkRunner().run(find_builtin_dataset("builtin_engineering_prediction", "demo"), model_id="m"))
        db.save_benchmark(BenchmarkRunner().run(find_builtin_dataset("builtin_engineering_prediction", "alpha"), model_id="m"))
        assert len(db.benchmarks("demo")) == 1
        assert len(db.benchmarks("alpha")) == 1

    def test_roundtrip_preserves_case_results(self, tmp_path) -> None:
        db = ValidationStore(tmp_path / "i.db")
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        cases = sorted(dataset.cases, key=lambda case: case.case_id)
        predictions = [cases[0].expected] + ["wrong"] * (len(cases) - 1)
        run = BenchmarkRunner().run(dataset, model_id="m", predictions=predictions)
        db.save_benchmark(run)
        loaded = db.get_benchmark(run.benchmark_id, "demo")
        assert loaded.cases[0].correct is True
        assert loaded.cases[1].correct is False


class TestBenchmarkApi:
    def test_run_requires_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "router"},
        )
        assert pending.status_code == 202
        assert pending.json()["action"] == "intelligence_benchmark_run"
        assert bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"] == []
        response = bridge.approve(pending.json()["requestId"])
        assert response.status_code == 200
        benchmarks = bridge.client.get("/intelligence/benchmarks?project=demo").json()
        assert len(benchmarks["benchmarks"]) == 1

    def test_run_rejects_unknown_dataset(self, bridge) -> None:
        response = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_missing", "model_id": "router"},
        )
        assert response.status_code == 400

    def test_benchmarks_endpoint_read_only(self, bridge) -> None:
        response = bridge.client.get("/intelligence/benchmarks?project=demo")
        assert response.status_code == 200
        assert response.json()["readOnly"] is True
        assert len(response.json()["datasets"]) == 3

    def test_benchmark_detail_after_run(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_context_understanding", "model_id": "router"},
        )
        bridge.approve(pending.json()["requestId"])
        benchmark_id = bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"][0]["benchmarkId"]
        detail = bridge.client.get(f"/intelligence/benchmark/{benchmark_id}?project=demo")
        assert detail.status_code == 200
        assert detail.json()["datasetName"] == "builtin-context_understanding"

    def test_benchmark_detail_is_project_scoped(self, bridge) -> None:
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "router"},
        )
        bridge.approve(pending.json()["requestId"])
        benchmark_id = bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"][0]["benchmarkId"]
        assert bridge.client.get(f"/intelligence/benchmark/{benchmark_id}?project=other").status_code == 404

    def test_benchmark_results_are_reproducible_via_api(self, bridge) -> None:
        for _ in range(2):
            pending = bridge.client.post(
                "/intelligence/benchmark/run",
                json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "router"},
            )
            bridge.approve(pending.json()["requestId"])
        runs = bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"]
        assert runs[0]["score"] == runs[1]["score"]
        assert runs[0]["accuracy"] == runs[1]["accuracy"]

    def test_benchmark_run_custom_predictions(self, bridge) -> None:
        dataset = find_builtin_dataset("builtin_engineering_prediction", "demo")
        predictions = ["wrong"] * len(dataset.cases)
        pending = bridge.client.post(
            "/intelligence/benchmark/run",
            json={"project_id": "demo", "dataset_id": "builtin_engineering_prediction", "model_id": "bad", "predictions": predictions},
        )
        bridge.approve(pending.json()["requestId"])
        runs = bridge.client.get("/intelligence/benchmarks?project=demo").json()["benchmarks"]
        assert runs[0]["accuracy"] < 0.5

    def test_no_benchmark_execution_endpoint(self, bridge) -> None:
        assert bridge.client.get("/intelligence/benchmark/execute?project=demo").status_code == 404
