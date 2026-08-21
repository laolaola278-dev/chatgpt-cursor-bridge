from __future__ import annotations

from app.code_intelligence.index import CodeIndex

from .analyzer import EngineeringAnalyzer
from .decision import DecisionManager
from .models import Decision
from .recommendation import RecommendationEngine
from .risk import IntelligenceRiskEngine
from .storage import IntelligenceStorage


class IntelligenceManager:
    def __init__(self, storage: IntelligenceStorage, index: CodeIndex) -> None:
        self.storage = storage
        self.index = index
        self.risk = IntelligenceRiskEngine()
        self.analyzer = EngineeringAnalyzer(index, self.risk)
        self.recommendations = RecommendationEngine(self.risk)
        self.decisions = DecisionManager(storage)

    def analyze(self, project: str, *, changed_files: list[str] | None = None, test_coverage: int | None = None, security_sensitive: bool = False) -> dict[str, object]:
        insights = self.analyzer.analyze(project, changed_files=changed_files, test_coverage=test_coverage, security_sensitive=security_sensitive)
        dependencies = self.index.dependencies(project)
        proposals = self.recommendations.from_insights(insights, dependency_count=len(dependencies), changed_files=len(changed_files or []), test_coverage=test_coverage)
        self.storage.save_insights(insights)
        self.storage.save_proposals(proposals)
        return {"project": project, "insights": [item.as_dict() for item in insights], "proposals": [item.as_dict() for item in proposals], "readOnlyAnalysis": True}

    def create_decision(self, **kwargs: object) -> Decision:
        return self.decisions.create(**kwargs)  # type: ignore[arg-type]
