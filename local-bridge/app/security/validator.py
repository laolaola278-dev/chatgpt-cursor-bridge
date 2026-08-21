"""Shared error types and input validators for the bridge."""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

REQUEST_ID_PATTERN = re.compile(r"^req_[0-9a-f]{12,32}$")
MAX_PATCH_BYTES = 1024 * 1024


class BridgeError(Exception):
    """Base error carrying an HTTP status code and a machine readable code."""

    status_code: int = 400
    code: str = "bridge_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationFailed(BridgeError):
    status_code = 400
    code = "validation_failed"


class ResourceNotFound(BridgeError):
    status_code = 404
    code = "not_found"


class ResourceConflict(BridgeError):
    status_code = 409
    code = "conflict"


class PayloadTooLarge(BridgeError):
    status_code = 413
    code = "payload_too_large"


class ApprovalError(BridgeError):
    status_code = 400
    code = "approval_error"


def ensure_non_empty(value: str, field: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationFailed(f"Field '{field}' must not be empty")
    return cleaned


def ensure_file_size(size_bytes: int, settings: Settings, *, what: str = "File") -> None:
    if size_bytes > settings.max_file_size_bytes:
        limit_mb = settings.max_file_size_bytes / (1024 * 1024)
        raise PayloadTooLarge(f"{what} exceeds the {limit_mb:.0f}MB limit ({size_bytes} bytes)")


def ensure_text_payload(content: str, settings: Settings) -> bytes:
    encoded = content.encode("utf-8")
    ensure_file_size(len(encoded), settings, what="Content")
    return encoded


def read_text_file(path: Path, settings: Settings) -> tuple[str, int]:
    """Read a UTF-8 text file after enforcing the configured size limit."""
    stat = path.stat()
    ensure_file_size(stat.st_size, settings)
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8"), stat.st_size
    except UnicodeDecodeError as exc:
        raise ValidationFailed("Only UTF-8 text files can be read through the bridge") from exc


def ensure_patch(patch: str) -> str:
    cleaned = ensure_non_empty(patch, "patch")
    if len(cleaned.encode("utf-8")) > MAX_PATCH_BYTES:
        raise PayloadTooLarge("Patch payload exceeds the 1MB limit")
    if "@@" not in cleaned:
        raise ValidationFailed("Patch must be a unified diff containing at least one '@@' hunk header")
    return cleaned


def ensure_request_id(request_id: str) -> str:
    cleaned = ensure_non_empty(request_id, "request_id")
    if not REQUEST_ID_PATTERN.match(cleaned):
        raise ValidationFailed("request_id has an invalid format")
    return cleaned
