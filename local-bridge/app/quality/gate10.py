"""Quality Gate 10.0 - organization engineering health gate.

Upgrades Quality Gate 9.0 from project quality to organization engineering
health: aggregates per-project health scores with open incidents and critical
projects into a single read-only org score. Compatible with earlier gates: it
never gates or blocks execution by itself.
"""

from __future__ import annotations

from typing import Any


class QualityGate10Evaluator:
    """Organization health gate over aggregated project signals."""

    def evaluate(
        self,
        *,
        org: str = "organization",
        org_health_score: int = 100,
        project_count: int = 1,
        open_incidents: int = 0,
        critical_projects: int = 0,
        recommendations: list[str] | None = None,
        blocking_issues: list[str] | None = None,
        strategy_confidence: float | None = None,
        architecture_risk: int | None = None,
        technical_debt: int | None = None,
        cross_project_impact: int | None = None,
        risk_propagation: int | None = None,
        policy_violations: list[str] | None = None,
    ) -> dict[str, Any]:
        """Organization engineering health gate (Phase 22) extended with the
        Phase 24 organization-strategy signals. Every new signal is optional;
        when omitted the output and score match the Phase 22 behavior exactly.
        """
        org_health_score = max(0, min(100, int(org_health_score)))
        project_count = max(0, int(project_count))
        open_incidents = max(0, int(open_incidents))
        critical_projects = max(0, int(critical_projects))

        strategy_confidence = round(max(0.0, min(1.0, float(strategy_confidence))) * 100) if strategy_confidence is not None else 100
        architecture_risk = max(0, min(100, int(architecture_risk))) if architecture_risk is not None else 0
        technical_debt = max(0, min(100, int(technical_debt))) if technical_debt is not None else 0
        cross_project_impact = max(0, min(100, int(cross_project_impact))) if cross_project_impact is not None else 0
        risk_propagation = max(0, min(100, int(risk_propagation))) if risk_propagation is not None else 0
        policy_violations = list(policy_violations or [])

        blocking: list[str] = list(blocking_issues or [])
        if org_health_score < 50:
            blocking.append("organization_health_critical")
        elif org_health_score < 70:
            blocking.append("organization_health_at_risk")
        if open_incidents >= 3:
            blocking.append("open_incidents")
        if critical_projects >= 2:
            blocking.append("critical_projects")
        if policy_violations:
            blocking.append("strategy_policy_violations")
        if architecture_risk >= 70:
            blocking.append("architecture_risk_high")
        if risk_propagation >= 70:
            blocking.append("risk_propagation_high")
        if strategy_confidence < 50:
            blocking.append("strategy_confidence_low")

        penalty = min(
            100,
            (100 - org_health_score) * 0.5
            + open_incidents * 4
            + critical_projects * 10
            + (10 if org_health_score < 70 else 0)
            + (10 if strategy_confidence < 50 else 0)
            + architecture_risk * 0.1
            + risk_propagation * 0.1
            + cross_project_impact * 0.05
            + technical_debt * 0.05,
        )
        quality = max(0, min(100, int(round(org_health_score - penalty))))

        return {
            "organization": org,
            "orgHealthScore": org_health_score,
            "projectCount": project_count,
            "openIncidents": open_incidents,
            "criticalProjects": critical_projects,
            "strategyConfidence": strategy_confidence,
            "architectureRisk": architecture_risk,
            "technicalDebt": technical_debt,
            "crossProjectImpact": cross_project_impact,
            "riskPropagation": risk_propagation,
            "policyViolations": policy_violations,
            "recommendations": list(dict.fromkeys(recommendations or [])),
            "blockingIssues": list(dict.fromkeys(blocking)),
            "quality": quality,
            "readOnly": True,
        }
