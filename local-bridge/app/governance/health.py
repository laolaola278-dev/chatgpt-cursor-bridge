"""Engineering health monitor.

Read-only analysis that turns execution, verification, failure and agent
metric records into a health score, risk level, trends, warnings and
recommendations. It never modifies code, memory or workflows.
"""

from __future__ import annotations

from typing import Any

from .models import (
    EngineeringHealthReport,
    GovernanceRecommendation,
    GovernanceWarning,
    HealthTrend,
)

_RISK_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0}

_FAILED_STATES = {"FAILED", "ROLLED_BACK"}
_TERMINAL_GOOD = {"COMPLETED", "VERIFIED"}


class EngineeringHealthManager:
    def evaluate(
        self,
        project: str,
        *,
        tasks: list[dict[str, Any]] | None = None,
        loops: list[dict[str, Any]] | None = None,
        results: list[dict[str, Any]] | None = None,
        failures: list[dict[str, Any]] | None = None,
        agent_metrics: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> EngineeringHealthReport:
        loops = loops or []
        results = results or []
        failures = failures or []
        agent_metrics = agent_metrics or []
        history = history or []

        # -- component scores (each 0..100) --------------------------------
        success_score = self._success_score(loops, results)
        rollback_score = self._rollback_score(loops, results)
        failure_score = self._failure_score(failures)
        test_score = self._test_score(results)
        risk_score = self._risk_component(results)
        agent_score = self._agent_score(agent_metrics)

        components = {
            "successRate": success_score,
            "rollbackStability": rollback_score,
            "failureResilience": failure_score,
            "testStability": test_score,
            "changeRisk": risk_score,
            "agentPerformance": agent_score,
            "counts": {
                "loops": len(loops),
                "results": len(results),
                "failures": len(failures),
                "agents": len(agent_metrics),
            },
        }

        weights = {"successRate": 0.25, "rollbackStability": 0.15, "failureResilience": 0.15, "testStability": 0.25, "changeRisk": 0.20}
        score = sum(components[key] * weight for key, weight in weights.items())
        health_score = max(0, min(100, int(round(score))))
        risk_level = "low" if health_score >= 80 else "medium" if health_score >= 60 else "high"

        warnings = self._warnings(components, failures, loops, results)
        recommendations = self._recommendations(warnings, components)
        trends = self._trends(components, history)

        return EngineeringHealthReport(
            project=project,
            health_score=health_score,
            risk_level=risk_level,
            components=components,
            trends=trends,
            warnings=warnings,
            recommendations=recommendations,
        )

    # -- component calculators ---------------------------------------------

    def _success_score(self, loops: list[dict[str, Any]], results: list[dict[str, Any]]) -> float:
        total = len(loops)
        if total == 0:
            return 100.0
        good = sum(1 for loop in loops if str(loop.get("status", "")).upper() in _TERMINAL_GOOD)
        failed = sum(1 for loop in loops if str(loop.get("status", "")).upper() in _FAILED_STATES)
        if good + failed == 0:
            return 80.0
        return max(0.0, min(100.0, good / (good + failed) * 100.0))

    def _rollback_score(self, loops: list[dict[str, Any]], results: list[dict[str, Any]]) -> float:
        total = len(loops)
        if total == 0:
            return 100.0
        rolled = sum(1 for loop in loops if str(loop.get("status", "")).upper() == "ROLLED_BACK")
        return max(0.0, min(100.0, 100.0 - (rolled / total) * 200.0))

    def _failure_score(self, failures: list[dict[str, Any]]) -> float:
        return max(0.0, min(100.0, 100.0 - len(failures) * 15.0))

    def _test_score(self, results: list[dict[str, Any]]) -> float:
        if not results:
            return 80.0
        passed = 0
        total = 0
        quality_sum = 0.0
        for result in results:
            verification = result.get("verification") or {}
            status = verification.get("status") or verification.get("verificationStatus")
            if status:
                total += 1
                if str(status).upper() == "PASS":
                    passed += 1
            quality_sum += float(result.get("qualityScore", 0) or 0)
        stability = (passed / total * 100.0) if total else 80.0
        avg_quality = quality_sum / len(results)
        return max(0.0, min(100.0, 0.6 * stability + 0.4 * avg_quality))

    def _risk_component(self, results: list[dict[str, Any]]) -> float:
        if not results:
            return 100.0
        total = sum(_RISK_WEIGHT.get(str(result.get("riskScore", "low")).lower(), 1.0) for result in results)
        avg = total / len(results)
        return max(0.0, min(100.0, 100.0 - (avg - 1.0) * 50.0))

    def _agent_score(self, agent_metrics: list[dict[str, Any]]) -> float:
        if not agent_metrics:
            return 80.0
        total = 0.0
        for metric in agent_metrics:
            total += float(metric.get("successRate", metric.get("success_rate", 0)) or 0)
        return max(0.0, min(100.0, total / len(agent_metrics)))

    # -- warnings / recommendations / trends -------------------------------

    def _warnings(
        self,
        components: dict[str, Any],
        failures: list[dict[str, Any]],
        loops: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> list[GovernanceWarning]:
        warnings: list[GovernanceWarning] = []
        if components["testStability"] < 60:
            warnings.append(GovernanceWarning("test_stability_low", "medium", "Test stability below 60; flaky or missing verification"))
        if components["changeRisk"] < 60:
            warnings.append(GovernanceWarning("change_risk_high", "medium", "Average change risk is high across recent executions"))
        if len(failures) >= 3:
            warnings.append(GovernanceWarning("failure_frequency_high", "high", f"{len(failures)} failure pattern(s) detected in this window"))
        rolled = sum(1 for loop in loops if str(loop.get("status", "")).upper() == "ROLLED_BACK")
        if loops and rolled / len(loops) > 0.25:
            warnings.append(GovernanceWarning("rollback_frequency_high", "high", "Rollback frequency above 25% of execution loops"))
        high_risk = sum(1 for result in results if str(result.get("riskScore", "low")).lower() == "high")
        if high_risk >= 2:
            warnings.append(GovernanceWarning("high_risk_changes", "medium", f"{high_risk} high-risk change(s) executed"))
        if components["agentPerformance"] < 60:
            warnings.append(GovernanceWarning("agent_performance_low", "low", "Average agent success rate below 60"))
        return warnings

    def _recommendations(self, warnings: list[GovernanceWarning], components: dict[str, Any]) -> list[GovernanceRecommendation]:
        recommendations: list[GovernanceRecommendation] = []
        for warning in warnings:
            if warning.code == "test_stability_low":
                recommendations.append(GovernanceRecommendation("improve_test_stability", "medium", "Expand verification coverage and stabilize flaky tests before further changes"))
            elif warning.code == "change_risk_high":
                recommendations.append(GovernanceRecommendation("reduce_change_risk", "medium", "Break large changes into smaller proposals and require review"))
            elif warning.code == "failure_frequency_high":
                recommendations.append(GovernanceRecommendation("investigate_failures", "high", "Open an investigation for repeated failure patterns before new executions"))
            elif warning.code == "rollback_frequency_high":
                recommendations.append(GovernanceRecommendation("review_rollbacks", "high", "Review recent rollbacks and strengthen pre-execution checks"))
            elif warning.code == "high_risk_changes":
                recommendations.append(GovernanceRecommendation("gate_high_risk", "medium", "Route high-risk changes through mandatory human review"))
            elif warning.code == "agent_performance_low":
                recommendations.append(GovernanceRecommendation("monitor_agents", "low", "Review agent capability metrics; do not auto-adjust permissions"))
        if components["testStability"] >= 60 and not warnings:
            recommendations.append(GovernanceRecommendation("maintain_health", "low", "Project health is stable; continue verification-first execution"))
        return recommendations

    def _trends(self, components: dict[str, Any], history: list[dict[str, Any]]) -> list[HealthTrend]:
        if not history:
            return []
        previous = history[0]
        previous_components = previous.get("components", {})
        trends: list[HealthTrend] = []
        for key in ("successRate", "testStability", "changeRisk", "rollbackStability", "failureResilience"):
            current = components.get(key, 0)
            prior = previous_components.get(key, current)
            delta = current - prior
            direction = "improving" if delta > 2 else "declining" if delta < -2 else "stable"
            trends.append(HealthTrend(key, delta, direction))
        return trends
