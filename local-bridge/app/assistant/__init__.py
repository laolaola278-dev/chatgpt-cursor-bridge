"""Phase 32 · AI Assistant Productization.

Product layer on top of the Phase 31 LLM Gateway: user/developer modes,
encrypted provider credentials, explicit-consent web context, and an assistant
chat that stays read-only.

Nothing in this package executes tools, runs shells, applies patches, writes
source files or approves anything. Persistent writes are approval-gated through
the existing ApprovalStore.
"""

from __future__ import annotations

from .context import (
    ASK_AI_TRIGGER,
    ContextConsentRequired,
    ContextSourceRejected,
    WebContext,
    build_web_context,
    redact_secrets,
    render_context_block,
)
from .crypto import SecretBox, SecretDecryptionError, SecretStorageUnavailable, crypto_available
from .errors import SAFE_MESSAGES, ProviderTestOutcome, safe_provider_failure
from .providers import SELECTABLE_PROVIDERS, VENDOR_PROVIDERS, build_registry, provider_catalog, test_provider
from .service import (
    DEVELOPER_MODE,
    DEVELOPER_MODE_SURFACES,
    MODES,
    NEVER_AVAILABLE,
    USER_MODE,
    USER_MODE_SURFACES,
    AssistantService,
)
from .store import AssistantSettingsStore, PreferenceRejected, default_assistant_db_path

__all__ = [
    "ASK_AI_TRIGGER",
    "AssistantService",
    "AssistantSettingsStore",
    "ContextConsentRequired",
    "ContextSourceRejected",
    "DEVELOPER_MODE",
    "DEVELOPER_MODE_SURFACES",
    "MODES",
    "NEVER_AVAILABLE",
    "PreferenceRejected",
    "ProviderTestOutcome",
    "SAFE_MESSAGES",
    "SELECTABLE_PROVIDERS",
    "SecretBox",
    "SecretDecryptionError",
    "SecretStorageUnavailable",
    "USER_MODE",
    "USER_MODE_SURFACES",
    "VENDOR_PROVIDERS",
    "WebContext",
    "build_registry",
    "build_web_context",
    "crypto_available",
    "default_assistant_db_path",
    "provider_catalog",
    "redact_secrets",
    "render_context_block",
    "safe_provider_failure",
    "test_provider",
]
