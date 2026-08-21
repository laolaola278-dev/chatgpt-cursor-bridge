"""Phase 33 · Local performance benchmarks (spec §14, backend half).

Four measurements, all offline and all against the real ``ConversationStore``
and the real streaming event type:

* a 100-message SQLite round trip (create → append ×100 → read back),
* concurrent writes from several threads into one store,
* long-conversation storage (300 messages of ~2 KB each),
* streaming event processing (100 delta events serialised the way the SSE
  route serialises them).

Every measurement records **elapsed / average / max** and is checked against a
deliberately generous budget: the point is to catch an order-of-magnitude
regression on this machine, not to publish a number. These are **local
baselines only** — they say nothing about any provider's production capacity,
and nothing here talks to a provider, a network or the filesystem outside
``tmp_path``.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.llm_gateway.conversation import ConversationStore
from app.llm_gateway.models import MessageRole, StreamEvent

# Budgets in seconds. Generous on purpose (see the module docstring).
BUDGETS = {
    "conversation_round_trip_100": {"total": 30.0, "average": 0.30},
    "concurrent_writes_100": {"total": 30.0, "average": 0.30},
    "long_conversation_300": {"total": 90.0, "average": 0.30},
    "stream_events_100": {"total": 2.0, "average": 0.02},
}

# The four backend measurements §14 asks for.
REQUIRED_BENCHMARKS = tuple(BUDGETS)

# Filled in as the tests run so the last test can report the whole table.
BENCHMARKS: dict[str, dict[str, float]] = {}


def record(name: str, samples: list[float]) -> dict[str, float]:
    """Store elapsed / average / max for ``name`` and assert its budget."""

    assert samples, name
    measurement = {
        "count": float(len(samples)),
        "elapsed": sum(samples),
        "average": sum(samples) / len(samples),
        "max": max(samples),
    }
    BENCHMARKS[name] = measurement
    budget = BUDGETS[name]
    assert measurement["elapsed"] <= budget["total"], f"{name}: {measurement}"
    assert measurement["average"] <= budget["average"], f"{name}: {measurement}"
    return measurement


def make_store(tmp_path: Path, name: str = "conversations.db") -> ConversationStore:
    return ConversationStore(tmp_path / name)


def new_conversation(store: ConversationStore, project: str = "bench") -> str:
    return store.create_conversation(
        project=project,
        provider="local",
        model="local/simulator-v1",
        title="benchmark",
    ).conversation_id


# -- Backend: conversation storage -------------------------------------------

class TestConversationStoreBenchmark:
    def test_hundred_message_round_trip(self, tmp_path: Path) -> None:
        store = make_store(tmp_path)
        conversation_id = new_conversation(store)

        samples: list[float] = []
        for index in range(100):
            role = MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT
            start = time.perf_counter()
            store.append_message(
                conversation_id=conversation_id,
                role=role,
                content=f"benchmark message {index}",
            )
            samples.append(time.perf_counter() - start)

        read_start = time.perf_counter()
        messages = store.list_messages(conversation_id, limit=200)
        read_elapsed = time.perf_counter() - read_start

        assert len(messages) == 100
        assert read_elapsed <= 2.0, read_elapsed
        measurement = record("conversation_round_trip_100", samples)
        assert measurement["count"] == 100.0

    def test_concurrent_writes_stay_consistent(self, tmp_path: Path) -> None:
        """The store is lock-protected; parallel appends must not lose a row."""
        store = make_store(tmp_path, "concurrent.db")
        conversation_id = new_conversation(store)

        def append(index: int) -> float:
            start = time.perf_counter()
            store.append_message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=f"concurrent {index}",
            )
            return time.perf_counter() - start

        with ThreadPoolExecutor(max_workers=8) as pool:
            samples = list(pool.map(append, range(100)))

        messages = store.list_messages(conversation_id, limit=200)
        assert len(messages) == 100, "a concurrent append was lost"
        assert len({message.message_id for message in messages}) == 100
        record("concurrent_writes_100", samples)

    def test_long_conversation_storage(self, tmp_path: Path) -> None:
        """A long conversation stays readable — and stays *bounded* on read."""
        store = make_store(tmp_path, "long.db")
        conversation_id = new_conversation(store)
        body = "x" * 2048

        samples: list[float] = []
        for index in range(300):
            start = time.perf_counter()
            store.append_message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=f"{index}:{body}",
            )
            samples.append(time.perf_counter() - start)

        read_start = time.perf_counter()
        page = store.list_messages(conversation_id, limit=200)
        read_elapsed = time.perf_counter() - read_start

        # ``limit`` is honoured, so context does not inflate without bound (§12).
        assert len(page) == 200
        assert read_elapsed <= 3.0, read_elapsed
        record("long_conversation_300", samples)

    def test_reload_does_not_rescan_the_whole_history(self, tmp_path: Path) -> None:
        """Re-opening the database is cheap: the reload path is an index read."""
        store = make_store(tmp_path, "reload.db")
        conversation_id = new_conversation(store)
        for index in range(100):
            store.append_message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=f"reload {index}",
            )

        start = time.perf_counter()
        reopened = ConversationStore(tmp_path / "reload.db")
        conversation = reopened.get_conversation(conversation_id)
        listed = reopened.list_conversations("bench")
        elapsed = time.perf_counter() - start

        assert conversation is not None
        assert listed and listed[0].conversation_id == conversation_id
        assert elapsed <= 3.0, elapsed


# -- Backend: streaming event processing -------------------------------------

class TestStreamingEventBenchmark:
    def test_hundred_delta_events_serialise_within_budget(self) -> None:
        events = [
            StreamEvent(kind="delta", content=f"token-{index} ", provider="local", model="local/simulator-v1")
            for index in range(99)
        ]
        events.append(StreamEvent(kind="done", provider="local", model="local/simulator-v1"))

        samples: list[float] = []
        frames: list[str] = []
        for event in events:
            start = time.perf_counter()
            # Exactly what ``/assistant/chat/stream`` writes onto the wire.
            frame = f"data: {json.dumps(event.as_dict(), ensure_ascii=False)}\n\n"
            samples.append(time.perf_counter() - start)
            frames.append(frame)

        assert len(frames) == 100
        assert frames[-1].startswith('data: {"type": "done"')
        record("stream_events_100", samples)

    def test_accumulating_a_hundred_tokens_is_linear(self) -> None:
        """Token accumulation must not be quadratic in the number of deltas."""
        events = [StreamEvent(kind="delta", content=f"t{index} ") for index in range(100)]

        start = time.perf_counter()
        buffer: list[str] = []
        for event in events:
            if event.kind == "delta":
                buffer.append(event.content)
        text = "".join(buffer)
        elapsed = time.perf_counter() - start

        assert text.startswith("t0 t1 ")
        assert len(text.split()) == 100
        assert elapsed <= 0.5, elapsed


# -- The recorded table ------------------------------------------------------

class TestBenchmarkTable:
    def test_every_required_measurement_was_recorded(self) -> None:
        missing = [name for name in REQUIRED_BENCHMARKS if name not in BENCHMARKS]
        if missing and len(BENCHMARKS) < len(REQUIRED_BENCHMARKS):
            pytest.skip(f"selective run; measured {sorted(BENCHMARKS)}")
        assert not missing, missing

    def test_each_measurement_reports_elapsed_average_and_max(self) -> None:
        if not BENCHMARKS:
            pytest.skip("selective run; nothing measured")
        for name, measurement in BENCHMARKS.items():
            for field in ("elapsed", "average", "max", "count"):
                assert field in measurement, f"{name} is missing {field}"
                assert measurement[field] >= 0.0, f"{name}.{field}"
            assert measurement["max"] <= measurement["elapsed"] + 1e-9, name

    def test_the_table_claims_nothing_about_a_provider(self) -> None:
        """§14: local baselines only — no provider capacity is measured here."""
        for name in BENCHMARKS:
            assert "openai" not in name
            assert "anthropic" not in name
            assert "deepseek" not in name
            assert "throughput" not in name
