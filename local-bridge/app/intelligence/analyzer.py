from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from secrets import token_hex
from typing import Any

from app.code_intelligence.index import CodeIndex

from .models import Insight, InsightType, RiskFactors, Severity
from .risk import IntelligenceRiskEngine


class EngineeringAnalyzer:
    """Read-only analyzer over indexed metadata; it never edits project files."""

    def __init__(self, index: CodeIndex, risk: IntelligenceRiskEngine | None = None) -> None:
        self.index = index
        self.risk = risk or IntelligenceRiskEngine()

    @staticmethod
    def _severity(score: int) -> Severity:
        return Severity.CRITICAL if score >= 80 else Severity.HIGH if score >= 60 else Severity.MEDIUM if score >= 30 else Severity.LOW

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{token_hex(8)}"

    def analyze(
        self,
        project: str,
        *,
        changed_files: list[str] | None = None,
        test_coverage: int | None = None,
        security_sensitive: bool = False,
    ) -> list[Insight]:
        stats = self.index.stats(project)
        dependencies = self.index.dependencies(project)
        incoming = Counter(edge["target"] for edge in dependencies)
        outgoing = Counter(edge["source"] for edge in dependencies)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        insights: list[Insight] = []
        changed = changed_files or []

        hotspots = sorted(incoming.items(), key=lambda item: (-item[1], item[0]))
        if hotspots and hotspots[0][1] >= 5:
            path, count = hotspots[0]
            score = self.risk.score_factors(impact_scope=count, dependency_count=count, test_coverage=test_coverage)["score"]
            insights.append(Insight(self._id("ins"), project, InsightType.ARCHITECTURE_RISK, self._severity(score), "High coupling detected", path, [f"{count} modules depend on this file"], "Consider extracting a focused service boundary", now))

        if stats["files"] and stats["dependencies"] > max(10, stats["files"] * 2):
            score = self.risk.score_factors(impact_scope=stats["files"], dependency_count=stats["dependencies"], test_coverage=test_coverage)["score"]
            insights.append(Insight(self._id("ins"), project, InsightType.DEPENDENCY_RISK, self._severity(score), "Dependency graph is dense", "project", [f"{stats['dependencies']} dependencies across {stats['files']} files"], "Review module boundaries before adding more coupling", now))

        if test_coverage is not None and test_coverage < 60:
            score = self.risk.score_factors(changed_files=len(changed), impact_scope=len(changed), test_coverage=test_coverage)["score"]
            insights.append(Insight(self._id("ins"), project, InsightType.TEST_GAP, self._severity(score), "Test coverage gap detected", changed[0] if changed else "project", [f"reported coverage is {test_coverage}%"], "Add focused tests before changing high-impact code", now))

        if security_sensitive or any(any(word in path.lower() for word in ("auth", "security", "permission", "token")) for path in changed):
            score = self.risk.score_factors(impact_scope=len(changed), changed_files=len(changed), security_sensitive=True, test_coverage=test_coverage)["score"]
            insights.append(Insight(self._id("ins"), project, InsightType.SECURITY_RISK, self._severity(score), "Security-sensitive change requires review", changed[0] if changed else "project", ["security-sensitive scope was explicitly marked"], "Require a focused security review and rollback plan", now))

        if stats["files"] and stats["symbols"] > stats["files"] * 25:
            insights.append(Insight(self._id("ins"), project, InsightType.CODE_SMELL, Severity.MEDIUM, "Large symbol surface detected", "project", [f"{stats['symbols']} symbols across {stats['files']} files"], "Split oversized modules and preserve tests around public behavior", now))

        if not insights and stats["files"]:
            insights.append(Insight(self._id("ins"), project, InsightType.MAINTENANCE_RISK, Severity.LOW, "No high-confidence engineering risk found", "project", [f"{stats['files']} indexed files", f"{stats['dependencies']} indexed dependencies"], "Continue observing quality and change history", now))
        return insights
