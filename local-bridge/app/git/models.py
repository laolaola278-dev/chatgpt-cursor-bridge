"""Git integration models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GitStatus:
    branch: str
    modified: tuple[str, ...]
    untracked: tuple[str, ...]
    staged: tuple[str, ...]
    clean: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "modifiedFiles": list(self.modified),
            "untrackedFiles": list(self.untracked),
            "stagedFiles": list(self.staged),
            "clean": self.clean,
        }


@dataclass(frozen=True)
class GitCommitResult:
    commit: str
    branch: str
    message: str
    files: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "commit": self.commit,
            "branch": self.branch,
            "message": self.message,
            "files": list(self.files),
            "size": len(self.files),
        }
