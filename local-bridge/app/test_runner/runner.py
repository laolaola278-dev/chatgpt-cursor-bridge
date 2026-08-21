"""Sandboxed test runner using fixed argv and ``shell=False``."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from app.config import Settings
from app.security.command_policy import CommandSpec, safe_environment, validate_command
from app.security.sandbox import get_project_dir

from .models import TestRunResult
from .policy import clamp_timeout, truncate_output

RunFunction = Callable[..., subprocess.CompletedProcess[bytes]]


class TestRunner:
    __test__ = False  # Prevent pytest from treating this service class as a test.

    def __init__(
        self,
        settings: Settings,
        *,
        run_function: RunFunction = subprocess.run,
    ) -> None:
        self._settings = settings
        self._run = run_function

    def preview(self, project: str, command: str) -> dict[str, object]:
        spec = validate_command(command)
        cwd = get_project_dir(project, self._settings)
        return {
            "command": spec.alias,
            "argv": list(spec.argv),
            "cwd": str(cwd),
            "timeoutSeconds": self._settings.test_timeout_seconds,
            "maxOutputBytes": self._settings.test_max_output_bytes,
            "description": spec.description,
        }

    def execute(self, project: str, command: str) -> TestRunResult:
        spec = validate_command(command)
        cwd = get_project_dir(project, self._settings)
        return self._execute_spec(spec, cwd)

    def _execute_spec(self, spec: CommandSpec, cwd: Path) -> TestRunResult:
        started = time.monotonic()
        try:
            completed = self._run(
                list(spec.argv),
                cwd=str(cwd),
                env=safe_environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=clamp_timeout(
                    self._settings.test_timeout_seconds,
                    self._settings.test_timeout_seconds,
                ),
                shell=False,
                check=False,
            )
            stdout_raw = completed.stdout or b""
            stderr_raw = completed.stderr or b""
            exit_code: int | None = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout_raw = exc.stdout or b""
            stderr_raw = (exc.stderr or b"") + b"\nTest command timed out."
            exit_code = None
            timed_out = True

        # Apply the output budget across stdout and stderr together.
        stdout, out_cut = truncate_output(stdout_raw, self._settings.test_max_output_bytes)
        remaining = max(0, self._settings.test_max_output_bytes - len(stdout.encode("utf-8")))
        stderr, err_cut = truncate_output(stderr_raw, remaining)
        duration_ms = int((time.monotonic() - started) * 1000)
        return TestRunResult(
            command=spec.alias,
            argv=spec.argv,
            cwd=str(cwd),
            exit_code=exit_code,
            passed=exit_code == 0 and not timed_out,
            timed_out=timed_out,
            duration_ms=duration_ms,
            stdout=stdout,
            stderr=stderr,
            output_truncated=out_cut or err_cut,
        )
