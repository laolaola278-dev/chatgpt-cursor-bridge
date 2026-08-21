from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import AgentProfile


class AgentProfileStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path); self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path), check_same_thread=False); self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (agent_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profile_history (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, profile_json TEXT NOT NULL, recorded_at TEXT NOT NULL);
        """); self.connection.commit()

    def save(self, profile: AgentProfile) -> AgentProfile:
        encoded = json.dumps(profile.as_dict(), ensure_ascii=False)
        self.connection.execute("INSERT OR REPLACE INTO profiles VALUES (?,?,?)", (profile.agent_id, encoded, profile.updated_at))
        self.connection.execute("INSERT INTO profile_history(agent_id,profile_json,recorded_at) VALUES (?,?,?)", (profile.agent_id, encoded, profile.updated_at)); self.connection.commit(); return profile

    def get(self, agent_id: str) -> AgentProfile | None:
        row = self.connection.execute("SELECT profile_json FROM profiles WHERE agent_id=?", (agent_id,)).fetchone()
        if not row: return None
        value = json.loads(row["profile_json"]); return AgentProfile(value["agentId"], value.get("role", "unknown"), value.get("domainScores", {}), float(value.get("successRate", 0)), float(value.get("failureRate", 0)), float(value.get("rollbackRate", 0)), float(value.get("averageQuality", 0)), value.get("weaknesses", []), value.get("strengths", []), value.get("updatedAt", ""))

    def history(self, agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return [json.loads(row["profile_json"]) for row in self.connection.execute("SELECT profile_json FROM profile_history WHERE agent_id=? ORDER BY id DESC LIMIT ?", (agent_id, limit)).fetchall()]

    def list(self) -> list[AgentProfile]:
        result = []
        for row in self.connection.execute("SELECT profile_json FROM profiles ORDER BY agent_id").fetchall():
            value = json.loads(row["profile_json"]); result.append(AgentProfile(value["agentId"], value.get("role", "unknown"), value.get("domainScores", {}), float(value.get("successRate", 0)), float(value.get("failureRate", 0)), float(value.get("rollbackRate", 0)), float(value.get("averageQuality", 0)), value.get("weaknesses", []), value.get("strengths", []), value.get("updatedAt", "")))
        return result
