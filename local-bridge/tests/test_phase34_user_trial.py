"""Phase 34 · User Trial & Product Refinement — backend tests (spec §2, §5, §8).

Scope of the Phase 34 backend change: the *unified error experience*. Every
assistant failure now answers with one envelope
(:func:`app.assistant.errors.safe_error_body`) whose ``message`` is one sentence
from a fixed vocabulary, ``provider_not_configured`` reports the documented HTTP
``400``, and a provider that dies *mid-stream* terminates the SSE stream with a
safe ``error`` frame instead of a dropped connection.

Everything else is a *regression* guard: the Ask AI consent gate, the
proposal-only tool path and the approval-gated writes must behave exactly as they
did in Phase 32/33.

No real API key and no external provider call exists in this file. An autouse
fixture blocks outbound HTTP, so the only way a vendor endpoint could be reached
is a hard failure of that fixture — and every provider failure here is raised by
a mock.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.assistant.errors import (
    BACKEND_UNREACHABLE,
    INVALID_KEY,
    NOT_CONFIGURED_DETAIL,
    NOT_CONFIGURED_HTTP_STATUS,
    PROVIDER_UNAVAILABLE,
    RATE_LIMITED,
    REQUEST_REJECTED,
    SAFE_MESSAGES,
    safe_error_body,
    safe_message_for_http,
    safe_provider_failure,
)
from app.assistant.routes import _error_response, _stream_error_event
from app.assistant.service import AssistantService
from app.llm_gateway.providers.base import ProviderError
from app.security.sandbox import SandboxViolation
from app.security.validator import ResourceNotFound, ValidationFailed

SAMPLE_API_KEY = "sk-test-1234567890abcdef"

#: Material that must never appear in a user-visible failure (spec §2).
FORBIDDEN_FRAGMENTS = (
    "Traceback",
    "most recent call last",
    SAMPLE_API_KEY,
    "sk-",
    "Authorization",
    "Bearer ",
    "app/assistant",
    "app\\assistant",
    "site-packages",
    "sqlite://",
    "postgres://",
    "password=",
    "org-1234",
)

#: A raw vendor body of exactly the kind ``base.HTTPProviderMixin`` embeds.
VENDOR_LEAK = (
    "openai 401: {'error': {'message': 'Incorrect API key provided: "
    f"{SAMPLE_API_KEY}. Authorization: Bearer {SAMPLE_API_KEY}', 'org': 'org-1234'}}"
    ' (traceback in File "/usr/lib/site-packages/httpx/_client.py", line 1015)'
)


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard stop against real provider traffic (mirrors the Phase 32 fixture)."""

    def blocked(self, request):  # noqa: ANN001, ANN202
        raise httpx.ConnectError("outbound network is disabled in tests", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)


def user_message(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def ask_ai_bundle(**overrides) -> dict[str, str]:
    bundle = {
        "trigger": "ask_ai",
        "consented_at": "2026-01-01T00:00:00+00:00",
        "page_title": "Rate limiting in FastAPI",
        "page_url": "https://example.com/docs",
        "selected_text": "How do I add a token bucket?",
        "readable_content": "A token bucket refills at a fixed rate.",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    bundle.update(overrides)
    return bundle


def body_of(response) -> dict:
    """Read a ``JSONResponse`` built by ``_error_response`` without a client."""
    return json.loads(response.body.decode("utf-8"))


def assert_safe(payload: object) -> str:
    """Assert a serialized failure carries no forbidden material. Returns it."""
    serialized = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in serialized, f"leaked {fragment!r}: {serialized}"
    # A bare exception repr (``<ProviderError ...>``) is equally forbidden.
    assert "<" not in serialized or "Error" not in serialized
    return serialized


# -- Task 2 · the fixed vocabulary -------------------------------------------


class TestSafeVocabulary:
    """The mapping is closed: classification never produces new text."""

    def test_status_mapping_matches_the_spec(self) -> None:
        assert safe_message_for_http(401) == INVALID_KEY
        assert safe_message_for_http(403) == INVALID_KEY
        assert safe_message_for_http(429) == RATE_LIMITED
        assert safe_message_for_http(500) == PROVIDER_UNAVAILABLE
        assert safe_message_for_http(503) == PROVIDER_UNAVAILABLE
        assert safe_message_for_http(400) == REQUEST_REJECTED
        assert safe_message_for_http(404) == REQUEST_REJECTED
        assert safe_message_for_http(422) == REQUEST_REJECTED

    def test_every_status_stays_inside_the_vocabulary(self) -> None:
        for status in list(range(400, 600)) + [0, 200, 204, 302, 999]:
            assert safe_message_for_http(status) in SAFE_MESSAGES

    def test_not_configured_sentence_and_status_are_the_documented_ones(self) -> None:
        assert NOT_CONFIGURED_DETAIL == "LLM provider is not configured"
        assert NOT_CONFIGURED_HTTP_STATUS == 400

    def test_vendor_text_never_survives_classification(self) -> None:
        exc = ProviderError(VENDOR_LEAK, code="provider_http_error", status=401)
        outcome = safe_provider_failure("openai", exc)
        assert outcome.message == INVALID_KEY
        assert_safe(outcome.as_dict())

    def test_unknown_exception_is_reported_as_an_unreachable_backend(self) -> None:
        outcome = safe_provider_failure("openai", RuntimeError(VENDOR_LEAK))
        assert outcome.message == BACKEND_UNREACHABLE
        assert_safe(outcome.as_dict())


class TestSafeErrorBody:
    """One envelope shape for the extension *and* the Phase 31/32/33 callers."""

    def test_envelope_carries_both_shapes(self) -> None:
        body = safe_error_body("provider_not_configured", NOT_CONFIGURED_DETAIL)
        assert body == {
            "detail": NOT_CONFIGURED_DETAIL,
            "code": "provider_not_configured",
            "error": "provider_not_configured",
            "message": NOT_CONFIGURED_DETAIL,
        }

    def test_detail_is_optional_and_never_replaces_the_message(self) -> None:
        body = safe_error_body("unknown_provider", REQUEST_REJECTED, "Unknown provider 'mystery'")
        assert body["message"] == REQUEST_REJECTED
        assert body["detail"] == "Unknown provider 'mystery'"
        assert body["message"] in SAFE_MESSAGES


# -- Task 2 · _error_response, the single JSON failure path -------------------


class TestErrorResponseMapping:
    def test_unconfigured_provider_is_a_400_envelope(self) -> None:
        exc = ProviderError(
            f"Provider 'openai' is not configured: set OPENAI_API_KEY ({SAMPLE_API_KEY})",
            code="provider_not_configured",
            status=422,
        )
        response = _error_response(exc)
        assert response.status_code == 400
        body = body_of(response)
        assert body["error"] == "provider_not_configured"
        assert body["message"] == NOT_CONFIGURED_DETAIL
        assert_safe(body)

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, INVALID_KEY),
            (403, INVALID_KEY),
            (429, RATE_LIMITED),
            (500, PROVIDER_UNAVAILABLE),
            (503, PROVIDER_UNAVAILABLE),
        ],
    )
    def test_provider_http_failures_map_to_one_sentence(self, status: int, expected: str) -> None:
        exc = ProviderError(VENDOR_LEAK, code="provider_http_error", status=status)
        response = _error_response(exc)
        assert response.status_code == status
        body = body_of(response)
        assert body["message"] == expected
        assert body["error"] == "provider_http_error"
        assert_safe(body)

    def test_unreachable_provider_is_reported_as_an_unreachable_backend(self) -> None:
        exc = ProviderError("name resolution failed", code="provider_unreachable", status=502)
        body = body_of(_error_response(exc))
        assert body["message"] == BACKEND_UNREACHABLE

    def test_caller_side_mistakes_keep_their_own_meaning(self) -> None:
        exc = ProviderError("Unknown provider 'mystery'", code="unknown_provider", status=404)
        response = _error_response(exc)
        assert response.status_code == 404
        body = body_of(response)
        assert body["message"] == REQUEST_REJECTED
        assert body["detail"] == "Unknown provider 'mystery'"

    @pytest.mark.parametrize(
        ("exc", "status", "code"),
        [
            (SandboxViolation("path escapes the sandbox"), 403, "sandbox_violation"),
            (ResourceNotFound("no such project"), 404, "not_found"),
            (ValidationFailed("messages must not be empty"), 422, "validation_failed"),
        ],
    )
    def test_local_failures_keep_their_status_and_a_safe_message(
        self, exc: Exception, status: int, code: str
    ) -> None:
        response = _error_response(exc)
        assert response.status_code == status
        body = body_of(response)
        assert body["code"] == code
        assert body["message"] == safe_message_for_http(status)
        assert body["message"] in SAFE_MESSAGES

    def test_unclassifiable_failure_never_echoes_the_exception(self) -> None:
        response = _error_response(RuntimeError(VENDOR_LEAK))
        assert response.status_code == 500
        body = body_of(response)
        assert body["code"] == "assistant_error"
        assert body["message"] == PROVIDER_UNAVAILABLE
        assert body["detail"] == "Assistant unavailable"
        assert_safe(body)

    def test_every_mapped_failure_stays_inside_the_vocabulary(self) -> None:
        failures = [
            ProviderError("x", code="provider_not_configured", status=422),
            ProviderError(VENDOR_LEAK, code="provider_http_error", status=429),
            ProviderError("x", code="provider_unreachable", status=502),
            ProviderError("x", code="unknown_model", status=404),
            ProviderError(VENDOR_LEAK, code="provider_error", status=502),
            SandboxViolation("x"),
            ResourceNotFound("x"),
            ValidationFailed("x"),
            RuntimeError(VENDOR_LEAK),
            KeyError("api_key"),
        ]
        for exc in failures:
            body = body_of(_error_response(exc))
            assert body["message"] in SAFE_MESSAGES, exc
            assert_safe(body)


# -- Task 2 · the mid-stream SSE error frame ---------------------------------


class TestStreamErrorEvent:
    def test_frame_shape_matches_a_normal_stream_event(self) -> None:
        event = _stream_error_event(ProviderError(VENDOR_LEAK, code="provider_http_error", status=429))
        assert set(event) == {"type", "content", "toolCall", "provider", "model"}
        assert event["type"] == "error"
        assert event["content"] == RATE_LIMITED
        assert event["toolCall"] is None

    def test_unconfigured_provider_gets_the_documented_sentence(self) -> None:
        event = _stream_error_event(ProviderError("x", code="provider_not_configured", status=422))
        assert event["content"] == NOT_CONFIGURED_DETAIL

    def test_any_failure_produces_one_safe_sentence(self) -> None:
        for exc in [
            ProviderError(VENDOR_LEAK, code="provider_http_error", status=401),
            ProviderError("x", code="provider_unreachable", status=502),
            RuntimeError(VENDOR_LEAK),
            ValueError(SAMPLE_API_KEY),
        ]:
            event = _stream_error_event(exc)
            assert event["content"] in SAFE_MESSAGES, exc
            assert_safe(event)


# -- Task 2 · the HTTP surface (mock provider failures only) -----------------


class TestUnifiedErrorHTTP:
    def test_chat_reports_an_unconfigured_provider_as_400(self, bridge) -> None:
        response = bridge.client.post(
            "/assistant/chat",
            json={
                "project": "demo",
                "messages": [user_message("hello")],
                "provider": "openai",
                "model": "gpt-4o",
            },
        )
        assert response.status_code == NOT_CONFIGURED_HTTP_STATUS
        body = response.json()
        assert body["error"] == "provider_not_configured"
        assert body["message"] == NOT_CONFIGURED_DETAIL
        assert_safe(response.text)

    def test_stream_reports_an_unconfigured_provider_as_400(self, bridge) -> None:
        response = bridge.client.post(
            "/assistant/chat/stream",
            json={
                "project": "demo",
                "messages": [user_message("hello")],
                "provider": "openai",
                "model": "gpt-4o",
            },
        )
        assert response.status_code == NOT_CONFIGURED_HTTP_STATUS
        body = response.json()
        assert body["error"] == "provider_not_configured"
        assert body["message"] == NOT_CONFIGURED_DETAIL

    @pytest.mark.parametrize(
        ("status", "expected"),
        [(401, INVALID_KEY), (429, RATE_LIMITED), (500, PROVIDER_UNAVAILABLE)],
    )
    def test_chat_maps_a_mocked_provider_failure_to_one_sentence(
        self, bridge, monkeypatch: pytest.MonkeyPatch, status: int, expected: str
    ) -> None:
        def failing_chat(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
            raise ProviderError(VENDOR_LEAK, code="provider_http_error", status=status)

        monkeypatch.setattr(AssistantService, "chat", failing_chat)
        response = bridge.client.post(
            "/assistant/chat", json={"project": "demo", "messages": [user_message("hello")]}
        )
        assert response.status_code == status
        assert response.json()["message"] == expected
        assert_safe(response.text)

    def test_a_network_failure_is_reported_as_an_unreachable_backend(
        self, bridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def failing_chat(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
            raise ProviderError("Connection refused to api.openai.com", code="provider_unreachable", status=502)

        monkeypatch.setattr(AssistantService, "chat", failing_chat)
        response = bridge.client.post(
            "/assistant/chat", json={"project": "demo", "messages": [user_message("hello")]}
        )
        assert response.json()["message"] == BACKEND_UNREACHABLE

    def test_an_unexpected_crash_never_leaks_its_cause(
        self, bridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def failing_chat(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
            raise RuntimeError(VENDOR_LEAK)

        monkeypatch.setattr(AssistantService, "chat", failing_chat)
        response = bridge.client.post(
            "/assistant/chat", json={"project": "demo", "messages": [user_message("hello")]}
        )
        assert response.status_code == 500
        assert response.json()["message"] == PROVIDER_UNAVAILABLE
        assert_safe(response.text)

    def test_a_mid_stream_failure_ends_the_stream_with_a_safe_error_frame(
        self, bridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure arrives *after* the first token, so JSON is impossible."""

        class Event:
            def __init__(self, payload: dict) -> None:
                self.payload = payload

            def as_dict(self) -> dict:
                return self.payload

        def half_a_stream(self, **kwargs):  # noqa: ANN001, ANN003, ANN202
            def generate():
                yield Event({"type": "delta", "content": "half ", "toolCall": None,
                             "provider": "openai", "model": "gpt-4o"})
                raise ProviderError(VENDOR_LEAK, code="provider_http_error", status=429)

            return generate()

        monkeypatch.setattr(AssistantService, "stream_events", half_a_stream)
        response = bridge.client.post(
            "/assistant/chat/stream", json={"project": "demo", "messages": [user_message("hello")]}
        )
        # The response already started, so the status stays 200 …
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        # … and the stream is *terminated* by one safe error frame.
        assert '"type": "delta"' in response.text
        assert '"type": "error"' in response.text
        assert RATE_LIMITED in response.text
        assert_safe(response.text)

    def test_provider_test_still_answers_with_the_fixed_vocabulary(self, bridge) -> None:
        for provider in ["openai", "anthropic", "deepseek", "local"]:
            response = bridge.client.post("/provider/test", json={"provider": provider})
            assert response.status_code == 200
            body = response.json()
            assert body["message"] in SAFE_MESSAGES, provider
            assert body["readOnly"] is True
            assert_safe(response.text)

    def test_no_failure_body_carries_a_key_a_header_or_a_path(self, bridge) -> None:
        probes = [
            ("/assistant/chat", {"project": "../evil", "messages": [user_message("x")]}),
            ("/assistant/chat", {"project": "demo", "messages": []}),
            ("/assistant/chat", {"project": "demo", "messages": [user_message("x")], "provider": "mystery"}),
            ("/assistant/chat", {"project": "demo", "messages": [user_message("x")],
                                 "web_context": ask_ai_bundle(trigger="page_load")}),
            ("/assistant/chat", {"project": "demo", "messages": [user_message("x")],
                                 "web_context": ask_ai_bundle(page_url="file:///etc/passwd")}),
            ("/provider/test", {"provider": "mystery"}),
            ("/user/settings", {}),
        ]
        for path, payload in probes:
            response = bridge.client.post(path, json=payload)
            assert response.status_code >= 400 or response.status_code == 202
            assert_safe(response.text)


# -- Task 5/8 · regression: consent, proposals and approvals are unchanged ---


class TestBoundariesUnchanged:
    """Phase 34 is a polish phase: none of these may have moved."""

    def test_context_still_requires_an_explicit_ask_ai_trigger(self, bridge) -> None:
        response = bridge.client.post(
            "/assistant/chat",
            json={
                "project": "demo",
                "messages": [user_message("x")],
                "web_context": ask_ai_bundle(trigger="page_load"),
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "context_consent_required"

    def test_ask_ai_context_is_used_only_when_it_is_supplied(self, bridge) -> None:
        without = bridge.client.post(
            "/assistant/chat", json={"project": "demo", "messages": [user_message("hello")]}
        )
        assert without.json()["contextIncluded"] is False
        with_context = bridge.client.post(
            "/assistant/chat",
            json={"project": "demo", "messages": [user_message("hello")], "web_context": ask_ai_bundle()},
        )
        assert with_context.json()["contextIncluded"] is True

    def test_chat_never_executes_a_tool_call(self, bridge) -> None:
        response = bridge.client.post(
            "/assistant/chat", json={"project": "demo", "messages": [user_message("write a file")]}
        )
        assert response.status_code == 200
        assert response.json()["toolCallsExecuted"] is False
        assert response.json()["readOnly"] is True

    def test_provider_config_is_still_approval_gated_and_key_free(self, bridge) -> None:
        pending = bridge.client.post(
            "/provider/config",
            json={
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": SAMPLE_API_KEY,
                "reason": "phase 34 regression",
            },
        )
        assert pending.status_code == 202
        assert SAMPLE_API_KEY not in pending.text
        assert "sk-test" not in pending.text
        # Still inert until a human approves it.
        catalog = bridge.client.get("/provider/status").json()["providers"]
        entry = next(item for item in catalog if item["provider"] == "openai")
        assert entry["hasStoredKey"] is False

    def test_no_response_body_ever_carries_credential_material(self, bridge) -> None:
        """No credential *field* and no key *value* in any read-only projection.

        ``keyEnv`` legitimately names the environment variable
        (``OPENAI_API_KEY``), so the check is on the JSON field names and on the
        secret material itself — not on a substring of a variable name.
        """

        def field_names(node: object) -> set[str]:
            if isinstance(node, dict):
                names = {str(key).lower() for key in node}
                for value in node.values():
                    names |= field_names(value)
                return names
            if isinstance(node, list):
                return set().union(*(field_names(item) for item in node)) if node else set()
            return set()

        for path in ["/user/settings", "/provider/status", "/context/status"]:
            response = bridge.client.get(path)
            assert response.status_code == 200
            names = field_names(response.json())
            for forbidden in ["api_key", "apikey", "encrypted_api_key", "authorization", "secret", "password"]:
                assert forbidden not in names, f"{path} exposes a {forbidden} field"
            for value in ["sk-", "bearer ", SAMPLE_API_KEY]:
                assert value not in response.text.lower(), f"{path} leaked {value}"
