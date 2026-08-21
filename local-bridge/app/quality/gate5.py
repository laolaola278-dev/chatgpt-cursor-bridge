from __future__ import annotations

from typing import Any


class QualityGate5Evaluator:
    def evaluate(
        self,
        *,
        architecture_score: int = 100,
        maintainability_score: int = 100,
        risk_score: int = 0,
        decision_confidence: int = 100,
        technical_debt: int = 0,
        technical_debt_items: int = 0,
        recommendations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        values = [max(0, min(100, architecture_score)), max(0, min(100, maintainability_score)), max(0, min(100, 100 - risk_score)), max(0, min(100, decision_confidence)), max(0, min(100, 100 - technical_debt))]
        quality = round(sum(values) / len(values))
        risk = "high" if quality < 60 or risk_score >= 70 else "medium" if quality < 80 or risk_score >= 35 else "low"
        return {"quality": quality, "risk": risk, "architectureScore": values[0], "maintainabilityScore": values[1], "riskScore": max(0, min(100, risk_score)), "decisionConfidence": values[3], "technicalDebt": {"score": max(0, min(100, technical_debt)), "items": max(0, technical_debt_items)}, "recommendations": recommendations or [], "readOnly": True}
