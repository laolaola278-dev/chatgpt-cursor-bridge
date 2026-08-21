"""Data models for developer context bundles (Phase 29).

All structures are read-only snapshots assembled by ``ContextBundleEngine``.
They never reference absolute filesystem paths and never carry secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DevProjectContext:
    project: str
    workspace_root: str  # relative display only, e.g. "projects/<name>"
    languages: dict[str, int]
    file_count: int
    package_managers: list[str]
    git: dict[str, Any]
    test_status: dict[str, Any] | None
    build_status: dict[str, Any] | None
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "workspaceRoot": self.workspace_root,
            "languages": self.languages,
            "fileCount": self.file_count,
            "packageManagers": self.package_managers,
            "git": self.git,
            "testStatus": self.test_status,
            "buildStatus": self.build_status,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class DevFileContext:
    path: str
    language: str
    size: int
    lines: int
    content: str
    truncated: bool
    symbols: list[dict[str, Any]] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exported: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "size": self.size,
            "lines": self.lines,
            "content": self.content,
            "truncated": self.truncated,
            "symbols": self.symbols,
            "imports": self.imports,
            "exported": self.exported,
        }


@dataclass(frozen=True)
class DevSymbolContext:
    symbols: list[dict[str, Any]]
    total: int
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {"symbols": self.symbols, "total": self.total, "truncated": self.truncated}


@dataclass(frozen=True)
class DevDependencyContext:
    dependencies: list[dict[str, Any]]
    total: int
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {"dependencies": self.dependencies, "total": self.total, "truncated": self.truncated}


@dataclass(frozen=True)
class DevGitContext:
    branch: str
    clean: bool
    changed_files: list[str]
    untracked: list[str]
    staged: list[str]
    diff: str
    diff_truncated: bool
    commits: list[dict[str, Any]]
    security_filtered: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "clean": self.clean,
            "changedFiles": self.changed_files,
            "untracked": self.untracked,
            "staged": self.staged,
            "diff": self.diff,
            "diffTruncated": self.diff_truncated,
            "commits": self.commits,
            "securityFiltered": self.security_filtered,
        }


@dataclass(frozen=True)
class DevTestBuildContext:
    test_status: dict[str, Any] | None
    build_status: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {"testStatus": self.test_status, "buildStatus": self.build_status}


@dataclass(frozen=True)
class DevContextBundle:
    project: str
    agent: str
    generated_at: str
    project_context: DevProjectContext
    files: list[dict[str, Any]]
    symbols: DevSymbolContext
    dependencies: DevDependencyContext
    git: DevGitContext
    tests: DevTestBuildContext
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": "context/dev",
            "project": self.project,
            "agent": self.agent,
            "generatedAt": self.generated_at,
            "truncated": self.truncated,
            "securityFiltering": True,
            "projectContext": self.project_context.as_dict(),
            "files": self.files,
            "symbols": self.symbols.as_dict(),
            "dependencies": self.dependencies.as_dict(),
            "git": self.git.as_dict(),
            "tests": self.tests.as_dict(),
        }
