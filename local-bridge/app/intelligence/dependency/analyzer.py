from __future__ import annotations

from collections import defaultdict
from secrets import token_hex
from typing import Any, Iterable

from app.intelligence.common import ensure_project, ids, sanitize_text, tokens
from app.intelligence.confidence import derive_confidence
from app.intelligence.observation.models import Observation, ObservationType

from .models import DependencyRisk, DependencyRiskLevel
from .storage import DependencyRiskStore


class DependencyRiskAnalyzer:
    """Analyze dependency observations; never upgrades, downgrades, or writes them."""

    def __init__(self, store: DependencyRiskStore | None = None) -> None:
        self.store = store

    @staticmethod
    def _field(item: Observation, *names: str) -> Any:
        for name in names:
            if item.metadata.get(name) is not None:
                return item.metadata[name]
        return None

    @staticmethod
    def _components(item: Observation) -> list[str]:
        value = item.metadata.get("affected_components") or item.metadata.get("components") or item.metadata.get("module") or item.metadata.get("file")
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(part) for part in value]
        return []

    @staticmethod
    def _dependency(item: Observation) -> str:
        value = item.metadata.get("dependency") or item.metadata.get("package") or item.metadata.get("name")
        return sanitize_text(value or item.source, limit=240).strip()

    @staticmethod
    def _severity(score: float) -> DependencyRiskLevel:
        if score >= 0.82:
            return DependencyRiskLevel.CRITICAL
        if score >= 0.58:
            return DependencyRiskLevel.HIGH
        if score >= 0.3:
            return DependencyRiskLevel.MEDIUM
        return DependencyRiskLevel.LOW

    def analyze(
        self,
        project: str,
        observations: Iterable[Observation],
        *,
        historical_failures: Iterable[Observation] = (),
    ) -> list[DependencyRisk]:
        project = ensure_project(project)
        items = [item for item in observations if item.project_id == project and item.type is ObservationType.DEPENDENCY_CHANGE]
        failures = [item for item in historical_failures if item.project_id == project and item.type in {ObservationType.TEST_RESULT, ObservationType.BUILD_RESULT, ObservationType.ERROR_EVENT}]
        grouped: dict[str, list[Observation]] = defaultdict(list)
        for item in items:
            grouped[self._dependency(item)].append(item)
        results: list[DependencyRisk] = []
        for dependency, changes in grouped.items():
            latest = sorted(changes, key=lambda item: item.timestamp)[-1]
            text = " ".join(f"{item.summary} {item.metadata}".lower() for item in changes)
            change_type = str(self._field(latest, "change_type", "changeType") or ("removed" if "remov" in text else "added" if "new depend" in text or "added" in text else "updated"))
            old_version = str(self._field(latest, "old_version", "oldVersion") or "")
            new_version = str(self._field(latest, "new_version", "newVersion") or "")
            transitive = bool(self._field(latest, "transitive", "is_transitive") or False)
            components = ids([component for item in changes for component in self._components(item)])
            matching_failures: list[Observation] = []
            dep_tokens = tokens(dependency, *[item.summary for item in changes])
            for failure in failures:
                if dep_tokens & tokens(failure.summary, failure.metadata.get("dependency"), failure.metadata.get("package"), failure.metadata.get("module")):
                    matching_failures.append(failure)
            concentration_raw = self._field(latest, "concentration", "dependency_concentration")
            coupling_raw = self._field(latest, "coupling", "dependency_coupling")
            concentration = float(concentration_raw) if isinstance(concentration_raw, (int, float)) else None
            coupling = float(coupling_raw) if isinstance(coupling_raw, (int, float)) else None
            score = 0.12 + min(0.35, len(changes) * 0.1) + min(0.3, len(matching_failures) * 0.12)
            if any(word in text for word in ("major", "breaking", "removed", "vulnerab", "critical")):
                score += 0.25
            if transitive:
                score += 0.08
            if concentration is not None:
                score += max(0.0, min(0.15, concentration * 0.15))
            if coupling is not None:
                score += max(0.0, min(0.15, coupling * 0.15))
            score = min(1.0, score)
            breakdown = derive_confidence(
                evidence_count=len(changes) + len(matching_failures),
                latest_timestamp=latest.timestamp,
                historical_similarity=min(1.0, len(matching_failures) / 3.0),
                outcome_validation=min(1.0, len(matching_failures) / 3.0),
                pattern_consistency=0.8 if len(changes) > 1 else 0.45,
            )
            reasons = [f"{change_type} dependency change observed for {dependency}"]
            if old_version or new_version:
                reasons.append(f"version evidence {old_version or 'unknown'} → {new_version or 'unknown'}")
            if matching_failures:
                reasons.append(f"{len(matching_failures)} historical failure observation(s) share dependency evidence")
            if transitive:
                reasons.append("dependency is marked transitive, increasing indirect impact uncertainty")
            results.append(DependencyRisk(
                risk_id=f"dep_risk_{token_hex(8)}", project_id=project, dependency=dependency,
                risk=self._severity(score), reason="; ".join(reasons),
                historical_evidence=[item.id for item in matching_failures],
                affected_components=components, confidence=breakdown.score,
                change_type=change_type, old_version=old_version, new_version=new_version,
                transitive=transitive, concentration=concentration, coupling=coupling,
            ))
        return results

    def analyze_and_store(self, project: str, observations: Iterable[Observation], **kwargs: Any) -> list[DependencyRisk]:
        results = self.analyze(project, observations, **kwargs)
        if self.store is not None:
            self.store.save_many(results)
        return results


DependencyRiskEngine = DependencyRiskAnalyzer
