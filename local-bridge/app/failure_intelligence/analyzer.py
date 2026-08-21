from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import FailurePattern


class FailureIntelligenceAnalyzer:
    """Read-only aggregation of execution failure signals."""

    def analyze(self, project: str, *, loops: list[Any] = [], tasks: list[Any] = [], results: list[Any] = []) -> list[FailurePattern]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

        def value(record: Any, name: str, default: Any = None) -> Any:
            if isinstance(record, dict): return record.get(name, default)
            return getattr(record, name, default)

        for loop in loops:
            status = str(value(loop, "status", ""))
            if hasattr(value(loop, "status"), "value"): status = value(loop, "status").value
            if status in {"FAILED", "ROLLED_BACK"}:
                category = "rollback" if status == "ROLLED_BACK" else "execution_failure"
                signature = str(value(loop, "verification", {}).get("status", status))
                grouped[(category, signature)].append({"source": value(loop, "id", "unknown"), "status": status})
        for task in tasks:
            status = str(value(task, "status", ""))
            if hasattr(value(task, "status"), "value"): status = value(task, "status").value
            if status == "FAILED": grouped[("task_failure", "task_failed")].append({"source": value(task, "id", "unknown")})
        for result in results:
            verification = value(result, "verification", {}) or {}
            if isinstance(verification, dict) and verification.get("status") == "FAIL":
                grouped[("test_failure", str(verification.get("error") or "verification_failed"))].append({"source": value(result, "id", "unknown"), "checks": verification.get("checks", [])})
                if verification.get("risk") in {"HIGH", "high"}:
                    grouped[("risk_block", "high_risk")].append({"source": value(result, "id", "unknown")})
        patterns: list[FailurePattern] = []
        for index, ((category, signature), evidence) in enumerate(sorted(grouped.items())):
            occurrences = len(evidence)
            severity = "high" if category in {"risk_block", "rollback"} else ("medium" if occurrences > 1 else "low")
            patterns.append(FailurePattern(f"failure_{index}_{category}", project, category, signature, occurrences, severity, evidence[:20]))
        return patterns
