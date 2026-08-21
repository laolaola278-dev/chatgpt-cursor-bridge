from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.code_intelligence.index import CodeIndex

from .models import Scenario


class ImpactSimulator:
    """Predict metadata impact without opening or modifying source files."""

    def __init__(self, index: CodeIndex) -> None:
        self.index = index

    def simulate(self, scenario_id: str, simulation_id: str, project: str, *, name: str, scenario_type: str, changes: list[str], affected_files: list[str]) -> Scenario:
        edges = self.index.dependencies(project)
        reverse: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            reverse[edge["target"]].add(edge["source"])
        dependents: set[str] = set()
        frontier = set(affected_files)
        for _ in range(2):
            next_frontier = set().union(*(reverse.get(path, set()) for path in frontier)) if frontier else set()
            dependents.update(next_frontier)
            frontier = next_frontier
        files = list(dict.fromkeys([*affected_files, *sorted(dependents)]))
        tests = [path for path in self.index.files(project, limit=500) if "test" in path["path"].lower() and any(part in path["path"] for part in files)]
        test_paths = [item["path"] for item in tests]
        impact = min(100, len(files) * 8 + len(dependents) * 4)
        risk_score = min(100, impact + (20 if scenario_type in {"rewrite", "migration"} else 8 if scenario_type == "refactor" else 0))
        risk = "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low"
        stages = ["IMPLEMENTATION", "TESTING", "REVIEW"]
        memories = ["architecture.md update"] if scenario_type in {"refactor", "rewrite"} else []
        if scenario_type in {"refactor", "rewrite", "migration"}: memories.append("ADR required")
        return Scenario(scenario_id, simulation_id, name, scenario_type, changes, files, sorted(dependents), test_paths, stages, memories, risk_score, impact, risk)
