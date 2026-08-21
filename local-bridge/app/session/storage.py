"""File-backed session storage with atomic writes."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from app.security.validator import ResourceNotFound

from .models import Session, SessionStatus


class SessionStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    @staticmethod
    def _from_dict(data: dict) -> Session:
        return Session(
            id=data["id"],
            project=data["project"],
            status=SessionStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            workflow_id=data.get("workflow_id"),
            stage_id=data.get("stage_id"),
            approval_id=data.get("approval_id"),
            history=list(data.get("history") or []),
        )

    @staticmethod
    def _to_dict(session: Session) -> dict:
        return {
            "id": session.id,
            "project": session.project,
            "status": session.status.value,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "workflow_id": session.workflow_id,
            "stage_id": session.stage_id,
            "approval_id": session.approval_id,
            "history": list(session.history),
        }

    def save(self, session: Session) -> None:
        target = self._path(session.id)
        temporary = target.with_suffix(".json.tmp")
        with self._lock:
            temporary.write_text(json.dumps(self._to_dict(session), ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(target)

    def get(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise ResourceNotFound(f"Session '{session_id}' was not found")
        with self._lock:
            return self._from_dict(json.loads(path.read_text(encoding="utf-8")))

    def all(self) -> list[Session]:
        with self._lock:
            paths = sorted(self.root.glob("*.json"))
        sessions: list[Session] = []
        for path in paths:
            try:
                sessions.append(self._from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError):
                continue
        return sessions
