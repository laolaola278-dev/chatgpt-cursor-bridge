"""Quality Gate 3.0 deterministic multi-agent evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MultiAgentQualityReport:
    score: int
    agent_consensus: bool
    blocking_issues: list[str]
    dimensions: dict[str, float]
    risk: str

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "agentConsensus": self.agent_consensus, "blockingIssues": list(self.blocking_issues), "dimensions": dict(self.dimensions), "risk": self.risk}


class MultiAgentQualityEvaluator:
    """Scores supplied reports only; it never runs tests or modifies state."""

    def evaluate(self, *, architecture_quality: float = 0, code_quality: float = 0, test_quality: float = 0, review_quality: float = 0, risk: str = "low", agent_scores: dict[str, float] | None = None) -> MultiAgentQualityReport:
        dimensions = {"architecture": _bounded(architecture_quality), "code": _bounded(code_quality), "test": _bounded(test_quality), "review": _bounded(review_quality)}
        scores = list((agent_scores or {}).values())
        consensus = len(scores) <= 1 or max(scores) - min(scores) <= 20
        issues: list[str] = []
        if not consensus: issues.append("agent_consensus_missing")
        if dimensions["test"] < 60: issues.append("test_quality_below_gate")
        if dimensions["review"] < 60: issues.append("review_quality_below_gate")
        risk_label = risk.strip().lower()
        if risk_label not in {"low", "medium", "high", "critical"}: risk_label = "high"
        if risk_label in {"high", "critical"}: issues.append("risk_requires_human_review")
        score = round(sum(dimensions.values()) / 4)
        if risk_label == "medium": score -= 10
        if risk_label == "high": score -= 20
        if risk_label == "critical": score -= 35
        return MultiAgentQualityReport(max(0, min(100, score)), consensus, list(dict.fromkeys(issues)), dimensions, risk_label)


def _bounded(value: float) -> float:
    try: return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError): return 0.0
