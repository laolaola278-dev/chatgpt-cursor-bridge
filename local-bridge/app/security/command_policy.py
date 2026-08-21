"""Strict command allow-list for engineering tools.

Callers submit one exact command alias. We map it to a fixed argv tuple; user
input is never interpolated into a shell command and ``shell=True`` is never
used.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from app.security.validator import ValidationFailed

FORBIDDEN_TOKENS = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n", "\r")
ENV_ASSIGNMENT = re.compile(r"(?:^|\s)(?:PATH|PYTHONPATH|NODE_OPTIONS|LD_PRELOAD)\s*=", re.I)


@dataclass(frozen=True)
class CommandSpec:
    alias: str
    argv: tuple[str, ...]
    description: str


ALLOWED_COMMANDS: dict[str, CommandSpec] = {
    "pytest": CommandSpec("pytest", ("pytest",), "Run the Python test suite"),
    "npm test": CommandSpec("npm test", ("npm", "test", "--"), "Run the npm test script"),
    "cmake build": CommandSpec(
        "cmake build", ("cmake", "--build", "build"), "Build the configured CMake project"
    ),
}


class CommandPolicyError(ValidationFailed):
    code = "command_policy_violation"


def validate_command(command: str) -> CommandSpec:
    """Return the fixed command spec or reject the input."""
    raw = command or ""
    if not raw.strip():
        raise CommandPolicyError("Command must not be empty")
    if any(token in raw for token in FORBIDDEN_TOKENS):
        raise CommandPolicyError("Shell operators and redirections are forbidden")
    if ENV_ASSIGNMENT.search(raw):
        raise CommandPolicyError("Environment modification is forbidden")
    if raw.strip().lower().endswith((".sh", ".bash", ".zsh", ".cmd", ".bat", ".ps1")):
        raise CommandPolicyError("Arbitrary shell scripts are forbidden")

    normalized = " ".join(raw.strip().split()).lower()
    spec = ALLOWED_COMMANDS.get(normalized)
    if spec is None:
        allowed = ", ".join(ALLOWED_COMMANDS)
        raise CommandPolicyError(f"Command is not allowed. Allowed commands: {allowed}")
    return spec


def safe_environment() -> dict[str, str]:
    """Create a minimal inherited environment without dangerous injection vars."""
    allowed = ("PATH", "HOME", "USER", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["CI"] = "1"
    env["NO_COLOR"] = "1"
    return env
