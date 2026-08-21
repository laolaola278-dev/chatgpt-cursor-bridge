from __future__ import annotations

from typing import Any


class QualityGate6Evaluator:
    def evaluate(self, *, simulation_confidence: float = 0.0, alternative_coverage: int = 0, risk_prediction_accuracy: int = 0, plan_completeness: int = 0, missing_information: list[str] | None = None) -> dict[str, Any]:
        confidence = max(0.0, min(1.0, simulation_confidence))
        coverage = max(0, min(100, alternative_coverage))
        accuracy = max(0, min(100, risk_prediction_accuracy))
        completeness = max(0, min(100, plan_completeness))
        quality = round(confidence * 30 + coverage * 0.2 + accuracy * 0.25 + completeness * 0.25)
        return {"quality": max(0, min(100, quality)), "simulationConfidence": confidence, "alternativeCoverage": coverage, "riskPredictionAccuracy": accuracy, "planCompleteness": completeness, "missingInformation": missing_information or [], "readOnly": True}
