"""Durable append-only event storage."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Iterable

from .models import Event


class EventStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path_for(self, event: Event) -> Path:
        # One JSONL stream is easier to tail and remains compatible with the
        # requested workspace/events/*.jsonl layout.
        return self.root / "runtime.jsonl"

    def append(self, event: Event) -> Event:
        if not event.is_valid():
            raise ValueError("Cannot persist an event with an invalid checksum")
        path = self._path_for(event)
        line = json.dumps(event.as_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return event

    def _read(self, limit: int | None = None) -> tuple[list[Event], int]:
        path = self.root / "runtime.jsonl"
        if not path.exists():
            return [], 0
        raw_lines = path.read_text(encoding="utf-8").splitlines()
        if limit is not None:
            raw_lines = raw_lines[-limit:]
        events: list[Event] = []
        invalid = 0
        for raw in raw_lines:
            if not raw.strip():
                continue
            try:
                event = Event.from_dict(json.loads(raw))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                invalid += 1
                continue
            if event.is_valid():
                events.append(event)
            else:
                invalid += 1
        return events, invalid

    def list_events(self, limit: int = 100) -> list[Event]:
        return self._read(limit=max(1, limit))[0]

    def recover_events(self) -> dict[str, object]:
        events, invalid = self._read()
        return {"events": events, "valid": invalid == 0, "invalidCount": invalid}

    def all_dicts(self, limit: int = 100) -> list[dict[str, object]]:
        return [event.as_dict() for event in self.list_events(limit)]
