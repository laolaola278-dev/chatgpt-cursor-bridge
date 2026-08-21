from __future__ import annotations

from typing import Any


class QualityGate4Evaluator:
    def evaluate(self, *, architecture_impact: int = 0, change_risk: str = "low", regression_risk: str = "low", historical_stability: int = 100, affected_modules: list[str] | None = None) -> dict[str, Any]:
        risk_weights = {"low": 0, "medium": 15, "high": 35}
        score = max(0, min(100, 100 - min(35, architecture_impact) - risk_weights.get(change_risk.lower(), 25) - risk_weights.get(regression_risk.lower(), 25) + max(-20, min(0, historical_stability - 100))))
        risk = "high" if score < 60 else "medium" if score < 80 else "low"
        issues: list[str] = []
        if risk == "high": issues.append("Quality score is below the safe delivery threshold")
        if regression_risk.lower() == "high": issues.append("Regression risk requires human review")
        return {"score": score, "risk": risk, "affectedModules": affected_modules or [], "architectureImpact": architecture_impact, "changeRisk": change_risk, "regressionRisk": regression_risk, "historicalStability": historical_stability, "recommendation": "Review affected modules and historical changes before delivery" if issues else "Ready for human review", "blockingIssues": issues, "readOnly": True}
