"""Phase 30 · Context Intelligence & Developer Workflow Preparation models.

All structures are read-only analysis outputs produced by deterministic
engines. Nothing here can execute, mutate source, run tools or enqueue
approvals on its own.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


def stable_id(*parts: str) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


#: Context kinds understood by the relevance / budget engines.
CONTEXT_KINDS = ("file", "symbol", "git", "test", "error", "metadata")

#: Per-kind budget buckets used by Context Budget 2.0 (bytes).
BUDGET_BY_KIND: dict[str, int] = {
    "code": 40 * 1024,
    "tests": 12 * 1024,
    "git": 8 * 1024,
    "metadata": 4 * 1024,
}
#: Global budget for one ranked context selection (bytes).
GLOBAL_CONTEXT_BUDGET = 64 * 1024

#: Priority order used when a budget must be trimmed (highest first).
KIND_PRIORITY = ("code", "tests", "git", "metadata")


@dataclass(frozen=True)
class ContextCandidate:
    """One selectable context unit (file / symbol / git / test / error)."""

    id: str
    kind: str  # file | symbol | git | test | error | metadata
    path: str
    name: str
    content: str
    size: int = 0
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "size", len(self.content.encode("utf-8")))

    @property
    def bucket(self) -> str:
        if self.kind in ("git", "metadata"):
            return "git" if self.kind == "git" else "metadata"
        if self.kind == "test":
            return "tests"
        return "code"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "path": self.path,
            "name": self.name,
            "size": self.size,
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class RankedContextItem:
    """A context candidate with its relevance score and explanation."""

    candidate: ContextCandidate
    score: float
    included: bool
    exclusion: str = ""  # "" | "budget" | "dedup" | "score"
    truncated: bool = False

    def as_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.candidate.id,
            "kind": self.candidate.kind,
            "path": self.candidate.path,
            "name": self.candidate.name,
            "score": self.score,
            "reason": "; ".join(self.candidate.reasons) if self.candidate.reasons else "Keyword / path relevance",
            "source": self.candidate.kind,
            "size": self.candidate.size,
            "included": self.included,
            "exclusion": self.exclusion,
            "truncated": self.truncated,
            "securityFiltered": True,
        }
        if include_content:
            data["content"] = self.candidate.content
        return data


@dataclass(frozen=True)
class BudgetUsage:
    bucket: str
    used: int
    limit: int
    items: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "used": self.used,
            "limit": self.limit,
            "remaining": self.remaining,
            "items": self.items,
        }


@dataclass(frozen=True)
class DedupReport:
    total_candidates: int
    unique: int
    dropped: int

    def as_dict(self) -> dict[str, Any]:
        return {"totalCandidates": self.total_candidates, "unique": self.unique, "dropped": self.dropped}


@dataclass(frozen=True)
class SuggestedContextResult:
    project: str
    agent: str
    query: str
    items: list[RankedContextItem]
    budget: list[BudgetUsage]
    dedup: DedupReport
    truncated: bool

    def as_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "agent": self.agent,
            "query": self.query,
            "items": [item.as_dict(include_content=include_content) for item in self.items],
            "budget": [usage.as_dict() for usage in self.budget],
            "dedup": self.dedup.as_dict(),
            "truncated": self.truncated,
            "securityFiltering": True,
            "readOnly": True,
        }


@dataclass(frozen=True)
class RelationshipNode:
    name: str
    kind: str
    file: str
    line: int
    direction: str  # caller | callee | import | reference | related

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "file": self.file, "line": self.line, "direction": self.direction}


@dataclass(frozen=True)
class RelationshipReport:
    project: str
    target: str
    imports: list[dict[str, Any]]
    importers: list[dict[str, Any]]
    callers: list[dict[str, Any]]
    callees: list[dict[str, Any]]
    references: list[dict[str, Any]]
    related_files: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "target": self.target,
            "imports": self.imports,
            "importers": self.importers,
            "callers": self.callers,
            "callees": self.callees,
            "references": self.references,
            "relatedFiles": self.related_files,
            "readOnly": True,
            "graphNotModified": True,
        }


@dataclass(frozen=True)
class ErrorContextBundle:
    project: str
    error: str
    kind: str  # python_exception | http_error | build_error | typescript_error | test_failure | generic
    source_location: dict[str, Any] | None
    related_files: list[str]
    related_symbols: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    recent_diff: list[str]
    relevant_tests: list[str]
    sanitized: bool
    absolute_paths_removed: bool
    secrets_redacted: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "error": self.error,
            "kind": self.kind,
            "sourceLocation": self.source_location,
            "relatedFiles": self.related_files,
            "relatedSymbols": self.related_symbols,
            "dependencies": self.dependencies,
            "recentDiff": self.recent_diff,
            "relevantTests": self.relevant_tests,
            "sanitized": self.sanitized,
            "absolutePathsRemoved": self.absolute_paths_removed,
            "secretsRedacted": self.secrets_redacted,
            "readOnly": True,
        }


@dataclass(frozen=True)
class TestFailureContext:
    project: str
    test: str
    failure: str
    expected: str
    actual: str
    test_file: str | None
    related_source: list[str]
    related_symbols: list[dict[str, Any]]
    suggested_investigation: list[str]
    patch_proposal_only: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "test": self.test,
            "failure": self.failure,
            "expected": self.expected,
            "actual": self.actual,
            "testFile": self.test_file,
            "relatedSource": self.related_source,
            "relatedSymbols": self.related_symbols,
            "suggestedInvestigation": self.suggested_investigation,
            "patchProposalOnly": self.patch_proposal_only,
            "readOnly": True,
        }


@dataclass(frozen=True)
class GitDiffAnalysis:
    project: str
    change_summary: list[str]
    changed_files: list[dict[str, Any]]
    changed_symbols: list[dict[str, Any]]
    affected_tests: list[str]
    affected_dependencies: list[str]
    risk_indicators: list[dict[str, Any]]
    review_points: list[str]
    stats: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "changeSummary": self.change_summary,
            "changedFiles": self.changed_files,
            "changedSymbols": self.changed_symbols,
            "affectedTests": self.affected_tests,
            "affectedDependencies": self.affected_dependencies,
            "riskIndicators": self.risk_indicators,
            "reviewPoints": self.review_points,
            "stats": self.stats,
            "readOnly": True,
            "noGitMutation": True,
        }


@dataclass(frozen=True)
class CodeReviewFinding:
    id: str
    severity: str  # Info | Low | Medium | High | Critical
    category: str
    location: str
    title: str
    explanation: str
    recommendation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "category": self.category,
            "location": self.location,
            "title": self.title,
            "explanation": self.explanation,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class CodeReviewResult:
    project: str
    target: str
    findings: list[CodeReviewFinding]
    summary: str
    patch_proposal_only: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "target": self.target,
            "summary": self.summary,
            "findings": [finding.as_dict() for finding in self.findings],
            "patchProposalOnly": self.patch_proposal_only,
            "readOnly": True,
        }


@dataclass(frozen=True)
class InjectionSignal:
    pattern: str
    severity: str  # info | warning | high
    snippet: str

    def as_dict(self) -> dict[str, Any]:
        return {"pattern": self.pattern, "severity": self.severity, "snippet": self.snippet}


@dataclass(frozen=True)
class InjectionReport:
    project: str
    trusted: str  # system | user
    untrusted: list[str]  # sources of untrusted project content
    signals: list[InjectionSignal]
    verdict: str  # clean | suspicious | untrusted_content_detected

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "trusted": self.trusted,
            "untrusted": self.untrusted,
            "signals": [signal.as_dict() for signal in self.signals],
            "verdict": self.verdict,
            "readOnly": True,
        }


@dataclass(frozen=True)
class PatchProposal:
    id: str
    project: str
    agent: str
    target_file: str
    target_symbol: str
    proposed_change: str
    reason: str
    expected_impact: str
    risk: str  # low | medium | high
    status: str  # proposed
    applied: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "agent": self.agent,
            "targetFile": self.target_file,
            "targetSymbol": self.target_symbol,
            "proposedChange": self.proposed_change,
            "reason": self.reason,
            "expectedImpact": self.expected_impact,
            "risk": self.risk,
            "status": self.status,
            "applied": self.applied,
            "readOnlyAnalysis": True,
            "requiresApproval": True,
        }


@dataclass(frozen=True)
class Phase30Snapshot:
    project: str
    suggested: SuggestedContextResult | None
    relationships: RelationshipReport | None
    error_bundle: ErrorContextBundle | None
    test_failure: TestFailureContext | None
    git_analysis: GitDiffAnalysis | None
    review: CodeReviewResult | None
    injection: InjectionReport | None
    budget: list[BudgetUsage]
    proposals: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev/intelligence",
            "project": self.project,
            "suggested": self.suggested.as_dict() if self.suggested else None,
            "relationships": self.relationships.as_dict() if self.relationships else None,
            "errorBundle": self.error_bundle.as_dict() if self.error_bundle else None,
            "testFailure": self.test_failure.as_dict() if self.test_failure else None,
            "gitAnalysis": self.git_analysis.as_dict() if self.git_analysis else None,
            "review": self.review.as_dict() if self.review else None,
            "injection": self.injection.as_dict() if self.injection else None,
            "budget": [usage.as_dict() for usage in self.budget],
            "proposals": self.proposals,
            "readOnly": True,
            "securityFiltering": True,
        }
