"""Phase 30 · Context Intelligence Engine (facade).

Selects the most relevant read-only context for a user question using the
Phase 29 services, deterministic relevance scoring, deduplication and
Context Budget 2.0. Every selection carries explanations ("why this
context?"), source, size and filtering/truncation flags. Nothing here
executes, writes, or enqueues approvals.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.context.dev.budget import ContextBudget
from app.context.dev.bundle import ContextBundleEngine
from app.context.dev.git_context import GitContextService
from app.context.dev.security import is_sensitive_path, redact_secrets
from app.context.dev.symbols import SymbolContextService
from app.security.sandbox import get_project_dir, validate_path
from app.security.validator import ResourceNotFound

from .budget2 import ContextBudget2
from .code_review import CodeReviewAssistant
from .dedup import ContextDeduplicator
from .error_assistant import ErrorContextAssistant
from .git_intel import GitDiffIntelligence
from .index_source import ReadOnlyProjectIndex
from .injection import PromptInjectionGuard
from .models import (
    CodeReviewResult,
    ContextCandidate,
    ErrorContextBundle,
    GitDiffAnalysis,
    Phase30Snapshot,
    RankedContextItem,
    RelationshipReport,
    SuggestedContextResult,
    TestFailureContext,
)
from .proposal import PatchProposalGenerator, PatchProposalStore
from .relationships import RelationshipAnalyzer
from .scoring import ContextRelevanceScorer
from .test_failure import TestFailureAssistant

MAX_FILE_CANDIDATES = 200
SCORE_SNIPPET_BYTES = 4 * 1024


class ContextIntelligenceEngine:
    def __init__(self, settings: Settings, bundle_engine: ContextBundleEngine | None = None) -> None:
        self._settings = settings
        self._bundle = bundle_engine or ContextBundleEngine(settings)
        self._index = ReadOnlyProjectIndex(settings)
        self._symbols = SymbolContextService(settings)
        self._git = GitContextService(settings)
        self._scorer = ContextRelevanceScorer()
        self._dedup = ContextDeduplicator()
        self._budget = ContextBudget2()
        self._relationships = RelationshipAnalyzer(settings)
        self._error = ErrorContextAssistant(settings)
        self._test_failure = TestFailureAssistant(settings)
        self._git_intel = GitDiffIntelligence(settings)
        self._review = CodeReviewAssistant(settings)
        self._injection = PromptInjectionGuard()

    # -- candidate collection -------------------------------------------

    def _candidates(
        self,
        project: str,
        *,
        query: str,
        selected_path: str = "",
        selected_text: str = "",
        error_text: str = "",
        test_failure_text: str = "",
        diff_files: list[str] | None = None,
    ) -> list[ContextCandidate]:
        diff_set = [item for item in (diff_files or []) if not is_sensitive_path(item)]
        candidates: list[ContextCandidate] = []

        # Files (bounded content for scoring).
        try:
            from app.code_intelligence.scanner import CodeScanner

            scanner = CodeScanner(self._settings)
            for count, (path, relative) in enumerate(scanner.files(project)):
                if count >= MAX_FILE_CANDIDATES:
                    break
                if is_sensitive_path(relative):
                    continue
                try:
                    snippet = redact_secrets(path.read_bytes()[:SCORE_SNIPPET_BYTES].decode("utf-8", errors="replace"))
                except OSError:
                    snippet = ""
                candidates.append(
                    ContextCandidate(
                        id=f"file:{relative}",
                        kind="file",
                        path=relative,
                        name=relative.rsplit("/", 1)[-1],
                        content=snippet,
                        reasons=[],
                    )
                )
        except Exception:  # noqa: BLE001 - scanning degrades gracefully
            pass

        # Symbols.
        try:
            symbols = self._symbols.build(project, query=query, limit=200)
            for symbol in symbols["symbols"][:200]:
                candidates.append(
                    ContextCandidate(
                        id=f"symbol:{symbol['file']}:{symbol['name']}",
                        kind="symbol",
                        path=symbol["file"],
                        name=symbol["name"],
                        content=f"{symbol['type']} {symbol['signature']}",
                        reasons=[],
                    )
                )
        except Exception:  # noqa: BLE001
            pass

        # Git (changed files).
        try:
            git_payload = self._git.build(project, ContextBudget())
            for path in git_payload.get("changedFiles", [])[:50]:
                candidates.append(
                    ContextCandidate(
                        id=f"git:{path}",
                        kind="git",
                        path=path,
                        name=f"git diff: {path}",
                        content=f"changed file: {path}",
                        reasons=[],
                    )
                )
        except Exception:  # noqa: BLE001
            pass

        # Tests.
        try:
            for row in self._index.files(project):
                if "test" in row["path"].lower() or "spec" in row["path"].lower():
                    candidates.append(
                        ContextCandidate(
                            id=f"test:{row['path']}",
                            kind="test",
                            path=row["path"],
                            name=row["path"].rsplit("/", 1)[-1],
                            content=f"test file: {row['path']}",
                            reasons=[],
                        )
                    )
        except Exception:  # noqa: BLE001
            pass

        # Metadata (project profile summary).
        try:
            project_ctx = self._bundle.project_context(project, ContextBudget())
            git_meta = self._git.build(project, ContextBudget())
            summary = (
                f"project {project}: {project_ctx['fileCount']} files, "
                f"{', '.join(project_ctx['languages'].keys())} languages, "
                f"branch {git_meta.get('branch', 'N/A')}"
            )
            candidates.append(
                ContextCandidate(
                    id="metadata:project",
                    kind="metadata",
                    path="",
                    name="Project summary",
                    content=summary,
                    reasons=[],
                )
            )
        except Exception:  # noqa: BLE001
            pass

        # Score every candidate (explanations for the UI).
        scored: list[ContextCandidate] = []
        for candidate in candidates:
            score, reasons = self._scorer.score(
                candidate,
                query=query,
                selected_path=selected_path,
                selected_text=selected_text,
                error_text=error_text,
                test_failure_text=test_failure_text,
                diff_files=diff_set,
            )
            candidate = ContextCandidate(
                id=candidate.id,
                kind=candidate.kind,
                path=candidate.path,
                name=candidate.name,
                content=candidate.content,
                reasons=reasons,
            )
            if score > 0 or not query:
                scored.append(candidate)

        scored.sort(key=lambda item: (-len(item.reasons), item.path))
        return scored

    # -- public analysis ------------------------------------------------

    def suggest(
        self,
        project: str,
        *,
        query: str = "",
        agent: str = "ASSISTANT",
        selected_path: str = "",
        selected_text: str = "",
        error: str = "",
        test_failure: str = "",
        limit: int = 40,
    ) -> SuggestedContextResult:
        candidates = self._candidates(
            project,
            query=query,
            selected_path=selected_path,
            selected_text=selected_text,
            error_text=error,
            test_failure_text=test_failure,
        )
        unique, dedup = self._dedup.deduplicate(candidates)
        included, excluded, truncated = self._budget.select(unique)

        included_ids = {item.id for item in included}
        items: list[RankedContextItem] = []
        for candidate in unique[: max(limit, len(included))]:
            score, _ = self._scorer.score(
                candidate,
                query=query,
                selected_path=selected_path,
                selected_text=selected_text,
                error_text=error,
                test_failure_text=test_failure,
            )
            if candidate.id in included_ids:
                items.append(RankedContextItem(candidate=candidate, score=score, included=True))
            elif candidate in excluded:
                items.append(RankedContextItem(candidate=candidate, score=score, included=False, exclusion="budget"))
            else:
                items.append(RankedContextItem(candidate=candidate, score=score, included=False, exclusion="score"))

        items.sort(key=lambda item: (-item.score, item.candidate.path))
        return SuggestedContextResult(
            project=project,
            agent=agent,
            query=query,
            items=items[:limit],
            budget=self._budget.usage(),
            dedup=dedup,
            truncated=truncated or any(not item.included for item in items),
        )

    def snapshot(self, project: str) -> Phase30Snapshot:
        git_analysis: GitDiffAnalysis | None = None
        review: CodeReviewResult | None = None
        try:
            git_analysis = self._git_intel.analyze(project)
            git_payload = self._git.build(project, ContextBudget())
            changed = git_payload.get("changedFiles") or []
            if changed and not is_sensitive_path(changed[0]):
                review = self._review.review(project, file=changed[0])
        except ResourceNotFound:
            git_analysis = GitDiffAnalysis(
                project=project, change_summary=[], changed_files=[], changed_symbols=[],
                affected_tests=[], affected_dependencies=[], risk_indicators=[], review_points=[],
                stats={"files": 0, "added": 0, "removed": 0, "symbols": 0, "tests": 0},
            )
        except Exception:  # noqa: BLE001 - snapshot degrades gracefully
            pass
        injection = self._injection.detect("project content loaded", source="project_content")
        proposals = []
        try:
            store = PatchProposalStore(self._proposal_db_path())
            proposals = store.list(project)
        except Exception:  # noqa: BLE001
            proposals = []
        return Phase30Snapshot(
            project=project,
            suggested=None,
            relationships=None,
            error_bundle=None,
            test_failure=None,
            git_analysis=git_analysis,
            review=review,
            injection=injection,
            budget=self._budget.usage(),
            proposals=proposals,
        )

    def _proposal_db_path(self) -> str:
        return str(self._settings.workspace_root.parent / "context_dev" / "proposals.db")

    # -- delegated engines ----------------------------------------------

    def relationships(self, project: str, *, file: str | None = None, symbol: str | None = None):
        try:
            return self._relationships.analyze(project, file=file, symbol=symbol)
        except ResourceNotFound:
            return RelationshipReport(project=project, target=symbol or file or "", imports=[], importers=[], callers=[], callees=[], references=[], related_files=[])

    def error_bundle(self, project: str, *, error: str, stack_trace: str = "", test_failure: str = "", file: str | None = None):
        try:
            return self._error.build(project, error=error, stack_trace=stack_trace, test_failure=test_failure, file=file)
        except ResourceNotFound:
            cleaned = redact_secrets(error)[:4000]
            return ErrorContextBundle(
                project=project, error=cleaned, kind="generic", source_location=None,
                related_files=[], related_symbols=[], dependencies=[], recent_diff=[],
                relevant_tests=[], sanitized=True, absolute_paths_removed=False,
                secrets_redacted=cleaned != error,
            )

    def test_failure(self, project: str, *, test: str, failure: str = "", expected: str = "", actual: str = "", traceback: str = ""):
        try:
            return self._test_failure.build(project, test=test, failure=failure, expected=expected, actual=actual, traceback=traceback)
        except ResourceNotFound:
            return TestFailureContext(
                project=project, test=redact_secrets(test)[:1000], failure=redact_secrets(failure)[:4000],
                expected=redact_secrets(expected)[:2000], actual=redact_secrets(actual)[:2000],
                test_file=None, related_source=[], related_symbols=[],
                suggested_investigation=["Project not found; no test context available."], patch_proposal_only=True,
            )

    def git_intel(self, project: str):
        try:
            return self._git_intel.analyze(project)
        except ResourceNotFound:
            return GitDiffAnalysis(
                project=project, change_summary=[], changed_files=[], changed_symbols=[],
                affected_tests=[], affected_dependencies=[], risk_indicators=[], review_points=[],
                stats={"files": 0, "added": 0, "removed": 0, "symbols": 0, "tests": 0},
            )

    def review(self, project: str, *, file: str | None = None, symbol: str | None = None, selection: str = "", diff: str = ""):
        try:
            return self._review.review(project, file=file, symbol=symbol, selection=selection, diff=diff)
        except ResourceNotFound:
            return CodeReviewResult(project=project, target=file or symbol or "selection", findings=[], summary="No review context available.", patch_proposal_only=True)

    def injection(self, project: str, *, text: str, source: str = "project_content"):
        return self._injection.detect(text, source=source)

    def patch_proposal(
        self,
        *,
        project: str,
        target_file: str,
        target_symbol: str,
        proposed_change: str,
        reason: str,
        expected_impact: str,
        risk: str,
        agent: str = "ASSISTANT",
    ):
        return PatchProposalGenerator().build(
            project=project,
            target_file=target_file,
            target_symbol=target_symbol,
            proposed_change=proposed_change,
            reason=reason,
            expected_impact=expected_impact,
            risk=risk,
            agent=agent,
        )

    def patch_proposal_store(self) -> PatchProposalStore:
        return PatchProposalStore(self._proposal_db_path())
