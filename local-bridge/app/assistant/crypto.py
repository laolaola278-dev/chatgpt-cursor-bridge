"""Phase 32 · AES-256-GCM secret box for provider credentials.

The only place in the codebase that may hold a plaintext API key is a local
variable inside this module and its callers' encrypt/decrypt call. Keys are
sealed with AES-256-GCM (random 96-bit nonce, authenticated additional data =
provider name) before they touch disk.

There is deliberately **no plaintext fallback**: when the cryptography backend
is unavailable the store refuses to save instead of degrading to clear text.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

NONCE_BYTES = 12
KEY_BYTES = 32  # AES-256
ENVELOPE_VERSION = "v1"
KEY_ENV_VAR = "ASSISTANT_SECRET_KEY"


class SecretStorageUnavailable(RuntimeError):
    """Raised when AES-256-GCM is not available on this installation."""

    code = "secret_storage_unavailable"
    status = 503

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "Encrypted credential storage is unavailable: install the 'cryptography' "
            "package (AES-256-GCM) to store provider API keys."
        )
        # ``detail`` is kept short and never echoes key material.
        self.detail = detail[:120]


class SecretDecryptionError(RuntimeError):
    """Raised when a stored envelope cannot be opened (wrong/rotated key)."""

    code = "secret_decrypt_failed"
    status = 409


def _aesgcm_class():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:  # noqa: BLE001 - optional dependency probe
        raise SecretStorageUnavailable(type(exc).__name__) from exc
    return AESGCM


def crypto_available() -> bool:
    try:
        _aesgcm_class()
    except SecretStorageUnavailable:
        return False
    return True


def default_key_path() -> Path:
    from app.config import get_settings

    return get_settings().workspace_root.parent / "assistant" / "secret.key"


def fingerprint(plaintext: str) -> str:
    """Short, non-reversible identity of a key so the UI can show *which* key.

    Truncated SHA-256; never enough material to reconstruct the key and never
    the key's own characters.
    """
    if not plaintext:
        return ""
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:12]}"


def masked_hint(plaintext: str) -> str:
    """Display hint for a configured key: length plus the last 4 characters."""
    if not plaintext:
        return ""
    tail = plaintext[-4:] if len(plaintext) > 8 else ""
    return f"****{tail}" if tail else "****"


@dataclass(frozen=True)
class Envelope:
    """Serialized ciphertext: ``v1:<base64(nonce)>:<base64(ciphertext)>``."""

    nonce: bytes
    ciphertext: bytes

    def serialize(self) -> str:
        return ":".join(
            (
                ENVELOPE_VERSION,
                base64.b64encode(self.nonce).decode("ascii"),
                base64.b64encode(self.ciphertext).decode("ascii"),
            )
        )

    @classmethod
    def parse(cls, raw: str) -> "Envelope":
        parts = (raw or "").split(":")
        if len(parts) != 3 or parts[0] != ENVELOPE_VERSION:
            raise SecretDecryptionError("Stored credential envelope is malformed")
        try:
            return cls(nonce=base64.b64decode(parts[1]), ciphertext=base64.b64decode(parts[2]))
        except Exception as exc:  # noqa: BLE001
            raise SecretDecryptionError("Stored credential envelope is malformed") from exc


class SecretBox:
    """AES-256-GCM sealing with a machine-local key file (or env override)."""

    def __init__(self, key_path: str | Path | None = None, *, key: bytes | None = None) -> None:
        self._key_path = Path(key_path) if key_path is not None else None
        self._key = key

    # -- key material -----------------------------------------------------

    def _load_key(self) -> bytes:
        if self._key is not None:
            return self._key
        env_key = os.getenv(KEY_ENV_VAR, "")
        if env_key:
            try:
                material = base64.b64decode(env_key, validate=True)
            except Exception:  # noqa: BLE001 - fall back to raw utf-8 material
                material = env_key.encode("utf-8")
            if len(material) != KEY_BYTES:
                material = hashlib.sha256(material).digest()
            self._key = material
            return self._key
        path = self._key_path or default_key_path()
        if path.exists():
            material = base64.b64decode(path.read_text(encoding="utf-8").strip())
            if len(material) != KEY_BYTES:
                raise SecretDecryptionError("Local secret key file is invalid")
            self._key = material
            return self._key
        material = secrets.token_bytes(KEY_BYTES)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(base64.b64encode(material).decode("ascii"), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:  # pragma: no cover - platform dependent (Windows ACLs)
            pass
        self._key = material
        return self._key

    # -- sealing ----------------------------------------------------------

    def encrypt(self, plaintext: str, *, aad: str = "") -> str:
        if not plaintext:
            raise ValueError("Refusing to encrypt an empty secret")
        aesgcm = _aesgcm_class()(self._load_key())
        nonce = secrets.token_bytes(NONCE_BYTES)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        return Envelope(nonce=nonce, ciphertext=ciphertext).serialize()

    def decrypt(self, envelope: str, *, aad: str = "") -> str:
        parsed = Envelope.parse(envelope)
        aesgcm = _aesgcm_class()(self._load_key())
        try:
            opened = aesgcm.decrypt(parsed.nonce, parsed.ciphertext, aad.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - vendor exception types vary
            raise SecretDecryptionError("Stored credential could not be decrypted") from exc
        return opened.decode("utf-8")


__all__ = [
    "ENVELOPE_VERSION",
    "Envelope",
    "KEY_ENV_VAR",
    "SecretBox",
    "SecretDecryptionError",
    "SecretStorageUnavailable",
    "crypto_available",
    "default_key_path",
    "fingerprint",
    "masked_hint",
]
