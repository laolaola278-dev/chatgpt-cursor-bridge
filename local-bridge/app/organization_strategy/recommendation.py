"""Organization Recommendation Engine (Phase 24).

Aggregates real signals - organization health warnings, risk propagation
reports, cross-project impacts, technical debt, architecture drift and
strategy simulations - into strategic recommendations. Recommendations are
evidence-backed suggestions only; they never convert into execution and never
write memory.
"""

from __future__ import annotations

from typing import Any

from .models import StrategicRecommendation


class OrganizationRecommendationEngine:
    def build(
        self,
        *,
        healths: list[dict[str, Any]] | None = None,
        risks: list[dict[str, Any]] | None = None,
        impacts: list[dict[str, Any]] | None = None,
        debts: dict[str, list[dict[str, Any]]] | None = None,
        drifts: dict[str, list[dict[str, Any]]] | None = None,
        simulations: list[dict[str, Any]] | None = None,
        teams_by_project: dict[str, str] | None = None,
    ) -> list[StrategicRecommendation]:
        healths = healths or []
        risks = risks or []
        impacts = impacts or []
        debts = debts or {}
        drifts = drifts or {}
        simulations = simulations or []
        teams_by_project = teams_by_project or {}

        recommendations: list[StrategicRecommendation] = []

        def teams(projects: list[str]) -> list[str]:
            return sorted({teams_by_project.get(project) for project in projects if teams_by_project.get(project)})

        # Health warnings -> recommendations.
        for health in healths:
            score = int(health.get("healthScore", 100))
            project = str(health.get("project", "unknown"))
            if score < 70:
                recommendations.append(StrategicRecommendation(
                    problem=f"{project} engineering health is {score}/100",
                    evidence=[f"healthScore={score} riskLevel={health.get('riskLevel', 'low')}"],
                    recommendation="Schedule a focused verification and test-stability improvement window for the project",
                    expected_benefit="Restore a stable execution pipeline and lower change risk",
                    risk="low",
                    confidence=0.7 if score < 60 else 0.55,
                    affected_projects=[project],
                    affected_teams=teams([project]),
                    alternatives=["Keep current posture and monitor", "Increase approval strictness temporarily"],
                ))

        # Risk propagation -> recommendations.
        for risk in risks:
            if str(risk.get("impact", "low")).lower() in ("high", "medium"):
                recommendations.append(StrategicRecommendation(
                    problem=f"Risk originating at {risk.get('source')} propagates to {len(risk.get('affected_nodes', []))} node(s)",
                    evidence=[str(item.get("path", "")) for item in risk.get("propagation_path", [])[:3] if item.get("path")],
                    recommendation="Review the propagation path before scheduling any cross-project change",
                    expected_benefit="Avoid cascading failures through shared services and repositories",
                    risk=str(risk.get("impact", "low")),
                    confidence=float(risk.get("confidence", 0.5)),
                    affected_projects=risk.get("affected_projects", []),
                    affected_teams=risk.get("affected_teams", []),
                    alternatives=["Isolate the source service", "Freeze dependent change windows"],
                ))

        # Cross-project impact -> recommendations.
        for impact in impacts:
            if int(impact.get("impact_score", 0)) >= 50:
                recommendations.append(StrategicRecommendation(
                    problem=f"Change at {impact.get('source_node')} affects {len(impact.get('affected_projects', []))} project(s)",
                    evidence=[f"impactScore={impact.get('impact_score')} riskLevel={impact.get('risk_level')}"],
                    recommendation="Prepare per-project implementation plans before any execution window",
                    expected_benefit="Contain the blast radius and sequence projects by dependency order",
                    risk=str(impact.get("risk_level", "low")),
                    confidence=float(impact.get("confidence", 0.5)),
                    affected_projects=impact.get("affected_projects", []),
                    affected_teams=impact.get("affected_teams", []),
                    alternatives=["Defer non-critical affected projects", "Split the change into smaller phases"],
                ))

        # Debt -> recommendations.
        for project, items in sorted(debts.items()):
            open_items = [item for item in items if str(item.get("status", "OPEN")).upper() == "OPEN"]
            if len(open_items) >= 3:
                recommendations.append(StrategicRecommendation(
                    problem=f"{project} carries {len(open_items)} open debt item(s)",
                    evidence=[f"{item.get('category', 'unknown')}:{item.get('severity', 'low')}" for item in open_items[:4]],
                    recommendation="Plan a dedicated refactor window for the most expensive debt items",
                    expected_benefit="Lower long-term maintenance cost and change risk",
                    risk="medium",
                    confidence=0.65,
                    affected_projects=[project],
                    affected_teams=teams([project]),
                    alternatives=["Keep a debt register only", "Prioritize by estimated cost"],
                ))

        # Drift -> recommendations.
        for project, reports in sorted(drifts.items()):
            issues = [issue for report in reports for issue in (report.get("issues") or [])]
            if len(issues) >= 2:
                recommendations.append(StrategicRecommendation(
                    problem=f"{project} has {len(issues)} architecture drift issue(s)",
                    evidence=[str(issue.get("type", "unknown")) for issue in issues[:4]],
                    recommendation="Align the implementation with recorded architecture decisions before new features",
                    expected_benefit="Prevent divergence that compounds future migration cost",
                    risk="medium",
                    confidence=0.6,
                    affected_projects=[project],
                    affected_teams=teams([project]),
                    alternatives=["Document drift as intentional", "Gate new proposals on drift"],
                ))

        # Simulations -> recommendations.
        for simulation in simulations:
            predictions = simulation.get("predictions", {})
            if float(predictions.get("risk", 0)) >= 0.7:
                recommendations.append(StrategicRecommendation(
                    problem=f"Strategy {simulation.get('strategy_id')} simulates high risk ({predictions.get('risk')})",
                    evidence=[f"disruption={predictions.get('project_disruption')} complexity={predictions.get('migration_complexity')}"],
                    recommendation="Choose a lower-disruption alternative or phase the strategy per project",
                    expected_benefit="Reduce organizational disruption while still moving toward the goal",
                    risk="high",
                    confidence=float(predictions.get("risk", 0.7)),
                    alternatives=["Status quo", "Phased rollout"],
                ))

        return recommendations
