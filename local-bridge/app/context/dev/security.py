"""Security filtering for developer context.

Context reads are read-only and never touch secrets. This module:

* rejects sensitive file names (``.env``, key material, credential stores);
* redacts secret-looking values inside text that is allowed through;
* exposes the filtering status on every bundle.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

#: File/directory names that are never included in context bundles.
SENSITIVE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".netrc",
        ".htpasswd",
        ".pypirc",
        ".npmrc",
        ".yarnrc.yml",
        ".git-credentials",
        "credentials.json",
        "credential.json",
        "service-account.json",
        "secrets.json",
        "secret.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        ".dockercfg",
        ".dockerconfigjson",
        "config.json",
        "kubeconfig",
        "id_rsa.pub",
        "known_hosts",
    }
)

#: Suffixes treated as secret material regardless of their file name.
SENSITIVE_SUFFIXES = frozenset(
    {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".crt", ".cer", ".p8", ".asc", ".gpg"}
)

#: Secret-like keys redacted wherever they appear (case-insensitive).
_SECRET_KEY_PATTERN = re.compile(
    r"\b(api[_-]?key|api[_-]?secret|access[_-]?key|secret[_-]?key|secret[_-]?token|"
    r"client[_-]?secret|client[_-]?token|auth[_-]?token|authorization|password|"
    r"passwd|private[_-]?key|bearer|refresh[_-]?token|session[_-]?token|"
    r"token|credential|app[_-]?secret|webhook[_-]?secret)\b",
    re.IGNORECASE,
)

#: Inline assignment redaction, e.g. ``AWS_SECRET_KEY=abc123`` -> ``AWS_SECRET_KEY=***REDACTED***``.
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b([a-z0-9_]{0,64}(?:api[_-]?key|secret|token|password|credential|authorization|"
    r"private[_-]?key|access[_-]?key)[a-z0-9_]{0,64})\s*[\"']?\s*[:=]\s*[\"']?([^\s\"'`,;]+)",
)

#: Bearer token values, e.g. ``Authorization: Bearer eyJ...`` -> value redacted.
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=:,-]{8,}")

_REDACTED = "***REDACTED***"


def is_sensitive_path(relative_path: str) -> bool:
    """Return True when a project-relative path must never enter context."""
    parts = PurePosixPath(relative_path.replace("\\", "/")).parts
    if any(part in SENSITIVE_NAMES for part in parts):
        return True
    if any(part.lower().endswith(tuple(SENSITIVE_SUFFIXES)) for part in parts):
        return True
    lowered = relative_path.lower()
    if "/.git/" in lowered or lowered.startswith(".git/"):
        return True
    return False


def redact_secrets(text: str) -> str:
    """Redact secret-like assignments, key/value pairs and bearer tokens."""
    redacted = _BEARER_PATTERN.sub(_REDACTED, text)
    redacted = _ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}={_REDACTED}", redacted)
    redacted = _SECRET_KEY_PATTERN.sub(_REDACTED, redacted)
    return redacted


def redact_line(line: str) -> str:
    """Redact a single line (used when surfacing diff lines or file excerpts)."""
    return redact_secrets(line)
