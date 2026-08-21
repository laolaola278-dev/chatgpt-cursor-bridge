"""Safe Git operations using fixed subprocess argv and project sandbox cwd."""

from __future__ import annotations

import subprocess
from typing import Any, Callable

from app.config import Settings
from app.security.sandbox import get_project_dir
from app.security.validator import ResourceConflict, ValidationFailed

from .diff import limit_git_output
from .models import GitCommitResult, GitStatus
from .policy import validate_commit_message

RunText = Callable[..., subprocess.CompletedProcess[str]]


class GitManager:
    def __init__(self, settings: Settings, *, run_function: RunText = subprocess.run) -> None:
        self._settings = settings
        self._run = run_function

    def _git(self, project: str, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        cwd = get_project_dir(project, self._settings)
        result = self._run(
            ["git", *args],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            check=False,
            timeout=30,
        )
        if check and result.returncode != 0:
            message = (result.stderr or result.stdout or "Git operation failed").strip()
            if "not a git repository" in message.lower():
                raise ValidationFailed(f"Project '{project}' is not a Git repository")
            raise ValidationFailed(message[:1000])
        return result

    def status(self, project: str) -> GitStatus:
        branch_result = self._git(project, ["branch", "--show-current"])
        status_result = self._git(project, ["status", "--porcelain=v1", "-uall"])
        modified: list[str] = []
        untracked: list[str] = []
        staged: list[str] = []
        for line in status_result.stdout.splitlines():
            if len(line) < 4:
                continue
            x, y = line[0], line[1]
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if x == "?" and y == "?":
                untracked.append(path)
                continue
            if x != " ":
                staged.append(path)
            if y != " ":
                modified.append(path)
        return GitStatus(
            branch=branch_result.stdout.strip() or "DETACHED",
            modified=tuple(sorted(set(modified))),
            untracked=tuple(sorted(set(untracked))),
            staged=tuple(sorted(set(staged))),
            clean=not (modified or untracked or staged),
        )

    def diff(self, project: str, *, staged: bool = False) -> dict[str, Any]:
        args = ["diff", "--no-ext-diff", "--binary"]
        if staged:
            args.append("--cached")
        result = self._git(project, args)
        text, truncated = limit_git_output(result.stdout.encode("utf-8"))
        return {"diff": text, "staged": staged, "truncated": truncated, "size": len(text.encode("utf-8"))}

    def preview_commit(self, project: str, message: str) -> dict[str, Any]:
        clean_message = validate_commit_message(message)
        status = self.status(project)
        diff = self.diff(project)
        if status.clean:
            raise ResourceConflict("Working tree is clean; nothing to commit")
        return {
            "message": clean_message,
            "status": status.as_dict(),
            "diff": diff["diff"],
            "diffTruncated": diff["truncated"],
        }

    def commit(self, project: str, message: str) -> GitCommitResult:
        clean_message = validate_commit_message(message)
        before = self.status(project)
        if before.clean:
            raise ResourceConflict("Working tree is clean; nothing to commit")
        self._git(project, ["add", "--all"])
        self._git(project, ["commit", "--message", clean_message])
        commit_hash = self._git(project, ["rev-parse", "HEAD"]).stdout.strip()
        branch = self._git(project, ["branch", "--show-current"]).stdout.strip() or "DETACHED"
        files = tuple(sorted(set(before.modified + before.untracked + before.staged)))
        return GitCommitResult(commit_hash, branch, clean_message, files)
