"""In-process event bus backed by append-only JSONL."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Any, Callable

from app.audit.logger import AuditLogger

from .models import Event, EventType
from .storage import EventStorage

Subscriber = Callable[[Event], None]


class EventBus:
    def __init__(self, storage: EventStorage, audit: AuditLogger | None = None) -> None:
        self.storage = storage
        self.audit = audit
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = Lock()

    def subscribe(self, event_type: str | EventType, callback: Subscriber) -> Callable[[], None]:
        topic = event_type.value if isinstance(event_type, EventType) else event_type
        with self._lock:
            self._subscribers[topic].append(callback)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers.get(topic, []):
                    self._subscribers[topic].remove(callback)

        return unsubscribe

    def publish(
        self,
        event_type: str | EventType,
        *,
        source: str,
        payload: dict[str, Any],
    ) -> Event:
        event = Event.create(event_type, source=source, payload=payload)
        self.storage.append(event)
        if self.audit is not None:
            self.audit.record(
                action="event_published",
                path=event.event_type,
                permission="LEVEL_0",
                approved=True,
                result="success",
                detail=f"{event.event_id} from {source}",
                audit_id=event.audit_id,
            )
        with self._lock:
            callbacks = [*self._subscribers.get(event.event_type, []), *self._subscribers.get("*", [])]
        for callback in callbacks:
            callback(event)
        return event

    def list_events(self, limit: int = 100) -> list[Event]:
        return self.storage.list_events(limit)

    def recover_events(self) -> dict[str, object]:
        return self.storage.recover_events()
