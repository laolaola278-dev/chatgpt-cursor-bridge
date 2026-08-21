"""Task 5 · Intelligence Benchmark System.

Deterministic, repeatable evaluation of intelligence claims. A benchmark run
scores predicted outcomes against expected outcomes with an explicit scoring
function; there is no randomness, so identical datasets and inputs always
produce identical scores (verifiable via ``determinism_hash``).

Benchmarks measure claims; they do not execute, patch, or modify anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import bounded_confidence, ensure_project, sanitize_text

from .models import BenchmarkCase, BenchmarkCaseResult, BenchmarkDataset, BenchmarkRun

BUILTIN_DATASETS: dict[str, list[BenchmarkCase]] = {
    "engineering_prediction": [
        BenchmarkCase("bp-1", "bug_prediction", "test suite reports an intermittent failure in parser after config change", "regression_risk"),
        BenchmarkCase("bp-2", "bug_prediction", "service memory usage grows 30% after the retry loop change", "failure_risk"),
        BenchmarkCase("bp-3", "failure_prediction", "cache invalidation removed from the read path", "failure_risk"),
        BenchmarkCase("bp-4", "test_failure_prediction", "shared test fixture updated while two tests depend on old ordering", "test_failure"),
        BenchmarkCase("bp-5", "regression_prediction", "migration renames a column still referenced by legacy queries", "regression_risk"),
        BenchmarkCase("bp-6", "failure_prediction", "dependency upgraded two minor versions across 40 call sites", "failure_risk"),
        BenchmarkCase("bp-7", "bug_prediction", "error handling swallows the original exception context", "failure_risk"),
        BenchmarkCase("bp-8", "test_failure_prediction", "flaky timeout test extended to cover new async paths", "test_failure"),
    ],
    "engineering_recommendation": [
        BenchmarkCase("br-1", "refactoring", "two modules duplicate the same retry logic", "extract_shared_helper"),
        BenchmarkCase("br-2", "testing", "new endpoint has no coverage for auth failures", "add_auth_failure_tests"),
        BenchmarkCase("br-3", "architecture", "service talks to the database directly instead of the repository layer", "use_repository_layer"),
        BenchmarkCase("br-4", "dependency", "pinned dependency has a known high-severity advisory", "upgrade_or_mitigate_dependency"),
        BenchmarkCase("br-5", "refactoring", "function takes nine positional parameters", "introduce_parameter_object"),
        BenchmarkCase("br-6", "testing", "error path is only covered by manual testing", "add_error_path_tests"),
        BenchmarkCase("br-7", "architecture", "frontend imports server-only module for constants", "move_shared_constants"),
        BenchmarkCase("br-8", "dependency", "two packages provide overlapping functionality", "consolidate_dependencies"),
    ],
    "context_understanding": [
        BenchmarkCase("bc-1", "project_understanding", "project language is Python with a FastAPI entrypoint", "python_fastapi"),
        BenchmarkCase("bc-2", "code_understanding", "module parser.py exposes parse() and tokenize()", "parser_module"),
        BenchmarkCase("bc-3", "dependency_understanding", "service depends on lib-x which depends on lib-y", "transitive_dependency"),
        BenchmarkCase("bc-4", "git_diff_understanding", "diff removes an import and adds a new module", "import_changed"),
        BenchmarkCase("bc-5", "project_understanding", "tests live in tests/ and use pytest", "pytest"),
        BenchmarkCase("bc-6", "dependency_understanding", "two services share the same cache library", "shared_dependency"),
        BenchmarkCase("bc-7", "git_diff_understanding", "diff only changes documentation comments", "docs_only_change"),
        BenchmarkCase("bc-8", "code_understanding", "the API layer delegates to a service layer", "layered_architecture"),
    ],
}


def builtin_datasets(project_id: str = "demo") -> list[BenchmarkDataset]:
    """Return the built-in deterministic benchmark datasets for a project."""
    project = ensure_project(project_id)
    return [
        BenchmarkDataset(
            dataset_id=f"builtin_{category}", name=f"builtin-{category}",
            project_id=project, category=category, cases=list(cases),
        )
        for category, cases in sorted(BUILTIN_DATASETS.items())
    ]


def find_builtin_dataset(dataset_id: str, project_id: str = "demo") -> BenchmarkDataset | None:
    for dataset in builtin_datasets(project_id):
        if dataset.dataset_id == dataset_id:
            return dataset
    return None


@dataclass(frozen=True)
class BenchmarkPlanner:
    """Deterministic case scoring used by the benchmark runner."""

    def score_case(self, predicted: str, expected: str) -> float:
        left = sanitize_text(predicted, limit=4000).strip().lower()
        right = sanitize_text(expected, limit=4000).strip().lower()
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        # Token overlap gives partial credit for related answers without
        # pretending exact equivalence.
        left_tokens = set(left.replace("-", "_").replace("/", "_").split("_"))
        right_tokens = set(right.replace("-", "_").replace("/", "_").split("_"))
        if not left_tokens or not right_tokens:
            return 0.0
        union = left_tokens | right_tokens
        return round(len(left_tokens & right_tokens) / len(union), 3)


class BenchmarkRunner:
    def __init__(self, planner: BenchmarkPlanner | None = None) -> None:
        self.planner = planner or BenchmarkPlanner()

    def run(
        self,
        dataset: BenchmarkDataset,
        *,
        model_id: str,
        predictions: Iterable[str] | None = None,
    ) -> BenchmarkRun:
        """Score a dataset deterministically.

        ``predictions`` optionally supplies the answers being benchmarked; when
        omitted every case is scored against its own expected answer (a
        self-consistency baseline of 1.0), which keeps the run repeatable for
        verification without fabricating a production accuracy claim.
        """
        answers = list(predictions or [])
        case_results: list[BenchmarkCaseResult] = []
        ordered_cases = sorted(dataset.cases, key=lambda case: case.case_id)
        for index, case in enumerate(ordered_cases):
            predicted = answers[index] if index < len(answers) else case.expected
            score = self.planner.score_case(predicted, case.expected)
            case_results.append(
                BenchmarkCaseResult(
                    case=case, predicted=sanitize_text(predicted, limit=4000),
                    correct=score >= 1.0, score=score,
                )
            )
        total = sum(result.score for result in case_results)
        count = len(case_results)
        raw_score = total / count if count else 0.0
        accuracy = sum(1 for result in case_results if result.correct) / count if count else 0.0
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    (result.case.case_id, result.predicted, result.score)
                    for result in case_results
                ],
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        # Scores are plain proportions, not confidence claims; the model clamps
        # them to [0.0, 1.0] without the confidence ceiling.
        return BenchmarkRun(
            benchmark_id=f"bench_{token_hex(8)}",
            dataset_id=dataset.dataset_id,
            dataset_name=dataset.name,
            project_id=dataset.project_id,
            category=dataset.category,
            model_id=sanitize_text(model_id, limit=200),
            score=raw_score,
            accuracy=accuracy,
            determinism_hash=fingerprint,
            cases=case_results,
        )


IntelligenceBenchmark = BenchmarkRunner
