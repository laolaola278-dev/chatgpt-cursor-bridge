"""Atomic JSON and append-only JSONL storage for collaboration metadata."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.security.validator import ResourceNotFound

from .models import AgentTeam, AgentTeamStatus, CollaborationMessage, ConflictRecord


class CollaborationStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.teams = self.root / "teams"; self.teams.mkdir(exist_ok=True)
        self.messages_path = self.root / "messages.jsonl"
        self.conflicts_path = self.root / "conflicts.jsonl"
        self._lock = Lock()

    def save_team(self, team: AgentTeam) -> AgentTeam:
        target = self.teams / f"{team.id}.json"; temp = target.with_suffix(".tmp")
        with self._lock:
            temp.write_text(json.dumps(team.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"); temp.replace(target)
        return team

    @staticmethod
    def _team(data: dict[str, Any]) -> AgentTeam:
        return AgentTeam(data["id"], data["workflowId"], list(data["members"]), data["leader"], AgentTeamStatus(data["status"]), data["createdAt"], data["updatedAt"], list(data.get("history", [])))

    def get_team(self, team_id: str) -> AgentTeam:
        path = self.teams / f"{team_id}.json"
        if not path.exists(): raise ResourceNotFound(f"Agent team '{team_id}' was not found")
        try: return self._team(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError) as exc: raise ValueError(f"Agent team '{team_id}' is corrupted") from exc

    def list_teams(self, workflow_id: str | None = None) -> list[AgentTeam]:
        result: list[AgentTeam] = []
        for path in sorted(self.teams.glob("team_*.json")):
            try:
                team = self._team(json.loads(path.read_text(encoding="utf-8")))
                if workflow_id is None or team.workflow_id == workflow_id: result.append(team)
            except (OSError, ValueError, KeyError): continue
        return sorted(result, key=lambda item: item.updated_at, reverse=True)

    def append_message(self, message: CollaborationMessage) -> CollaborationMessage:
        with self._lock:
            with self.messages_path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(message.as_dict(), ensure_ascii=False) + "\n")
        return message

    def list_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.messages_path.exists(): return []
        records: list[dict[str, Any]] = []
        for line in self.messages_path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 500)):]:
            try: records.append(json.loads(line))
            except json.JSONDecodeError: continue
        return records

    def append_conflict(self, conflict: ConflictRecord) -> ConflictRecord:
        with self._lock:
            with self.conflicts_path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(conflict.as_dict(), ensure_ascii=False) + "\n")
        return conflict

    def list_conflicts(self, limit: int = 100) -> list[ConflictRecord]:
        if not self.conflicts_path.exists(): return []
        records: list[ConflictRecord] = []
        for line in self.conflicts_path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 500)):]:
            try:
                value = json.loads(line); records.append(ConflictRecord(value["id"], value["workflowId"], value["taskId"], list(value["agents"]), value["issue"], list(value["options"]), value.get("resolution"), value["status"], value["createdAt"], value.get("resolvedAt")))
            except (json.JSONDecodeError, KeyError, TypeError): continue
        return records

    def get_conflict(self, conflict_id: str) -> ConflictRecord:
        for item in reversed(self.list_conflicts(500)):
            if item.id == conflict_id: return item
        raise ResourceNotFound(f"Conflict '{conflict_id}' was not found")
