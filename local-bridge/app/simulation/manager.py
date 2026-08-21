from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_hex

from app.code_intelligence.index import CodeIndex
from app.intelligence.models import Proposal
from app.planning.generator import EngineeringPlanGenerator
from app.security.validator import ValidationFailed

from .evaluator import ScenarioEvaluator
from .models import Plan, Simulation, SimulationStatus
from .planner import ScenarioPlanner
from .storage import SimulationStorage


class SimulationManager:
    def __init__(self, storage: SimulationStorage, index: CodeIndex) -> None:
        self.storage = storage
        self.index = index
        self.planner = ScenarioPlanner(index)
        self.evaluator = ScenarioEvaluator()
        self.plan_generator = EngineeringPlanGenerator()

    def create(self, *, project: str, problem: str) -> Simulation:
        cleaned = problem.strip()
        if not cleaned:
            raise ValidationFailed("Simulation problem must not be empty")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        item = Simulation(f"sim_{token_hex(8)}", project, cleaned, created_at=now, updated_at=now, history=[{"status": SimulationStatus.DRAFT.value, "at": now}])
        self.storage.save_simulation(item)
        return item

    def analyze(self, simulation_id: str, *, proposal: Proposal | None = None, test_coverage: int | None = None) -> dict[str, object]:
        simulation = self.storage.get_simulation(simulation_id)
        if simulation is None:
            raise ValidationFailed(f"Simulation '{simulation_id}' was not found")
        scenarios = self.planner.plan(simulation_id=simulation.id, project=simulation.project, problem=simulation.problem, proposal=proposal)
        self.storage.save_scenarios(scenarios)
        evaluations = []
        for scenario in scenarios:
            evaluation = self.evaluator.evaluate(scenario, test_coverage=test_coverage)
            self.storage.save_evaluation(evaluation)
            evaluations.append(evaluation)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        simulation.status = SimulationStatus.COMPLETED
        simulation.updated_at = now
        simulation.history.append({"status": simulation.status.value, "at": now})
        self.storage.save_simulation(simulation)
        return {"simulation": simulation.as_dict(), "scenarios": [item.as_dict() for item in scenarios], "evaluations": [item.as_dict() for item in evaluations], "readOnlyAnalysis": True}

    def evaluation(self, simulation_id: str) -> list[dict[str, object]]:
        output = []
        for scenario in self.storage.list_scenarios(simulation_id):
            evaluation = self.storage.get_evaluation(scenario.id)
            if evaluation:
                output.append(evaluation.as_dict())
        return output

    def plan(self, simulation_id: str, scenario_id: str) -> Plan:
        simulation = self.storage.get_simulation(simulation_id)
        scenario = self.storage.get_scenario(scenario_id)
        if simulation is None or scenario is None or scenario.simulation_id != simulation_id:
            raise ValidationFailed("Scenario does not belong to simulation")
        evaluation = self.storage.get_evaluation(scenario_id)
        content = self.plan_generator.render(simulation, scenario, evaluation)
        plan = Plan(f"plan_{token_hex(8)}", simulation_id, scenario_id, content, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.storage.save_plan(plan)
        return plan
