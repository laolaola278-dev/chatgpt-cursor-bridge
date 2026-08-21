"""Command policy security tests (14+ cases)."""

from __future__ import annotations

import pytest

from app.security.command_policy import CommandPolicyError, safe_environment, validate_command


@pytest.mark.parametrize(
    ("alias", "argv"),
    [
        ("pytest", ("pytest",)),
        ("npm test", ("npm", "test", "--")),
        ("cmake build", ("cmake", "--build", "build")),
        ("  NPM   TEST  ", ("npm", "test", "--")),
    ],
)
def test_allowed_commands_map_to_fixed_argv(alias: str, argv: tuple[str, ...]) -> None:
    assert validate_command(alias).argv == argv


@pytest.mark.parametrize(
    "command",
    [
        "pytest; rm -rf /",
        "pytest && whoami",
        "pytest || true",
        "pytest | cat",
        "pytest > out.txt",
        "pytest < input",
        "pytest `whoami`",
        "pytest $(whoami)",
        "pytest\nwhoami",
    ],
)
def test_shell_injection_is_rejected(command: str) -> None:
    with pytest.raises(CommandPolicyError):
        validate_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "bash script.sh",
        "./run.sh",
        "python script.py",
        "node test.js",
        "git status",
        "curl example.com",
        "pytest -k unit",
        "npm run build",
    ],
)
def test_non_whitelisted_commands_and_arguments_are_rejected(command: str) -> None:
    with pytest.raises(CommandPolicyError):
        validate_command(command)


@pytest.mark.parametrize(
    "command",
    ["PATH=/tmp pytest", "PYTHONPATH=. pytest", "NODE_OPTIONS=--require=x npm test", "LD_PRELOAD=x pytest"],
)
def test_environment_modification_is_rejected(command: str) -> None:
    with pytest.raises(CommandPolicyError):
        validate_command(command)


def test_empty_command_is_rejected() -> None:
    with pytest.raises(CommandPolicyError):
        validate_command("   ")


def test_safe_environment_drops_dangerous_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LD_PRELOAD", "/evil.so")
    monkeypatch.setenv("PYTHONPATH", "/evil")
    env = safe_environment()
    assert "LD_PRELOAD" not in env
    assert "PYTHONPATH" not in env
    assert env["CI"] == "1"
