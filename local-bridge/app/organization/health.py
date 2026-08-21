"""Organization Health aggregation (Engineering Command Center core).

Turns per-project engineering health reports, agent metrics, incidents and
patterns into an organization-level health report with debt ranking, risk
trends and recommendations. Read-only analysis; never modifies source code.
"""

from __future__ import annotations

from typing import Any

from .models import OrgHealthReport


class OrganizationHealthAggregator:
    def evaluate(
        self,
        org: str,
        project_healths: list[dict[str, Any]],
        *,
        debt_summaries: list[dict[str, Any]] | None = None,
        agent_metrics: list[dict[str, Any]] | None = None,
        incidents: list[dict[str, Any]] | None = None,
        patterns: list[dict[str, Any]] | None = None,
        history: dict[str, list[dict[str, Any]]] | None = None,
    ) -> OrgHealthReport:
        project_healths = project_healths or []
        debt_summaries = debt_summaries or []
        agent_metrics = agent_metrics or []
        incidents = incidents or []
        patterns = patterns or []
        history = history or {}

        health_by_project = [
            {
                "project": str(report.get("project", "unknown")),
                "healthScore": int(report.get("healthScore", 0)),
                "riskLevel": str(report.get("riskLevel", "low")),
            }
            for report in project_healths
        ]
        if project_healths:
            org_health_score = int(round(sum(item["healthScore"] for item in health_by_project) / len(health_by_project)))
        else:
            org_health_score = 100

        debt_ranking = sorted(
            [
                {
                    "project": str(item.get("project", "unknown")),
                    "openDebt": int(item.get("openDebt", 0)),
                    "estimatedCost": int(item.get("estimatedCost", 0)),
                }
                for item in debt_summaries
                if int(item.get("openDebt", 0)) > 0
            ],
            key=lambda item: (item["openDebt"], item["estimatedCost"]),
            reverse=True,
        )

        risk_trends = self._risk_trends(history)

        failure_patterns = [
            {
                "project": str(pattern.get("project", "unknown")),
                "category": str(pattern.get("category", "unknown")),
                "signature": str(pattern.get("signature", "")),
                "occurrences": int(pattern.get("occurrences", 0)),
                "severity": str(pattern.get("severity", "low")),
            }
            for pattern in patterns
        ]

        agent_effectiveness = self._agent_effectiveness(agent_metrics)

        warnings: list[dict[str, Any]] = []
        for item in health_by_project:
            if item["healthScore"] < 60:
                warnings.append(
                    {
                        "code": "project_health_low",
                        "severity": "high",
                        "message": f"Project {item['project']} health is {item['healthScore']}/100 ({item['riskLevel']})",
                    }
                )
            elif item["healthScore"] < 80:
                warnings.append(
                    {
                        "code": "project_health_declining",
                        "severity": "medium",
                        "message": f"Project {item['project']} health is {item['healthScore']}/100 ({item['riskLevel']})",
                    }
                )
        if incidents:
            open_incidents = sum(1 for incident in incidents if str(incident.get("status", "OPEN")).upper() == "OPEN")
            if open_incidents >= 2:
                warnings.append({"code": "incident_count_high", "severity": "high", "message": f"{open_incidents} open incident(s) across the organization"})
        if not health_by_project:
            warnings.append({"code": "no_project_telemetry", "severity": "low", "message": "No project health telemetry registered yet"})

        recommendations: list[dict[str, Any]] = []
        for warning in warnings:
            if warning["code"] == "project_health_low":
                recommendations.append({"code": "remediate_low_health", "priority": "high", "suggestion": "Investigate the lowest-health projects before new execution windows"})
            elif warning["code"] == "project_health_declining":
                recommendations.append({"code": "monitor_declining", "priority": "medium", "suggestion": "Review recent executions for the declining projects"})
            elif warning["code"] == "incident_count_high":
                recommendations.append({"code": "gate_incidents", "priority": "high", "suggestion": "Resolve open incidents before scheduling cross-project work"})
            elif warning["code"] == "no_project_telemetry":
                recommendations.append({"code": "register_telemetry", "priority": "low", "suggestion": "Register projects in the organization graph and run health scans"})
        if not warnings:
            recommendations.append({"code": "maintain_org_health", "priority": "low", "suggestion": "Organization health is stable; continue verification-first execution"})

        return OrgHealthReport(
            org=org,
            org_health_score=org_health_score,
            project_count=len(health_by_project),
            health_by_project=health_by_project,
            debt_ranking=debt_ranking,
            risk_trends=risk_trends,
            failure_patterns=failure_patterns,
            agent_effectiveness=agent_effectiveness,
            warnings=warnings,
            recommendations=recommendations,
        )

    @staticmethod
    def _risk_trends(history: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        trends: list[dict[str, Any]] = []
        for project, snapshots in history.items():
            if not snapshots:
                continue
            latest = int(snapshots[0].get("healthScore", 0))
            previous = int(snapshots[1].get("healthScore", latest)) if len(snapshots) > 1 else latest
            delta = latest - previous
            direction = "improving" if delta > 2 else "declining" if delta < -2 else "stable"
            trends.append({"project": project, "healthScore": latest, "delta": delta, "direction": direction})
        return sorted(trends, key=lambda item: item["delta"])

    @staticmethod
    def _agent_effectiveness(agent_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not agent_metrics:
            return []
        total_completed = sum(int(metric.get("tasksCompleted", 0)) for metric in agent_metrics)
        total_failed = sum(int(metric.get("failedTasks", 0)) for metric in agent_metrics)
        completed_ratio = total_completed / (total_completed + total_failed) if (total_completed + total_failed) else 0.0
        quality_values = [float(metric.get("averageQuality", 0) or 0) for metric in agent_metrics if metric.get("averageQuality")]
        average_quality = sum(quality_values) / len(quality_values) if quality_values else 0.0
        effectiveness = int(round(completed_ratio * 100 * 0.6 + average_quality * 0.4)) if (total_completed or quality_values) else 0
        return [{"agentCount": len(agent_metrics), "completionRate": round(completed_ratio, 3), "averageQuality": round(average_quality, 2), "effectivenessScore": effectiveness}]
