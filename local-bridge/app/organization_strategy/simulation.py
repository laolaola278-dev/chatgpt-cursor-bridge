"""Organization Strategy Simulation Adapter (Phase 24).

Predicts risk / cost / impact / dependency / project disruption / migration
complexity for a candidate strategy using the same scenario-style, read-only
evaluation pattern as the Phase 14 Simulation Engine. It does not re-implement
the simulation engine and never executes anything: predictions are
deterministic projections derived from the strategy's real data.
"""

from __future__ import annotations

from .models import OrganizationStrategySimulation, StrategyType


class OrganizationSimulationAdapter:
    """Deterministic projection of a strategy into organization-level predictions."""

    _DISRUPTION = {
        StrategyType.REFACTOR: 0.45,
        StrategyType.MIGRATION: 0.85,
        StrategyType.STANDARDIZATION: 0.6,
        StrategyType.DEPRECATION: 0.5,
        StrategyType.TEST_IMPROVEMENT: 0.25,
        StrategyType.ARCHITECTURE_ALIGNMENT: 0.65,
        StrategyType.RISK_REDUCTION: 0.3,
    }

    def simulate(self, strategy) -> OrganizationStrategySimulation:
        strategy_type = strategy.strategy_type
        project_count = max(1, len(strategy.affected_projects))
        team_count = max(1, len(strategy.affected_teams) or 1)
        disruption = self._DISRUPTION[strategy_type]
        base_risk = min(1.0, 0.25 + 0.12 * len(strategy.risks))

        predictions = {
            "risk": round(min(1.0, base_risk + disruption * 0.3), 3),
            "cost": round(min(1.0, 0.2 + project_count * 0.15), 3),
            "impact": round(min(1.0, project_count * 0.22), 3),
            "dependency": round(min(1.0, team_count * 0.18), 3),
            "project_disruption": round(min(1.0, disruption + project_count * 0.05), 3),
            "migration_complexity": round(min(1.0, 0.15 + disruption * 0.6), 3),
            "project_count": project_count,
            "team_count": team_count,
            "estimated_effort": strategy.estimated_effort,
        }
        return OrganizationStrategySimulation(
            strategy_id=strategy.id,
            strategy_type=strategy_type.value,
            predictions=predictions,
        )
