from __future__ import annotations

from app.simulation.models import Evaluation, Scenario, Simulation


class EngineeringPlanGenerator:
    def render(self, simulation: Simulation, scenario: Scenario, evaluation: Evaluation | None = None) -> str:
        risk = evaluation.risk if evaluation else scenario.risk
        tests = scenario.affected_tests or ["focused regression tests for affected behavior"]
        lines = ["# Engineering Plan", "", "## Problem", simulation.problem, "", "## Current State", f"Simulation predicts {scenario.impact_score}/100 impact across {len(scenario.affected_files)} file(s).", "", "## Selected Scenario", f"{scenario.name} ({scenario.scenario_type})", "", "## Files", *[f"- `{path}`" for path in scenario.affected_files], "", "## Implementation Steps", *[f"{index}. {change}" for index, change in enumerate(scenario.changes, 1)], "", "## Testing Plan", *[f"- {test}" for test in tests], "", "## Rollback Plan", "- Capture existing state before any approved implementation action.", "- Restore the stage through the existing rollback approval path if validation fails.", "", "## Risks", f"- Predicted risk: {risk}", f"- Required workflow stages: {', '.join(scenario.workflow_stages)}", "", "This plan is metadata only; it is not an execution command."]
        return "\n".join(lines) + "\n"
