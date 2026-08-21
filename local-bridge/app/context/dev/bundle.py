"""Developer context bundle engine (Phase 29).

Assembles project / file / symbol / dependency / git / test context into one
read-only bundle. Every read is bounded by a ``ContextBudget`` and filtered by
:mod:`app.context.dev.security`. The engine never writes project files, never
executes anything and never touches secret material.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.code_intelligence.parser import language_for
from app.code_intelligence.scanner import CodeScanner
from app.config import Settings
from app.security.sandbox import get_project_dir, validate_path
from app.workflow.manager import WorkflowManager

from .budget import ContextBudget, budget_report
from .dependencies import DependencyContextService
from .git_context import GitContextService
from .models import DevContextBundle, DevDependencyContext, DevFileContext, DevGitContext, DevProjectContext, DevSymbolContext, DevTestBuildContext
from .security import is_sensitive_path, redact_secrets
from .symbols import SymbolContextService
from .tests import TestBuildContextService


class ContextBundleEngine:
    def __init__(self, settings: Settings, workflow_manager: WorkflowManager | None = None) -> None:
        self._settings = settings
        self._workflows = workflow_manager
        self._scanner = CodeScanner(settings)
        self._symbols = SymbolContextService(settings)
        self._deps = DependencyContextService(settings)
        self._git = GitContextService(settings)
        self._tests = TestBuildContextService(settings, workflow_manager) if workflow_manager else None

    # -- pieces ---------------------------------------------------------

    def project_context(self, project: str, budget: ContextBudget) -> dict[str, Any]:
        root = get_project_dir(project, self._settings)
        languages: Counter[str] = Counter()
        file_count = 0
        for _path, relative in self._scanner.files(project):
            file_count += 1
            languages[language_for(Path(relative))] += 1
        dependency_ctx = self._deps.build(project, budget)
        managers = sorted({manager for manifest in dependency_ctx.get("manifests", []) for manager in manifest.get("managers", [])})
        git = self._git.build(project, budget)
        tests = self._tests.build(project) if self._tests else {"testStatus": None, "buildStatus": None}
        return DevProjectContext(
            project=project,
            workspace_root=f"projects/{project}",
            languages=dict(languages.most_common()),
            file_count=file_count,
            package_managers=managers,
            git=git,
            test_status=tests.get("testStatus"),
            build_status=tests.get("buildStatus"),
            truncated=False,
        ).as_dict()

    def files(self, project: str, budget: ContextBudget) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        truncated = False
        for path, relative in self._scanner.files(project):
            if is_sensitive_path(relative):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            entries.append({"path": relative, "language": language_for(path), "size": size})
            if len(entries) >= budget.max_files:
                truncated = True
                break
        return {"files": entries, "total": len(entries), "truncated": truncated}

    def file(self, project: str, path: str, budget: ContextBudget) -> DevFileContext:
        if is_sensitive_path(path):
            raise PermissionError(f"Sensitive path is not available in developer context: {path}")
        target = validate_path(project, path, self._settings, must_exist=True)
        raw = target.read_bytes()
        truncated = len(raw) > budget.max_file_bytes
        content = raw[: budget.max_file_bytes].decode("utf-8", errors="replace")
        if truncated:
            content += "\n... [file truncated]"
        content = redact_secrets(content)
        lines = content.count("\n") + 1
        file_info = self._symbols.file_symbols(project, path)
        return DevFileContext(
            path=path,
            language=language_for(target),
            size=len(raw),
            lines=lines,
            content=content,
            truncated=truncated,
            symbols=file_info["symbols"],
            imports=file_info["imports"],
            exported=file_info["exported"],
        )

    def symbols(self, project: str, *, query: str = "", limit: int | None = None, budget: ContextBudget | None = None) -> DevSymbolContext:
        budget = budget or ContextBudget()
        payload = self._symbols.build(project, query=query, limit=limit, budget=budget)
        return DevSymbolContext(payload["symbols"], payload["total"], payload["truncated"])

    def symbol(self, project: str, symbol_id: str) -> dict[str, Any] | None:
        return self._symbols.get(project, symbol_id)

    def dependencies(self, project: str, budget: ContextBudget) -> DevDependencyContext:
        payload = self._deps.build(project, budget)
        return DevDependencyContext(payload["dependencies"], payload["total"], payload["truncated"])

    def git(self, project: str, budget: ContextBudget) -> DevGitContext:
        payload = self._git.build(project, budget)
        return DevGitContext(
            branch=payload["branch"],
            clean=payload["clean"],
            changed_files=payload["changedFiles"],
            untracked=payload["untracked"],
            staged=payload["staged"],
            diff=payload["diff"],
            diff_truncated=payload["diffTruncated"],
            commits=payload["commits"],
        )

    def tests(self, project: str) -> DevTestBuildContext:
        payload = self._tests.build(project) if self._tests else {"testStatus": None, "buildStatus": None}
        return DevTestBuildContext(payload.get("testStatus"), payload.get("buildStatus"))

    # -- bundle ---------------------------------------------------------

    def bundle(self, project: str, agent: str, budget: ContextBudget | None = None) -> dict[str, Any]:
        budget = budget or ContextBudget()
        project_ctx = self.project_context(project, budget)
        files = self.files(project, budget)
        symbols = self.symbols(project, budget=budget)
        dependencies = self.dependencies(project, budget)
        git = self.git(project, budget)
        tests = self.tests(project)
        bundle = DevContextBundle(
            project=project,
            agent=agent,
            generated_at="",
            project_context=DevProjectContext(
                project=project_ctx["project"],
                workspace_root=project_ctx["workspaceRoot"],
                languages=project_ctx["languages"],
                file_count=project_ctx["fileCount"],
                package_managers=project_ctx["packageManagers"],
                git=project_ctx["git"],
                test_status=project_ctx["testStatus"],
                build_status=project_ctx["buildStatus"],
                truncated=project_ctx["truncated"],
            ),
            files=files["files"],
            symbols=symbols,
            dependencies=dependencies,
            git=git,
            tests=tests,
            truncated=files["truncated"] or symbols.truncated or dependencies.truncated or git.diff_truncated,
        )
        import json
        from datetime import datetime, timezone

        bundle_dict = bundle.as_dict()
        bundle_dict["contextType"] = "bundle"
        bundle_dict["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        encoded = json.dumps(bundle_dict, ensure_ascii=False, default=str).encode("utf-8")
        bundle_dict["size"] = len(encoded)
        bundle_dict["truncated"] = bundle_dict["truncated"] or len(encoded) > budget.max_bundle_bytes
        return bundle_dict
