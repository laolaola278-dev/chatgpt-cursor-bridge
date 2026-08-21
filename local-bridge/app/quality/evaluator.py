"""Quality Gate 2.0 evaluator."""

from __future__ import annotations

from typing import Any

from .models import QualityReport
from .rules import file_penalty, risk_penalty


class QualityEvaluator:
    def evaluate(self, *, git_diff: dict[str, Any] | None = None, test_result: dict[str, Any] | None = None, risk: str = "low", memory_recorded: bool = True) -> QualityReport:
        git_diff = git_diff or {}; test_result = test_result or {}
        files = git_diff.get("files") or git_diff.get("changedFiles") or []
        file_count = len(files) if isinstance(files, list) else int(git_diff.get("fileCount", 0) or 0)
        test_passed = test_result.get("passed") if test_result else None
        issues: list[str] = []
        score = 100 - file_penalty(file_count) - risk_penalty(risk)
        if test_passed is False: score -= 35; issues.append("test_result_failed")
        if test_passed is None: score -= 10; issues.append("test_result_missing")
        if not memory_recorded: score -= 10; issues.append("memory_record_missing")
        if file_count > 20: issues.append("too_many_modified_files")
        if risk.lower() in {"high", "critical"}: issues.append("high_risk_requires_human_review")
        if test_passed is False or risk.lower() == "critical": risk_label = "critical"
        elif risk.lower() == "high" or file_count > 20: risk_label = "high"
        elif risk.lower() == "medium" or score < 70: risk_label = "medium"
        else: risk_label = "low"
        return QualityReport(max(0, min(100, score)), risk_label, issues, {"gitDiff": {"fileCount": file_count}, "test": {"passed": test_passed}, "memoryRecorded": memory_recorded})
