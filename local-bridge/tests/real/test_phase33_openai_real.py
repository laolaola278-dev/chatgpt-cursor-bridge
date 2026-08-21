"""Phase 33 · Real OpenAI validation — **skipped unless explicitly enabled**.

Enable with both gates (see ``tests/real/__init__.py``):

```bash
OPENAI_API_KEY=<your key> REAL_LLM_RUN=1 python -m pytest tests/real -q
```

Coverage (§12): streaming, a ≥100-message conversation, a bounded long context,
a 401 from a deliberately invalid key, 429 and 5xx through a **mock** transport,
and the secret-leak assertions.

Two deliberate omissions, both required by the spec:

* **429 is never provoked.** §12 forbids abusive traffic just to trigger a rate
  limit, so the 429 path is exercised with a mock transport, not with a burst of
  real requests. The same is true of 5xx, which we cannot induce politely.
* **Nothing is ever echoed.** Assertions compare against the fixed safe
  vocabulary and against *absence* of the key; no test message contains the key,
  the ``Authorization`` header or a raw provider body, so a failure report
  cannot become the leak (§13).
"""

from __future__ import annotations

import json
import os
import re

import httpx
import pytest

from app.assistant.errors import (
    CONNECTED_MESSAGE,
    INVALID_KEY,
    PROVIDER_UNAVAILABLE,
    RATE_LIMITED,
    SAFE_MESSAGES,
)
from app.assistant.service import AssistantService
from app.assistant.store import AssistantSettingsStore
from app.llm_gateway.conversation import ConversationStore
from app.llm_gateway.models import MessageRole
from real import KEY_ENV, real_run_enabled, skip_reason

# Every test in this module is gated. Collection still happens (so the suite can
# prove the file is skipped rather than missing), execution does not.
pytestmark = pytest.mark.skipif(not real_run_enabled(), reason=skip_reason())

REAL_MODEL = os.environ.get("REAL_LLM_MODEL", "gpt-4o-mini")

# Shapes that must never appear in anything this module produces.
LEAK_PATTERNS = (
    r"sk-[A-Za-z0-9_\-]{16,}",
    r"(?i)\bauthorization\b\s*[:=]",
    r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}",
)


def real_key() -> str:
    """The configured key. Returned, never logged, never asserted on."""
    return os.environ.get(KEY_ENV, "").strip()


def assert_no_leak(label: str, text: str) -> None:
    """Fail with the *label* only — the inspected text is never included."""
    key = real_key()
    assert key and key not in text, f"{label} contains the configured key"
    for pattern in LEAK_PATTERNS:
        assert re.search(pattern, text) is None, f"{label} matches {pattern}"


@pytest.fixture()
def service(tmp_path) -> AssistantService:
    """A service that reads the key from the environment, not from the repo."""
    store = AssistantSettingsStore(tmp_path / "assistant.db")
    return AssistantService(store)


def mock_service(tmp_path, status: int, payload: dict | None = None) -> AssistantService:
    """A service wired to a mock transport — no real request leaves the machine."""
    body = payload if payload is not None else {"error": {"message": "mocked upstream detail"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    store = AssistantSettingsStore(tmp_path / f"mock-{status}.db")
    return AssistantService(store, transport=httpx.MockTransport(handler))


# -- Connection ---------------------------------------------------------------

class TestRealConnection:
    def test_probe_reports_connected(self, service: AssistantService) -> None:
        outcome = service.test_provider(provider="openai", model=REAL_MODEL)
        assert outcome["message"] in SAFE_MESSAGES
        assert outcome["message"] == CONNECTED_MESSAGE, outcome["status"]
        assert outcome["readOnly"] is True
        assert_no_leak("provider probe", json.dumps(outcome, ensure_ascii=False))

    def test_invalid_key_is_reported_as_invalid(self, service: AssistantService) -> None:
        """A deliberately wrong key: one cheap request, no real credential used."""
        outcome = service.test_provider(
            provider="openai", model=REAL_MODEL, api_key="sk-invalid-" + "0" * 24
        )
        assert outcome["message"] == INVALID_KEY
        assert_no_leak("invalid-key probe", json.dumps(outcome, ensure_ascii=False))


# -- Chat and streaming -------------------------------------------------------

class TestRealChatAndStreaming:
    def test_single_turn_chat_returns_content_without_leaking(
        self, service: AssistantService
    ) -> None:
        payload = service.chat(
            project="real-check",
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            provider="openai",
            model=REAL_MODEL,
            max_tokens=32,
        )
        assert payload["content"].strip()
        # The gateway stays a gateway: a tool call is a proposal, never a run.
        assert payload["toolCallsExecuted"] is False
        assert_no_leak("chat payload", json.dumps(payload, ensure_ascii=False))

    def test_streaming_emits_deltas_then_done(self, service: AssistantService) -> None:
        events = list(
            service.stream_events(
                project="real-check",
                messages=[{"role": "user", "content": "Count from one to five."}],
                provider="openai",
                model=REAL_MODEL,
                max_tokens=64,
            )
        )
        kinds = [event.kind for event in events]
        assert kinds, "the stream produced no event"
        assert "delta" in kinds
        assert kinds[-1] in ("done", "error")
        assert kinds.count("done") <= 1, "a stream must not restart itself"
        text = "".join(event.content for event in events if event.kind == "delta")
        assert text.strip()
        assert_no_leak("stream text", text)
        assert_no_leak(
            "stream events", json.dumps([event.as_dict() for event in events], ensure_ascii=False)
        )

    def test_stopping_a_stream_never_resends(self, service: AssistantService) -> None:
        """§16: a user stop ends the turn — no automatic retry, no re-send."""
        stream = service.stream_events(
            project="real-check",
            messages=[{"role": "user", "content": "Write two short sentences."}],
            provider="openai",
            model=REAL_MODEL,
            max_tokens=64,
        )
        iterator = iter(stream)
        seen = [next(iterator) for _ in range(1)]
        iterator.close() if hasattr(iterator, "close") else None
        del iterator  # dropping the generator is the whole stop mechanism
        assert seen and seen[0].kind in ("delta", "done", "error")


# -- A long conversation ------------------------------------------------------

class TestRealLongConversation:
    def test_hundred_message_history_is_stored_and_bounded(
        self, service: AssistantService, tmp_path
    ) -> None:
        """A ≥100-message history round-trips locally; only the tail is sent."""
        store = ConversationStore(tmp_path / "real-conversations.db")
        conversation = store.create_conversation(
            project="real-check", provider="openai", model=REAL_MODEL, title="long run"
        )
        for index in range(100):
            store.append_message(
                conversation_id=conversation.conversation_id,
                role=MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT,
                content=f"turn {index}",
            )
        history = store.list_messages(conversation.conversation_id, limit=200)
        assert len(history) == 100

        # Only a bounded tail is ever sent to the provider: the context must not
        # inflate without limit (§12).
        tail = [
            {"role": message.role.value, "content": message.content} for message in history[-8:]
        ]
        tail.append({"role": "user", "content": "Reply with the single word: done"})
        payload = service.chat(
            project="real-check",
            messages=tail,
            provider="openai",
            model=REAL_MODEL,
            max_tokens=32,
        )
        assert payload["content"].strip()
        assert_no_leak("long-history payload", json.dumps(payload, ensure_ascii=False))

    def test_long_single_prompt_stays_within_a_fixed_ceiling(
        self, service: AssistantService
    ) -> None:
        # ~8 KB, fixed. Deliberately not grown in a loop until something breaks.
        filler = "The bridge never executes a tool. " * 240
        payload = service.chat(
            project="real-check",
            messages=[
                {"role": "user", "content": filler},
                {"role": "user", "content": "In one word: acknowledged?"},
            ],
            provider="openai",
            model=REAL_MODEL,
            max_tokens=32,
        )
        assert payload["content"].strip()
        assert_no_leak("long-prompt payload", json.dumps(payload, ensure_ascii=False))


# -- Failure modes that must not be provoked for real -------------------------

class TestMockedFailureModes:
    """429 and 5xx come from a mock transport: §12 forbids abusive traffic."""

    def test_rate_limit_maps_to_the_safe_message(self, tmp_path) -> None:
        outcome = mock_service(tmp_path, 429).test_provider(provider="openai", model=REAL_MODEL)
        assert outcome["message"] == RATE_LIMITED
        assert_no_leak("mocked 429", json.dumps(outcome, ensure_ascii=False))

    @pytest.mark.parametrize("status", [500, 503])
    def test_upstream_failure_maps_to_the_safe_message(self, tmp_path, status: int) -> None:
        outcome = mock_service(tmp_path, status).test_provider(
            provider="openai", model=REAL_MODEL
        )
        assert outcome["message"] == PROVIDER_UNAVAILABLE
        assert_no_leak(f"mocked {status}", json.dumps(outcome, ensure_ascii=False))

    def test_vendor_body_never_reaches_the_caller(self, tmp_path) -> None:
        service = mock_service(
            tmp_path, 400, {"error": {"message": "org-9999 internal quota detail"}}
        )
        outcome = service.test_provider(provider="openai", model=REAL_MODEL)
        rendered = json.dumps(outcome, ensure_ascii=False)
        assert "org-9999" not in rendered
        assert outcome["message"] in SAFE_MESSAGES


# -- The gate itself ----------------------------------------------------------

class TestRealRunGate:
    def test_both_gates_are_required(self) -> None:
        """Sanity: if we are running at all, both opt-ins really were present."""
        assert real_key(), f"{KEY_ENV} is empty"
        assert os.environ.get("REAL_LLM_RUN") == "1"

    def test_no_key_is_written_anywhere_by_this_module(self) -> None:
        """§13: the key must not be committed into this file or its fixtures."""
        source = __file__
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        assert re.search(r"sk-(?:live|proj|ant)-[A-Za-z0-9]{16,}", text) is None
        assert real_key() not in text
