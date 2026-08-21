"""Test runner data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TestRunResult:
    command: str
    argv: tuple[str, ...]
    cwd: str
    exit_code: int | None
    passed: bool
    timed_out: bool
    duration_ms: int
    stdout: str
    stderr: str
    output_truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exitCode": self.exit_code,
            "passed": self.passed,
            "timedOut": self.timed_out,
            "durationMs": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "outputTruncated": self.output_truncated,
            "size": len(self.stdout.encode("utf-8")) + len(self.stderr.encode("utf-8")),
        }
