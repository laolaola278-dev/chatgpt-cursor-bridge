from __future__ import annotations

from secrets import token_hex

from app.code_intelligence.index import CodeIndex
from app.intelligence.models import Proposal

from .models import Scenario
from .scenario import ImpactSimulator


class ScenarioPlanner:
    def __init__(self, index: CodeIndex) -> None:
        self.index = index
        self.simulator = ImpactSimulator(index)

    def plan(self, *, simulation_id: str, project: str, problem: str, proposal: Proposal | None = None) -> list[Scenario]:
        target = (proposal.target.get("file") if proposal else None) or "project"
        stats = self.index.stats(project)
        base = [target] if target != "project" else [item["path"] for item in self.index.files(project, limit=1)]
        breadth = max(1, min(4, stats["files"] // 5 or 1))
        definitions = [("Minimal Patch", "patch", [f"apply a focused change to {target}"], base), ("Module Extraction", "refactor", ["create a focused service boundary", "move the highest-risk responsibility"], list(dict.fromkeys(base + [f"{target.rsplit('/', 1)[0]}/service.py" if "/" in target else "service.py"]))), ("Architecture Rewrite", "rewrite", ["redesign the affected boundary", "migrate dependent modules"], base * max(1, breadth))]
        return [self.simulator.simulate(f"scenario_{token_hex(6)}", simulation_id, project, name=name, scenario_type=kind, changes=changes, affected_files=list(dict.fromkeys(files))) for name, kind, changes, files in definitions]
