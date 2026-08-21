"""Read-only Git context for developer context bundles.

Uses the existing ``GitManager`` for status and diff. Recent commit history
is read through the same fixed-argv sandboxed git invocation. This module
never stages, commits, pushes or mutates the working tree.
"""

from __future__ import annotations

import subprocess
from typing import Any

from app.config import Settings
from app.git.manager import GitManager
from app.security.sandbox import get_project_dir
from app.security.validator import BridgeError, ValidationFailed

from .budget import ContextBudget, truncate_bytes
from .security import is_sensitive_path, redact_secrets


class GitContextService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._git = GitManager(settings)

    def build(self, project: str, budget: ContextBudget) -> dict[str, Any]:
        try:
            status = self._git.status(project)
            diff = self._git.diff(project)
            commits = self._recent_commits(project, budget.max_commits)
        except (BridgeError, ValidationFailed):
            # Not every project is a Git repository; the context degrades
            # gracefully instead of failing the whole bundle.
            return {
                "branch": "N/A",
                "clean": True,
                "changedFiles": [],
                "untracked": [],
                "staged": [],
                "diff": "",
                "diffTruncated": False,
                "commits": [],
                "notAGitRepository": True,
                "securityFiltered": True,
            }
        diff_text, diff_truncated = truncate_bytes(diff["diff"], budget.max_diff_bytes)
        # Redact any secret-looking values that may appear in diff text.
        diff_text = redact_secrets(diff_text)
        changed = [
            path
            for path in sorted(set(status.modified) | set(status.staged))
            if not is_sensitive_path(path)
        ]
        untracked = [path for path in status.untracked if not is_sensitive_path(path)]
        staged = [path for path in status.staged if not is_sensitive_path(path)]
        return {
            "branch": status.branch,
            "clean": status.clean,
            "changedFiles": changed,
            "untracked": untracked,
            "staged": staged,
            "diff": diff_text,
            "diffTruncated": diff_truncated,
            "commits": commits,
            "securityFiltered": True,
        }

    def _recent_commits(self, project: str, limit: int) -> list[dict[str, Any]]:
        cwd = get_project_dir(project, self._settings)
        try:
            result = subprocess.run(
                ["git", "log", "--pretty=format:%h|%s|%an|%aI", "-n", str(limit)],
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0:
            return []
        commits: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            short_hash, subject, author, authored_at = parts
            commits.append(
                {
                    "hash": short_hash,
                    "subject": redact_secrets(subject)[:200],
                    "author": author[:100],
                    "authoredAt": authored_at,
                }
            )
        return commits
