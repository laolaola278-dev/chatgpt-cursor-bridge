from __future__ import annotations

from typing import Any

from .models import EngineeringReport


class EngineeringReportGenerator:
    def generate(self, project: str, *, insights: list[Any] = [], proposals: list[Any] = [], decisions: list[Any] = [], loops: list[Any] = [], verifications: list[Any] = [], failures: list[Any] = [], learning: list[Any] = []) -> EngineeringReport:
        def convert(items: list[Any]) -> list[dict[str, Any]]:
            result = []
            for item in items:
                if isinstance(item, dict): result.append(item)
                elif hasattr(item, "as_dict"): result.append(item.as_dict())
            return result

        problems = [item for item in convert(failures + verifications) if item.get("status") in ("FAILED", "FAIL", "ROLLED_BACK") or item.get("severity") == "high"]
        analysis = convert(insights)
        decisions = convert(decisions)
        execution = [item for item in convert(loops) if item.get("status") in ("COMPLETED", "EXECUTING", "FAILED", "ROLLED_BACK", "RECOVERED")]
        verification = convert(verifications)
        risk = [{"title": "High-risk failure pattern", "id": item.get("id", "")} for item in convert(failures) if item.get("severity") == "high"]
        learning = convert(learning)
        return EngineeringReport(project=project, problem=problems, analysis=analysis, decisions=decisions, execution=execution, verification=verification, risk=risk, learning=learning)
