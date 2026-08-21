"""Engineering Strategy Generator and Evaluation (Phase 24).

Generates candidate organization strategies deterministically from real
persisted signals (governance debt/drift/health, org failure patterns,
incidents, org graph), then compares candidates on impact / risk / cost /
complexity / maintainability / migration difficulty / confidence. Strategies
are proposals only: the evaluator can mark a recommended strategy, but the
final selection always requires a human decision.
"""

from __future__ import annotations

from typing import Any

from .models import EngineeringStrategy, StrategyEvaluation, StrategyType

_TYPE_MIGRATION_COMPLEXITY = {
    StrategyType.REFACTOR: 0.4,
    StrategyType.MIGRATION: 0.8,
    StrategyType.STANDARDIZATION: 0.55,
    StrategyType.DEPRECATION: 0.5,
    StrategyType.TEST_IMPROVEMENT: 0.3,
    StrategyType.ARCHITECTURE_ALIGNMENT: 0.65,
    StrategyType.RISK_REDUCTION: 0.35,
}

_TYPE_MAINTAINABILITY = {
    StrategyType.REFACTOR: 0.8,
    StrategyType.MIGRATION: 0.6,
    StrategyType.STANDARDIZATION: 0.75,
    StrategyType.DEPRECATION: 0.7,
    StrategyType.TEST_IMPROVEMENT: 0.65,
    StrategyType.ARCHITECTURE_ALIGNMENT: 0.85,
    StrategyType.RISK_REDUCTION: 0.7,
}


class OrganizationStrategyGenerator:
    """Deterministic rule-based candidate generation from real telemetry."""

    def generate(
        self,
        *,
        healths: list[dict[str, Any]] | None = None,
        debts: dict[str, list[dict[str, Any]]] | None = None,
        drifts: dict[str, list[dict[str, Any]]] | None = None,
        failure_patterns: list[dict[str, Any]] | None = None,
        incidents: list[dict[str, Any]] | None = None,
        teams_by_project: dict[str, str] | None = None,
    ) -> list[EngineeringStrategy]:
        healths = healths or []
        debts = debts or {}
        drifts = drifts or {}
        failure_patterns = failure_patterns or []
        incidents = incidents or []
        teams_by_project = teams_by_project or {}

        strategies: list[EngineeringStrategy] = []

        def teams(projects: list[str]) -> list[str]:
            return sorted({teams_by_project.get(project) for project in projects if teams_by_project.get(project)})

        # 1. REFACTOR — technical debt accumulation.
        for project, items in sorted(debts.items()):
            open_items = [item for item in items if str(item.get("status", "OPEN")).upper() == "OPEN"]
            if len(open_items) >= 2:
                total_cost = sum(int(item.get("estimatedCost", item.get("estimated_cost", 0)) or 0) for item in open_items)
                strategies.append(EngineeringStrategy(
                    strategy_type=StrategyType.REFACTOR,
                    title=f"Reduce technical debt in {project}",
                    problem=f"{project} accumulated {len(open_items)} open debt item(s)",
                    affected_projects=[project],
                    affected_teams=teams([project]),
                    benefits=["Lower change risk and maintenance cost", "Improve long-term engineering health"],
                    risks=["Refactor churn may destabilize active workstreams", "Requires focused verification windows"],
                    estimated_effort=self._effort(len(open_items), total_cost),
                    confidence=self._confidence(len(open_items), extra=total_cost > 20),
                    priority="high" if total_cost >= 40 else "medium",
                    evidence=[f"{project}: {len(open_items)} open debt item(s), est {total_cost}h"],
                ))

        # 2. ARCHITECTURE_ALIGNMENT — architecture drift.
        for project, reports in sorted(drifts.items()):
            issues = [issue for report in reports for issue in (report.get("issues") or [])]
            if len(issues) >= 2:
                kinds = sorted({str(issue.get("type", "unknown")) for issue in issues})
                strategies.append(EngineeringStrategy(
                    strategy_type=StrategyType.ARCHITECTURE_ALIGNMENT,
                    title=f"Align {project} with its recorded architecture",
                    problem=f"{project} shows architecture drift ({', '.join(kinds[:3])})",
                    affected_projects=[project],
                    affected_teams=teams([project]),
                    benefits=["Reconcile implementation with approved design decisions", "Reduce future unrecorded dependencies"],
                    risks=["Alignment work may touch multiple modules", "Requires design review before any change"],
                    estimated_effort=self._effort(len(issues), 0),
                    confidence=self._confidence(len(issues)),
                    priority="high" if any(str(issue.get("severity", "")) == "high" for issue in issues) else "medium",
                    evidence=[f"{project}: {len(issues)} drift issue(s): {', '.join(kinds[:3])}"],
                ))

        # 3. DEPRECATION — deprecated component usage.
        deprecated_projects = [
            project for project, reports in sorted(drifts.items())
            if any(
                str(issue.get("type", "")) == "deprecated_component_usage"
                for report in reports for issue in (report.get("issues") or [])
            )
        ]
        if deprecated_projects:
            strategies.append(EngineeringStrategy(
                strategy_type=StrategyType.DEPRECATION,
                title="Deprecate legacy components still in use",
                problem=f"Deprecated components are still referenced in: {', '.join(deprecated_projects)}",
                affected_projects=deprecated_projects,
                affected_teams=teams(deprecated_projects),
                benefits=["Remove obsolete code paths and their maintenance cost", "Shrink the attack/support surface"],
                risks=["Consumers may depend on undocumented behavior", "Migration must be approved per project"],
                estimated_effort=self._effort(len(deprecated_projects), 0),
                confidence=self._confidence(len(deprecated_projects)),
                priority="medium",
                evidence=[f"{project}: deprecated_component_usage drift" for project in deprecated_projects],
            ))

        # 4. STANDARDIZATION — repeated failure category across projects.
        by_category: dict[str, list[dict[str, Any]]] = {}
        for pattern in failure_patterns:
            by_category.setdefault(str(pattern.get("category", "unknown")), []).append(pattern)
        for category, patterns in sorted(by_category.items()):
            projects = sorted({str(pattern.get("project", "")) for pattern in patterns})
            if len(projects) >= 2:
                strategies.append(EngineeringStrategy(
                    strategy_type=StrategyType.STANDARDIZATION,
                    title=f"Standardize {category} handling across projects",
                    problem=f"'{category}' failure patterns repeat across {len(projects)} project(s)",
                    affected_projects=projects,
                    affected_teams=teams(projects),
                    benefits=["One shared approach prevents the same failure recurring", "Cross-project lessons become reusable"],
                    risks=["Standardization changes touch every affected project", "Needs per-project implementation plans"],
                    estimated_effort=self._effort(len(projects), 0),
                    confidence=self._confidence(len(patterns)),
                    priority="high" if any(str(p.get("severity", "")) == "high" for p in patterns) else "medium",
                    evidence=[f"{p.get('project')}: {category} x{p.get('occurrences', 1)}" for p in patterns[:4]],
                ))

        # 5. MIGRATION — cache/migration-related failures across projects.
        migration_projects = sorted({
            str(pattern.get("project", "")) for pattern in failure_patterns
            if "cache" in str(pattern.get("signature", "")).lower() or "migration" in str(pattern.get("signature", "")).lower()
        })
        if len(migration_projects) >= 2:
            strategies.append(EngineeringStrategy(
                strategy_type=StrategyType.MIGRATION,
                title="Consolidate cache technology across projects",
                problem=f"Cache-related failures observed in: {', '.join(migration_projects)}",
                affected_projects=migration_projects,
                affected_teams=teams(migration_projects),
                benefits=["One invalidation strategy removes cross-project cache bugs", "Shared operational knowledge"],
                risks=["Migration is the highest-disruption candidate", "Requires staged per-project rollout"],
                estimated_effort=self._effort(len(migration_projects), 30),
                confidence=self._confidence(len(migration_projects), extra=True),
                priority="high",
                evidence=[f"{pattern.get('project')}: {pattern.get('signature')}" for pattern in failure_patterns if "cache" in str(pattern.get("signature", "")).lower()][:4],
                alternatives=["Keep current cache per project (status quo)", "Standardize cache invalidation patterns without migration"],
            ))

        # 6. TEST_IMPROVEMENT — low or declining health.
        for health in healths:
            score = int(health.get("healthScore", 100))
            project = str(health.get("project", "unknown"))
            if score < 70:
                strategies.append(EngineeringStrategy(
                    strategy_type=StrategyType.TEST_IMPROVEMENT,
                    title=f"Improve test stability for {project}",
                    problem=f"{project} health is {score}/100 ({health.get('riskLevel', 'low')})",
                    affected_projects=[project],
                    affected_teams=teams([project]),
                    benefits=["Stable verification pipeline for future execution windows", "Earlier failure detection"],
                    risks=["Test-only changes still need approval-gated execution"],
                    estimated_effort=self._effort(1, 0),
                    confidence=self._confidence(1, extra=score < 60),
                    priority="high" if score < 60 else "medium",
                    evidence=[f"{project}: healthScore={score} riskLevel={health.get('riskLevel', 'low')}"],
                ))

        # 7. RISK_REDUCTION — open high-severity incidents.
        high_incidents = [incident for incident in incidents if str(incident.get("severity", "")).lower() == "high" and str(incident.get("status", "OPEN")).upper() == "OPEN"]
        if high_incidents:
            incident_projects = sorted({str(incident.get("project", "unknown")) for incident in high_incidents})
            strategies.append(EngineeringStrategy(
                strategy_type=StrategyType.RISK_REDUCTION,
                title="Reduce open high-severity incident risk",
                problem=f"{len(high_incidents)} open high-severity incident(s) across {', '.join(incident_projects)}",
                affected_projects=incident_projects,
                affected_teams=teams(incident_projects),
                benefits=["Lower organizational risk posture", "Unblock cross-project work"],
                risks=["Incident investigation must precede any remediation"],
                estimated_effort=self._effort(len(high_incidents), 0),
                confidence=self._confidence(len(high_incidents), extra=True),
                priority="high",
                evidence=[f"{incident.get('project')}: {incident.get('title')} (high)" for incident in high_incidents[:4]],
            ))

        return strategies

    @staticmethod
    def _effort(count: int, cost: int) -> str:
        base = max(1, count)
        weeks = max(2, base * 2 + cost // 20)
        return f"{weeks}-{weeks + 3} person-weeks"

    @staticmethod
    def _confidence(evidence_count: int, *, extra: bool = False) -> float:
        return min(0.95, 0.45 + 0.12 * evidence_count + (0.1 if extra else 0))


class OrganizationStrategyEvaluator:
    """Compares candidate strategies without auto-selecting the final one."""

    WEIGHTS = {
        "impact": 0.2,
        "risk": 0.2,
        "cost": 0.15,
        "complexity": 0.15,
        "maintainability": 0.1,
        "migration_difficulty": 0.1,
        "confidence": 0.1,
    }

    def evaluate(self, strategies: list[EngineeringStrategy]) -> list[StrategyEvaluation]:
        evaluations: list[StrategyEvaluation] = []
        for strategy in strategies:
            criteria = self._criteria(strategy)
            composite = sum(criteria[key] * self.WEIGHTS[key] for key in self.WEIGHTS)
            evaluations.append(StrategyEvaluation(
                strategy_id=strategy.id, criteria=criteria, composite_score=composite,
            ))
        if evaluations:
            best = max(evaluations, key=lambda item: item.composite_score)
            best.recommended = True
        return evaluations

    def _criteria(self, strategy: EngineeringStrategy) -> dict[str, float]:
        project_count = max(1, len(strategy.affected_projects))
        priority_factor = {"low": 0.3, "medium": 0.5, "high": 0.8}[strategy.priority]
        risk_count = len(strategy.risks)
        return {
            "impact": min(1.0, project_count * 0.25),
            "risk": max(0.0, min(1.0, 1.0 - (0.2 * risk_count + (1.0 - priority_factor) * 0.4))),
            "cost": max(0.0, min(1.0, 1.0 - project_count * 0.15)),
            "complexity": max(0.0, min(1.0, 1.0 - project_count * 0.2)),
            "maintainability": _TYPE_MAINTAINABILITY[strategy.strategy_type],
            "migration_difficulty": 1.0 - _TYPE_MIGRATION_COMPLEXITY[strategy.strategy_type],
            "confidence": min(1.0, strategy.confidence),
        }
