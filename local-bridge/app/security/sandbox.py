"""Filesystem sandbox.

Every file operation must go through :func:`validate_path`. The sandbox
guarantees that:

* project names cannot contain path separators or traversal segments;
* relative paths cannot escape the project directory (``../../secret.txt``);
* absolute paths are rejected;
* symlinks that resolve outside of the workspace root are rejected.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from app.config import Settings
from app.security.validator import BridgeError, ResourceNotFound, ValidationFailed

PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


class SandboxViolation(BridgeError):
    """Raised when a path escapes the sandbox or is otherwise unsafe."""

    status_code = 403
    code = "sandbox_violation"


def _real(path: Path) -> Path:
    return Path(os.path.realpath(str(path)))


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def workspace_root(settings: Settings) -> Path:
    root = _real(settings.workspace_root)
    if not root.is_dir():
        raise SandboxViolation(f"Workspace root does not exist: {settings.workspace_root}")
    return root


def validate_project_name(project: str) -> str:
    cleaned = (project or "").strip()
    if not cleaned:
        raise ValidationFailed("Field 'project' must not be empty")
    if not PROJECT_NAME_PATTERN.match(cleaned):
        raise SandboxViolation(f"Invalid project name: {project!r}")
    if cleaned in {".", ".."}:
        raise SandboxViolation(f"Invalid project name: {project!r}")
    return cleaned


def get_project_dir(project: str, settings: Settings) -> Path:
    """Resolve and validate a project directory inside the workspace root."""
    name = validate_project_name(project)
    root = workspace_root(settings)
    candidate = _real(root / name)
    if not _is_within(candidate, root):
        raise SandboxViolation(f"Project '{name}' resolves outside of the workspace root")
    if not candidate.is_dir():
        raise ResourceNotFound(f"Project '{name}' was not found in the workspace")
    return candidate


def memory_root(settings: Settings) -> Path:
    """Resolve the memory root, creating it on first use."""
    settings.memory_root.mkdir(parents=True, exist_ok=True)
    root = _real(settings.memory_root)
    if not root.is_dir():
        raise SandboxViolation(f"Memory root does not exist: {settings.memory_root}")
    return root


def get_memory_dir(project: str, settings: Settings, *, create: bool = False) -> Path:
    """Resolve `<MEMORY_ROOT>/<project>/`, isolated per project.

    Project A can never resolve into project B's memory directory because the
    name is pattern-validated and the realpath must stay inside the project's
    own memory folder.
    """
    name = validate_project_name(project)
    root = memory_root(settings)
    candidate = root / name

    if create:
        candidate.mkdir(parents=True, exist_ok=True)

    resolved = _real(candidate)
    if not _is_within(resolved, root):
        raise SandboxViolation(f"Memory directory for '{name}' escapes the memory root")
    if not resolved.is_dir():
        raise ResourceNotFound(f"Memory for project '{name}' has not been initialised")
    return resolved


def validate_memory_path(
    project: str,
    document: str,
    settings: Settings,
    *,
    create_dir: bool = False,
) -> Path:
    """Validate a memory document path and return its safe absolute path."""
    memory_dir = get_memory_dir(project, settings, create=create_dir)
    relative = normalize_relative_path(document)

    if len(relative.parts) != 1:
        raise SandboxViolation("Memory documents must be flat file names")

    literal_target = memory_dir / relative.parts[0]
    if literal_target.is_symlink() and not _is_within(_real(literal_target), memory_dir):
        raise SandboxViolation("Symlink escapes the memory sandbox")

    resolved = _real(literal_target)
    if not _is_within(resolved, memory_dir):
        raise SandboxViolation("Resolved memory path escapes the project memory sandbox")
    if not _is_within(resolved, memory_root(settings)):
        raise SandboxViolation("Resolved memory path escapes the memory root")
    return resolved


def normalize_relative_path(relative_path: str) -> PurePosixPath:
    raw = (relative_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValidationFailed("Field 'path' must not be empty")
    if raw.startswith("/") or WINDOWS_DRIVE_PATTERN.match(raw):
        raise SandboxViolation("Absolute paths are not allowed")
    if "\x00" in raw:
        raise SandboxViolation("Path contains a null byte")

    parts: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise SandboxViolation("Path traversal ('..') is not allowed")
        parts.append(part)

    if not parts:
        raise ValidationFailed("Field 'path' must point to a file")
    return PurePosixPath(*parts)


def _assert_no_symlink_escape(project_dir: Path, target: Path) -> None:
    """Walk each existing ancestor and make sure symlinks stay in the sandbox."""
    current = project_dir
    for part in target.relative_to(project_dir).parts if _is_within(target, project_dir) else ():
        current = current / part
        if not current.exists() and not current.is_symlink():
            return
        if current.is_symlink() and not _is_within(_real(current), project_dir):
            raise SandboxViolation(f"Symlink escapes the sandbox: {part}")


def validate_path(
    project: str,
    relative_path: str,
    settings: Settings,
    *,
    must_exist: bool = False,
    must_be_file: bool = True,
) -> Path:
    """Validate ``project``/``relative_path`` and return the safe absolute path."""
    project_dir = get_project_dir(project, settings)
    relative = normalize_relative_path(relative_path)

    literal_target = project_dir / Path(*relative.parts)
    _assert_no_symlink_escape(project_dir, literal_target)

    resolved = _real(literal_target)
    if not _is_within(resolved, project_dir):
        raise SandboxViolation("Resolved path escapes the project sandbox")
    if not _is_within(resolved, workspace_root(settings)):
        raise SandboxViolation("Resolved path escapes the workspace root")

    if must_exist:
        if not resolved.exists():
            raise ResourceNotFound(f"File not found: {relative}")
        if must_be_file and not resolved.is_file():
            raise ValidationFailed(f"Path is not a regular file: {relative}")

    return resolved


def relative_display(project: str, relative_path: str) -> str:
    """Human friendly identifier used inside audit logs."""
    return f"{project}:{relative_path}"
