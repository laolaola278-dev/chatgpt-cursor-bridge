"""Task 2 · Prediction Accuracy System.

Statistics are computed only from stored, real historical evaluations. No
score is fabricated and no benchmark is synthesized. Filters support agent,
project, prediction kind, model, and time range so accuracy can be inspected
along the dimensions that matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.intelligence.common import bounded_confidence, ensure_project

from .models import COUNTED_EVALUATION_RESULTS, EvaluationRecord

CALIBRATION_BINS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    correct: int
    bin_accuracy: float
    bin_mean_confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "lower": self.lower, "upper": self.upper, "count": self.count,
            "correct": self.correct, "binAccuracy": round(self.bin_accuracy, 3),
            "binMeanConfidence": round(self.bin_mean_confidence, 3),
        }


@dataclass(frozen=True)
class AccuracyReport:
    project_id: str
    predictions: int
    counted: int
    correct: int
    incorrect: int
    partial: int
    unknown: int
    accuracy: float
    precision: float
    recall: float
    false_positive: int
    false_negative: int
    false_positive_rate: float
    false_negative_rate: float
    success_rate: float
    calibration_error: float
    calibration: list[CalibrationBin] = field(default_factory=list)
    by_kind: dict[str, dict[str, float]] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "projectId": self.project_id,
            "predictions": self.predictions, "counted": self.counted,
            "correct": self.correct, "incorrect": self.incorrect,
            "partial": self.partial, "unknown": self.unknown,
            "accuracy": self.accuracy, "precision": self.precision, "recall": self.recall,
            "falsePositive": self.false_positive, "falseNegative": self.false_negative,
            "falsePositiveRate": self.false_positive_rate,
            "falseNegativeRate": self.false_negative_rate,
            "successRate": self.success_rate,
            "calibrationError": self.calibration_error,
            "calibration": [bin_.as_dict() for bin_ in self.calibration],
            "byKind": self.by_kind, "filters": self.filters,
            "readOnly": True,
        }


def _round(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 3)


class AccuracySystem:
    """Compute prediction accuracy metrics from stored evaluation records."""

    @staticmethod
    def _matches(record: EvaluationRecord, *, agent_id: str | None, model_id: str | None, kind: str | None, since: str | None, until: str | None) -> bool:
        if agent_id and record.agent_id != agent_id:
            return False
        if model_id and record.model_id != model_id:
            return False
        if kind and record.evaluation_kind != kind:
            return False
        if since and record.evaluated_at < since:
            return False
        if until and record.evaluated_at > until:
            return False
        return True

    def report(
        self,
        project_id: str,
        records: Iterable[EvaluationRecord],
        *,
        agent_id: str | None = None,
        model_id: str | None = None,
        kind: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> AccuracyReport:
        project = ensure_project(project_id)
        selected = [
            record
            for record in records
            if record.project_id == project
            and self._matches(record, agent_id=agent_id, model_id=model_id, kind=kind, since=since, until=until)
        ]
        counted = [record for record in selected if record.evaluation_result in COUNTED_EVALUATION_RESULTS]
        tp = sum(1 for record in counted if record.correct and record.confidence >= 0.5)
        tn = sum(1 for record in counted if record.correct and record.confidence < 0.5)
        fp = sum(1 for record in counted if not record.correct and record.confidence >= 0.5)
        fn = sum(1 for record in counted if not record.correct and record.confidence < 0.5)
        correct = sum(1 for record in counted if record.correct)
        total = len(counted)
        partial = sum(1 for record in selected if record.evaluation_result == "partial")
        unknown = sum(1 for record in selected if record.evaluation_result == "unknown")

        # Calibration: accuracy within confidence bins, weighted by count.
        calibration: list[CalibrationBin] = []
        for lower, upper in CALIBRATION_BINS:
            in_bin = [record for record in counted if lower <= record.confidence < upper or (upper == 1.0 and record.confidence == 1.0)]
            bin_count = len(in_bin)
            bin_correct = sum(1 for record in in_bin if record.correct)
            bin_accuracy = bin_correct / bin_count if bin_count else 0.0
            bin_mean_confidence = (sum(record.confidence for record in in_bin) / bin_count) if bin_count else (lower + upper) / 2.0
            calibration.append(CalibrationBin(lower, upper, bin_count, bin_correct, bin_accuracy, bin_mean_confidence))
        weighted = sum(bin_.count * abs(bin_.bin_accuracy - bin_.bin_mean_confidence) for bin_ in calibration)
        calibration_error = weighted / total if total else 0.0

        by_kind: dict[str, dict[str, float]] = {}
        for record in counted:
            bucket = by_kind.setdefault(
                record.evaluation_kind,
                {"counted": 0.0, "correct": 0.0, "accuracy": 0.0},
            )
            bucket["counted"] += 1
            if record.correct:
                bucket["correct"] += 1
        for values in by_kind.values():
            values["accuracy"] = _round(values["correct"] / values["counted"]) if values["counted"] else 0.0

        return AccuracyReport(
            project_id=project,
            predictions=len(selected),
            counted=total,
            correct=correct,
            incorrect=total - correct,
            partial=partial,
            unknown=unknown,
            accuracy=_round(correct / total) if total else 0.0,
            precision=_round(tp / (tp + fp)) if tp + fp else 0.0,
            recall=_round(tp / (tp + fn)) if tp + fn else 0.0,
            false_positive=fp,
            false_negative=fn,
            false_positive_rate=_round(fp / (fp + tn)) if fp + tn else 0.0,
            false_negative_rate=_round(fn / (fn + tp)) if fn + tp else 0.0,
            success_rate=_round(correct / total) if total else 0.0,
            calibration_error=_round(calibration_error),
            calibration=calibration,
            by_kind=by_kind,
            filters={
                "agentId": agent_id or "",
                "modelId": model_id or "",
                "kind": kind or "",
                "since": since or "",
                "until": until or "",
            },
        )

    def failed_predictions(self, records: Iterable[EvaluationRecord], limit: int = 100) -> list[dict[str, Any]]:
        """Recent incorrect evaluations, used by the dashboard read-only view."""
        failed = [record for record in records if record.counted and not record.correct]
        failed.sort(key=lambda record: (record.evaluated_at, record.evaluation_id), reverse=True)
        return [record.as_dict() for record in failed[: max(1, min(int(limit), 500))]]
