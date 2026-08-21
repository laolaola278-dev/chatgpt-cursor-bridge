"""Read-only composition of Phase 28 governance signals.

This facade performs no persistence and no mutation. Governance records,
risk findings, violations, review proposals, governance memory, trends,
policies, and the governance graph are only readable here; writes happen
exclusively through approval-gated actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.intelligence.governance import (
    GovernanceGraphBuilder,
    GovernanceStore,
    GovernanceTrendAnalyzer,
    list_policies,
)
from app.intelligence.governance.models import RISK_ORDER
from app.intelligence.validation import ValidationStore
from app.quality.gate14 import QualityGate14Evaluator


@dataclass(frozen=True)
class Phase28Snapshot:
    project: str
    records: list[Any]
    risks: list[Any]
    violations: list[Any]
    reviews: list[Any]
    memory: list[Any]
    trends: list[Any]
    signals: list[dict[str, str]]
    policies: list[Any]
    graph: dict[str, Any]
    quality14: dict[str, Any]
    reviewRequired: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "records": [item.as_dict() for item in self.records],
            "risks": [item.as_dict() for item in self.risks],
            "violations": [item.as_dict() for item in self.violations],
            "reviews": [item.as_dict() for item in self.reviews],
            "memory": [item.as_dict() for item in self.memory],
            "trends": [item.as_dict() for item in self.trends],
            "signals": list(self.signals),
            "policies": [item.as_dict() for item in self.policies],
            "graph": self.graph,
            "quality14": dict(self.quality14),
            "reviewRequired": self.reviewRequired,
            "readOnly": True,
        }


def build_phase28_snapshot(settings: Settings, project: str, *, limit: int = 1000) -> Phase28Snapshot:
    validation = ValidationStore(settings.intelligence_db_path)
    governance = GovernanceStore(settings.intelligence_db_path)

    records = governance.records(project, limit=limit)
    risks = governance.risks(project, limit=limit)
    violations = governance.violations(project, limit=limit)
    reviews = governance.proposals(project, limit=limit)
    memory = governance.memory(project, limit=limit)

    analyzer = GovernanceTrendAnalyzer(validation)
    trends = analyzer.overall(project, governance_records=records)
    signals = analyzer.detected(trends)

    evaluations = validation.evaluations(project, limit=limit)
    effectiveness = validation.effectiveness(project, limit=limit)
    decision_outcomes = validation.decision_outcomes(project, limit=limit)
    benchmarks = validation.benchmarks(project, limit=limit)

    counted = [item for item in evaluations if item.counted]
    correct = sum(1 for item in counted if item.correct)
    prediction_quality = round(correct / len(counted), 3) if counted else None
    failure_rate = round(1 - prediction_quality, 3) if prediction_quality is not None else None
    rejection = [item for item in effectiveness if item.user_decision == "rejected"]
    rejection_rate = round(len(rejection) / len(effectiveness), 3) if effectiveness else None
    effectiveness_rate = (
        round(sum(item.effectiveness_score for item in effectiveness if item.classification != "rejected") / max(1, len([item for item in effectiveness if item.classification != "rejected"])), 3)
        if effectiveness
        else None
    )
    decision_success_rate = (
        round(sum(1 for item in decision_outcomes if item.status == "SUCCESS") / len(decision_outcomes), 3)
        if decision_outcomes
        else None
    )
    max_risk = max((item.risk_level for item in records), key=lambda level: RISK_ORDER.get(level, 0), default="LOW")
    max_risk_score = max((item.risk_score for item in records), default=0.0)
    benchmark_score = max((item.score for item in benchmarks), default=None)
    best_recent_accuracy = None
    if counted:
        recent = counted[-20:]
        best_recent_accuracy = round(sum(1 for item in recent if item.correct) / len(recent), 3)

    quality14 = QualityGate14Evaluator().evaluate(
        prediction_quality=prediction_quality,
        prediction_count=len({item.prediction_id for item in evaluations}),
        evaluation_quality=all(item.prediction_id and item.evaluation_result for item in evaluations),
        evaluation_count=len(evaluations),
        recommendation_effectiveness=effectiveness_rate,
        effectiveness_count=len(effectiveness),
        decision_success_rate=decision_success_rate,
        decision_count=len(decision_outcomes),
        max_risk_level=max_risk,
        max_risk_score=max_risk_score,
        confidence_calibration=abs((best_recent_accuracy or 0.0) - (sum(item.confidence for item in counted) / len(counted) if counted else 0.0)),
        regression_rate=failure_rate,
        benchmark_score=benchmark_score,
        benchmark_count=len(benchmarks),
        policy_compliance=not any(item.severity == "blocking" for item in violations),
        violation_count=len(violations),
        audit_complete=all(item.audit_request_id for item in records),
    )

    graph = GovernanceGraphBuilder().build(
        project=project,
        evaluations=evaluations,
        effectiveness=effectiveness,
        decision_outcomes=decision_outcomes,
        risks=risks,
        governance_records=records,
    )

    return Phase28Snapshot(
        project=project,
        records=records,
        risks=risks,
        violations=violations,
        reviews=reviews,
        memory=memory,
        trends=trends,
        signals=signals,
        policies=list_policies(),
        graph=graph,
        quality14=quality14,
        reviewRequired=any(item.status == "proposed" for item in reviews) or quality14["status"] in ("REVIEW_REQUIRED", "BLOCKED"),
    )


Phase28Governance = build_phase28_snapshot
Phase28Manager = build_phase28_snapshot
