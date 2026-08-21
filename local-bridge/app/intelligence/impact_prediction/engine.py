from __future__ import annotations

from pathlib import PurePosixPath
from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import ensure_project, ids, sanitize_text
from app.intelligence.confidence import derive_confidence
from app.intelligence.observation.models import Observation, ObservationType

from .models import ImpactPrediction, ImpactRiskLevel
from .storage import ImpactPredictionStore


class ChangeImpactPredictionEngine:
    """Predicts impact from supplied diff metadata and observations only."""

    def __init__(self, store: ImpactPredictionStore | None = None) -> None:
        self.store = store

    @staticmethod
    def _value(item: Any, *keys: str) -> Any:
        if isinstance(item, dict):
            for key in keys:
                if item.get(key) is not None:
                    return item[key]
        else:
            for key in keys:
                value = getattr(item, key, None)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if str(item).strip()]
        return []

    @staticmethod
    def _module(path: str) -> str:
        clean = sanitize_text(path, limit=400).replace("\\", "/").strip("/")
        parts = PurePosixPath(clean).parts
        if len(parts) <= 1:
            return parts[0] if parts else "unknown"
        return "/".join(parts[:-1]) or parts[0]

    @staticmethod
    def _is_failure(item: Observation) -> bool:
        text = f"{item.summary} {item.metadata}".lower()
        return item.type in {ObservationType.TEST_RESULT, ObservationType.BUILD_RESULT, ObservationType.ERROR_EVENT} and any(word in text for word in ("fail", "error", "regression", "broken", "timeout"))

    def predict(
        self,
        project: str,
        observations: Iterable[Observation] = (),
        *,
        changed_files: Iterable[str] = (),
        changed_symbols: Iterable[str] = (),
        dependencies: Iterable[Any] = (),
        historical_failures: Iterable[Observation] = (),
        graph: Any | None = None,
    ) -> ImpactPrediction:
        project = ensure_project(project)
        observation_items = [item for item in observations if item.project_id == project]
        history = [item for item in historical_failures if item.project_id == project]
        changed = ids(list(changed_files))
        symbols = ids(list(changed_symbols))
        affected_files = list(changed)
        evidence: list[str] = []
        affected_modules: list[str] = []
        affected_tests: list[str] = []
        dependency_paths: list[list[str]] = []

        for item in observation_items:
            if item.type in {ObservationType.CODE_CHANGE, ObservationType.GIT_DIFF}:
                file_values = self._list(item.metadata.get("files") or item.metadata.get("file") or item.metadata.get("path"))
                if not changed or set(file_values) & set(changed):
                    affected_files.extend(file_values)
                    evidence.append(item.id)
                symbol_values = self._list(item.metadata.get("symbols") or item.metadata.get("symbol"))
                symbols.extend(symbol_values)
            module = item.metadata.get("module")
            if module:
                affected_modules.append(str(module))
            tests = self._list(item.metadata.get("affected_tests") or item.metadata.get("tests") or item.metadata.get("test"))
            if tests:
                affected_tests.extend(tests)
            if self._is_failure(item):
                evidence.append(item.id)
                test_name = item.metadata.get("test") or item.metadata.get("test_name")
                if test_name:
                    affected_tests.append(str(test_name))

        for item in history:
            if self._is_failure(item):
                evidence.append(item.id)
                file_value = item.metadata.get("file") or item.metadata.get("module")
                if file_value:
                    affected_modules.append(str(file_value))

        for dependency in dependencies:
            if isinstance(dependency, dict):
                path = self._list(dependency.get("path") or dependency.get("dependency_path") or dependency.get("nodes"))
            else:
                path = self._list(dependency)
            if path:
                dependency_paths.append(path)
                affected_modules.extend(path)

        affected_files = ids(affected_files)
        symbols = ids(symbols)
        affected_modules = ids(affected_modules + [self._module(path) for path in affected_files])
        affected_tests = ids(affected_tests)
        evidence = ids(evidence)
        size = len(affected_files) + len(symbols) * 0.5 + len(dependency_paths) * 1.5
        failure_count = sum(1 for item in history if self._is_failure(item))
        score = min(1.0, 0.08 + min(0.45, size / 20.0) + min(0.35, failure_count * 0.12) + min(0.2, len(affected_tests) * 0.04))
        if score >= 0.82:
            level = ImpactRiskLevel.CRITICAL
        elif score >= 0.58:
            level = ImpactRiskLevel.HIGH
        elif score >= 0.3:
            level = ImpactRiskLevel.MEDIUM
        else:
            level = ImpactRiskLevel.LOW
        latest = max((item.timestamp for item in observation_items if item.id in evidence), default=None)
        breakdown = derive_confidence(
            evidence_count=len(evidence), latest_timestamp=latest,
            historical_similarity=min(1.0, failure_count / 3.0),
            pattern_consistency=0.8 if affected_tests or dependency_paths else 0.35,
        )
        reasons: list[str] = []
        if len(affected_files) > 1:
            reasons.append(f"{len(affected_files)} changed or observed files span the predicted impact")
        if len(affected_modules) > 1:
            reasons.append(f"{len(affected_modules)} modules are connected to the change evidence")
        if affected_tests:
            reasons.append(f"{len(affected_tests)} test target(s) are linked to the evidence")
        if failure_count:
            reasons.append(f"{failure_count} historical failure observation(s) match the affected area")
        if dependency_paths:
            reasons.append(f"{len(dependency_paths)} dependency path(s) increase the review surface")
        if not reasons:
            reasons.append("No historical failure or dependency evidence was supplied; confidence is limited")
        return ImpactPrediction(
            prediction_id=f"impact_{token_hex(8)}", project_id=project,
            affected_files=affected_files, affected_modules=affected_modules,
            affected_tests=affected_tests, risk_level=level, confidence=breakdown.score,
            evidence=evidence, why_risky=reasons, changed_files=changed,
            changed_symbols=symbols, dependency_paths=dependency_paths,
            confidence_sources=breakdown.as_dict(), confidence_explanation=breakdown.explanation(),
        )

    def analyze(self, project: str, *args: Any, **kwargs: Any) -> ImpactPrediction:
        return self.predict(project, *args, **kwargs)

    def predict_and_store(self, project: str, *args: Any, **kwargs: Any) -> ImpactPrediction:
        result = self.predict(project, *args, **kwargs)
        if self.store is not None:
            self.store.save(result)
        return result


ImpactPredictionEngine = ChangeImpactPredictionEngine
