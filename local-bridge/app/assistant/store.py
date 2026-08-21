"""Phase 32 · Provider credential + user preference storage.

SQLite-backed, single local user. Two hard rules enforced here:

1. An API key is **only ever** persisted as an AES-256-GCM envelope
   (``app.assistant.crypto``). No column, log line, or return value of this
   module carries plaintext key material.
2. A newly submitted credential lands in ``status='staged'``. It becomes usable
   only after :meth:`activate_credential` runs, which happens exclusively from
   the approved-action dispatcher — the human-in-the-loop boundary.

The public projections (:meth:`public_credentials`, :meth:`preferences`) are the
only shapes the HTTP layer is allowed to serialize.
"""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .crypto import SecretBox, fingerprint, masked_hint

STATUS_STAGED = "staged"
STATUS_ACTIVE = "active"

# Provider connection statuses surfaced to the UI (spec §4).
CONNECTED = "connected"
NOT_CONFIGURED = "not_configured"
FAILED = "failed"

# Preference keys the Bridge is willing to persist. Anything resembling a
# credential is rejected by ``set_preference``.
ALLOWED_PREFERENCE_KEYS = (
    "mode",
    "selected_provider",
    "selected_model",
    "onboarding_state",
    "theme",
    "language",
)

FORBIDDEN_PREFERENCE_FRAGMENTS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "authorization",
    "credential",
    "bearer",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def default_assistant_db_path() -> Path:
    from app.config import get_settings

    return get_settings().workspace_root.parent / "assistant" / "assistant.db"


class PreferenceRejected(ValueError):
    """Raised when a caller tries to persist a non-allowlisted preference."""

    code = "preference_rejected"
    status = 422


@dataclass(frozen=True)
class CredentialRecord:
    credential_id: str
    provider: str
    model: str
    base_url: str
    key_fingerprint: str
    key_hint: str
    has_key: bool
    status: str
    connection_status: str
    last_tested_at: str
    approval_request_id: str
    created_at: str
    updated_at: str

    def public_dict(self) -> dict[str, Any]:
        """Non-sensitive projection. Never includes envelope or key material."""
        return {
            "provider": self.provider,
            "model": self.model,
            "baseUrl": self.base_url,
            "hasApiKey": self.has_key,
            "keyFingerprint": self.key_fingerprint,
            "keyHint": self.key_hint,
            "state": self.status,
            "status": self.connection_status,
            "lastTestedAt": self.last_tested_at,
            "approvalRequestId": self.approval_request_id,
            "updatedAt": self.updated_at,
        }


class AssistantSettingsStore:
    def __init__(self, db_path: str | Path, *, secret_box: SecretBox | None = None) -> None:
        self._lock = Lock()
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._secrets = secret_box or SecretBox()
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_credentials (
                credential_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL DEFAULT '',
                encrypted_api_key TEXT NOT NULL DEFAULT '',
                key_fingerprint TEXT NOT NULL DEFAULT '',
                key_hint TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                connection_status TEXT NOT NULL DEFAULT 'not_configured',
                last_tested_at TEXT NOT NULL DEFAULT '',
                approval_request_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    # -- rows -------------------------------------------------------------

    @staticmethod
    def _record(row: sqlite3.Row) -> CredentialRecord:
        return CredentialRecord(
            credential_id=row["credential_id"],
            provider=row["provider"],
            model=row["model"],
            base_url=row["base_url"],
            key_fingerprint=row["key_fingerprint"],
            key_hint=row["key_hint"],
            has_key=bool(row["encrypted_api_key"]),
            status=row["status"],
            connection_status=row["connection_status"],
            last_tested_at=row["last_tested_at"],
            approval_request_id=row["approval_request_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # -- credentials ------------------------------------------------------

    def stage_credential(
        self,
        *,
        provider: str,
        model: str = "",
        base_url: str = "",
        api_key: str = "",
        keep_existing_key: bool = False,
    ) -> CredentialRecord:
        """Encrypt and store a pending credential (never active on its own)."""
        now = _utc_now()
        envelope = ""
        key_fingerprint = ""
        key_hint = ""
        if api_key:
            envelope = self._secrets.encrypt(api_key, aad=provider)
            key_fingerprint = fingerprint(api_key)
            key_hint = masked_hint(api_key)
        elif keep_existing_key:
            current = self.active_credential(provider)
            if current is not None:
                with self._lock:
                    row = self._connection.execute(
                        "SELECT encrypted_api_key FROM provider_credentials WHERE credential_id = ?",
                        (current.credential_id,),
                    ).fetchone()
                envelope = row["encrypted_api_key"] if row else ""
                key_fingerprint = current.key_fingerprint
                key_hint = current.key_hint
        credential_id = _new_id("cred")
        with self._lock:
            # Only the newest staged credential per provider is retained; older
            # staged rows (rejected or superseded) are discarded.
            self._connection.execute(
                "DELETE FROM provider_credentials WHERE provider = ? AND status = ?",
                (provider, STATUS_STAGED),
            )
            self._connection.execute(
                """
                INSERT INTO provider_credentials (
                    credential_id, provider, model, base_url, encrypted_api_key,
                    key_fingerprint, key_hint, status, connection_status,
                    last_tested_at, approval_request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?)
                """,
                (
                    credential_id,
                    provider,
                    model,
                    base_url,
                    envelope,
                    key_fingerprint,
                    key_hint,
                    STATUS_STAGED,
                    NOT_CONFIGURED,
                    now,
                    now,
                ),
            )
            self._connection.commit()
        return self.get_credential(credential_id)  # type: ignore[return-value]

    def activate_credential(self, credential_id: str, *, approval_request_id: str = "") -> CredentialRecord | None:
        """Promote a staged credential after human approval."""
        record = self.get_credential(credential_id)
        if record is None or record.status != STATUS_STAGED:
            return None
        now = _utc_now()
        with self._lock:
            self._connection.execute(
                "DELETE FROM provider_credentials WHERE provider = ? AND status = ? AND credential_id != ?",
                (record.provider, STATUS_ACTIVE, credential_id),
            )
            self._connection.execute(
                """
                UPDATE provider_credentials
                   SET status = ?, connection_status = ?, approval_request_id = ?, updated_at = ?
                 WHERE credential_id = ?
                """,
                (
                    STATUS_ACTIVE,
                    CONNECTED if record.has_key else NOT_CONFIGURED,
                    approval_request_id,
                    now,
                    credential_id,
                ),
            )
            self._connection.commit()
        return self.get_credential(credential_id)

    def get_credential(self, credential_id: str) -> CredentialRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM provider_credentials WHERE credential_id = ?", (credential_id,)
            ).fetchone()
        return self._record(row) if row else None

    def active_credential(self, provider: str) -> CredentialRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM provider_credentials
                 WHERE provider = ? AND status = ?
                 ORDER BY updated_at DESC LIMIT 1
                """,
                (provider, STATUS_ACTIVE),
            ).fetchone()
        return self._record(row) if row else None

    def public_credentials(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM provider_credentials WHERE status = ? ORDER BY provider", (STATUS_ACTIVE,)
            ).fetchall()
        return [self._record(row).public_dict() for row in rows]

    def reveal_api_key(self, provider: str) -> str:
        """Decrypt the active key for outbound provider calls only.

        Callers must pass the result straight into an Authorization header and
        must never log, echo, or persist it.
        """
        record = self.active_credential(provider)
        if record is None or not record.has_key:
            return ""
        with self._lock:
            row = self._connection.execute(
                "SELECT encrypted_api_key FROM provider_credentials WHERE credential_id = ?",
                (record.credential_id,),
            ).fetchone()
        if row is None or not row["encrypted_api_key"]:
            return ""
        return self._secrets.decrypt(row["encrypted_api_key"], aad=provider)

    def forget_provider(self, provider: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM provider_credentials WHERE provider = ?", (provider,)
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def record_connection_status(self, provider: str, status: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE provider_credentials
                   SET connection_status = ?, last_tested_at = ?, updated_at = ?
                 WHERE provider = ? AND status = ?
                """,
                (status, _utc_now(), _utc_now(), provider, STATUS_ACTIVE),
            )
            self._connection.commit()

    # -- preferences ------------------------------------------------------

    def set_preference(self, key: str, value: str) -> None:
        normalized = (key or "").strip().lower()
        if normalized not in ALLOWED_PREFERENCE_KEYS:
            raise PreferenceRejected(f"Preference '{key}' is not stored by the Bridge")
        if any(fragment in normalized for fragment in FORBIDDEN_PREFERENCE_FRAGMENTS):
            raise PreferenceRejected("Credential-like preferences are never stored")
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (normalized, str(value)[:400], _utc_now()),
            )
            self._connection.commit()

    def preferences(self) -> dict[str, str]:
        with self._lock:
            rows = self._connection.execute("SELECT key, value FROM user_preferences").fetchall()
        return {row["key"]: row["value"] for row in rows}


__all__ = [
    "ALLOWED_PREFERENCE_KEYS",
    "AssistantSettingsStore",
    "CONNECTED",
    "CredentialRecord",
    "FAILED",
    "NOT_CONFIGURED",
    "PreferenceRejected",
    "STATUS_ACTIVE",
    "STATUS_STAGED",
    "default_assistant_db_path",
]
