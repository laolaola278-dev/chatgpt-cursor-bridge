"""Phase 32 · Safe provider error mapping.

The Phase 31 provider layer raises ``ProviderError`` messages that may embed the
vendor's raw response body (``base.HTTPProviderMixin._request_json`` includes
``response.text[:400]``). Those messages are fine for an internal 502 but must
never reach the Settings page: they can carry provider account identifiers,
request echoes and internal hints.

Everything user-visible from ``POST /provider/test`` goes through
:func:`safe_provider_failure`, which maps a failure to one of a small set of
fixed strings. No stack trace, no vendor payload, no header, no path, no key.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.assistant.store import CONNECTED, FAILED, NOT_CONFIGURED

INVALID_KEY = "Invalid API key"
RATE_LIMITED = "Rate limit reached"
PROVIDER_UNAVAILABLE = "Provider unavailable"
BACKEND_UNREACHABLE = "Backend unreachable"
NOT_CONFIGURED_MESSAGE = "Not configured"
REQUEST_REJECTED = "Provider rejected the request"
CONNECTED_MESSAGE = "Connected"
# Phase 34 · the sentence the panel shows when no provider is set up. The
# ``/provider/status`` badge keeps the short ``NOT_CONFIGURED_MESSAGE``; this is
# the full sentence returned by the chat endpoints.
NOT_CONFIGURED_DETAIL = "LLM provider is not configured"

# Fixed vocabulary: anything user-visible must be one of these.
SAFE_MESSAGES = (
    CONNECTED_MESSAGE,
    INVALID_KEY,
    RATE_LIMITED,
    PROVIDER_UNAVAILABLE,
    BACKEND_UNREACHABLE,
    NOT_CONFIGURED_MESSAGE,
    NOT_CONFIGURED_DETAIL,
    REQUEST_REJECTED,
)

#: Phase 34 · HTTP status for "no provider configured" on the assistant chat
#: endpoints. The Phase 31 gateway keeps raising ``ProviderError(status=422)``
#: internally (and ``/llm/chat`` still answers 422); the assistant API — the one
#: the extension talks to — reports the unified 400 documented in Phase 34.
NOT_CONFIGURED_HTTP_STATUS = 400


def safe_error_body(code: str, message: str, detail: str | None = None) -> dict[str, str]:
    """Phase 34 · one body shape for every assistant failure.

    ``error`` and ``message`` are the Phase 34 envelope the extension reads;
    ``detail`` and ``code`` are kept so every Phase 31/32/33 caller and test
    keeps working. ``message`` is always a fixed safe sentence, so the envelope
    itself can never carry a stack trace, a path, a key, a header or a vendor
    body — only ``detail`` keeps the existing (already safe) text.
    """
    return {
        "detail": message if detail is None else detail,
        "code": code,
        "error": code,
        "message": message,
    }


@dataclass(frozen=True)
class ProviderTestOutcome:
    provider: str
    status: str
    message: str
    httpStatus: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "status": self.status,
            "message": self.message,
            "httpStatus": self.httpStatus,
            "readOnly": True,
        }


def safe_message_for_http(status_code: int) -> str:
    if status_code in (401, 403):
        return INVALID_KEY
    if status_code == 429:
        return RATE_LIMITED
    if status_code >= 500:
        return PROVIDER_UNAVAILABLE
    if status_code >= 400:
        return REQUEST_REJECTED
    return CONNECTED_MESSAGE


def safe_provider_failure(provider: str, exc: Exception) -> ProviderTestOutcome:
    """Map any provider exception to a safe Connected/Failed/Not configured."""
    from app.llm_gateway.providers.base import ProviderError

    if isinstance(exc, ProviderError):
        if exc.code == "provider_not_configured":
            return ProviderTestOutcome(provider, NOT_CONFIGURED, NOT_CONFIGURED_MESSAGE)
        if exc.code in ("unknown_provider", "unknown_model"):
            # Caller-side mistakes are reported without vendor detail.
            return ProviderTestOutcome(provider, FAILED, REQUEST_REJECTED, exc.status)
        if exc.code == "provider_unreachable":
            return ProviderTestOutcome(provider, FAILED, BACKEND_UNREACHABLE)
        if exc.code == "provider_http_error":
            return ProviderTestOutcome(provider, FAILED, safe_message_for_http(exc.status), exc.status)
        return ProviderTestOutcome(provider, FAILED, PROVIDER_UNAVAILABLE)
    return ProviderTestOutcome(provider, FAILED, BACKEND_UNREACHABLE)


def connected(provider: str) -> ProviderTestOutcome:
    return ProviderTestOutcome(provider, CONNECTED, CONNECTED_MESSAGE, 200)


def not_configured(provider: str) -> ProviderTestOutcome:
    return ProviderTestOutcome(provider, NOT_CONFIGURED, NOT_CONFIGURED_MESSAGE)


__all__ = [
    "BACKEND_UNREACHABLE",
    "CONNECTED_MESSAGE",
    "INVALID_KEY",
    "NOT_CONFIGURED_DETAIL",
    "NOT_CONFIGURED_HTTP_STATUS",
    "NOT_CONFIGURED_MESSAGE",
    "PROVIDER_UNAVAILABLE",
    "ProviderTestOutcome",
    "RATE_LIMITED",
    "REQUEST_REJECTED",
    "SAFE_MESSAGES",
    "connected",
    "not_configured",
    "safe_error_body",
    "safe_message_for_http",
    "safe_provider_failure",
]
