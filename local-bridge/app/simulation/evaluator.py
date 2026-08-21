from __future__ import annotations

from .models import Evaluation, Scenario


class ScenarioEvaluator:
    def evaluate(self, scenario: Scenario, *, test_coverage: int | None = None, rollback_available: bool = True, architecture_improvement: int = 70, maintenance_cost: int = 30) -> Evaluation:
        scope = max(0, min(35, 35 - scenario.impact_score // 3))
        risk = max(0, min(25, 25 - scenario.risk_score // 4))
        tests = 10 if test_coverage is None else max(0, min(15, test_coverage // 7))
        rollback = 10 if rollback_available else 0
        architecture = max(0, min(10, architecture_improvement // 10))
        maintenance = max(0, min(5, 5 - maintenance_cost // 20))
        score = max(0, min(100, scope + risk + tests + rollback + architecture + maintenance))
        level = "high" if scenario.risk_score >= 60 else "medium" if scenario.risk_score >= 30 else "low"
        advantages = ["lower coupling" if scenario.scenario_type in {"refactor", "rewrite"} else "small reviewable change", "bounded workflow impact"]
        disadvantages = ["large change" if len(scenario.affected_files) > 10 else "limited architectural improvement"]
        if not scenario.affected_tests: disadvantages.append("affected tests are not indexed")
        return Evaluation(scenario.id, score, level, advantages, disadvantages, {"changeScope": scope, "risk": risk, "testCoverage": tests, "rollback": rollback, "architectureImprovement": architecture, "maintenanceCost": maintenance})
