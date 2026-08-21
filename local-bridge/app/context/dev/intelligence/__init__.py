"""Phase 30 · Context Intelligence & Developer Workflow Preparation.

Read-only context intelligence built on top of the Phase 29 developer
context: relevance ranking, context budget 2.0, deduplication, code
relationship analysis, error / test-failure / git-diff / code-review
assistants, prompt-injection protection and structured patch proposals
(which never touch source files without human approval).
"""

from .budget2 import ContextBudget2
from .code_review import CodeReviewAssistant
from .dedup import ContextDeduplicator
from .engine import ContextIntelligenceEngine
from .error_assistant import ErrorContextAssistant
from .git_intel import GitDiffIntelligence
from .injection import PromptInjectionGuard
from .models import (
    ContextCandidate,
    DedupReport,
    ErrorContextBundle,
    GitDiffAnalysis,
    InjectionReport,
    PatchProposal,
    RankedContextItem,
    RelationshipReport,
    SuggestedContextResult,
    TestFailureContext,
)
from .proposal import PatchProposalGenerator, PatchProposalStore
from .relationships import RelationshipAnalyzer
from .scoring import ContextRelevanceScorer
from .test_failure import TestFailureAssistant

__all__ = [
    "CodeReviewAssistant",
    "ContextBudget2",
    "ContextCandidate",
    "ContextDeduplicator",
    "ContextIntelligenceEngine",
    "ContextRelevanceScorer",
    "DedupReport",
    "ErrorContextAssistant",
    "ErrorContextBundle",
    "GitDiffAnalysis",
    "GitDiffIntelligence",
    "InjectionReport",
    "PatchProposal",
    "PatchProposalGenerator",
    "PatchProposalStore",
    "PromptInjectionGuard",
    "RankedContextItem",
    "RelationshipAnalyzer",
    "RelationshipReport",
    "SuggestedContextResult",
    "TestFailureAssistant",
    "TestFailureContext",
]
