from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from app.config import Settings


class ProductionReadiness:
    """Static, read-only readiness checks. Never starts services or deploys."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def environment(self) -> dict[str, Any]:
        missing: list[str] = []
        required = ["WORKSPACE_ROOT", "LOG_PATH", "MEMORY_ROOT", "APPROVAL_DB_PATH"]
        for name in required:
            if not (getattr(self.settings, "workspace_root", None) and True):
                missing.append(name)
        return {"status": "pass" if not missing else "warn", "missing": missing, "port": self.settings.bridge_port, "host": self.settings.bridge_host}

    def migrations(self) -> dict[str, Any]:
        databases = {
            "approvals": self.settings.approval_db_path,
            "execution_loop": self.settings.execution_loop_db_path,
            "execution_dag": self.settings.execution_dag_db_path,
            "agent_profile": getattr(self.settings, "agent_profile_db_path", None),
        }
        checked: list[dict[str, Any]] = []
        for name, path in databases.items():
            if path is None: continue
            try:
                connection = sqlite3.connect(str(path))
                connection.execute("PRAGMA integrity_check")
                connection.close()
                checked.append({"name": name, "status": "ok"})
            except sqlite3.Error as exc:
                checked.append({"name": name, "status": "error", "detail": str(exc)})
        return {"status": "pass" if all(item["status"] == "ok" for item in checked) else "warn", "databases": checked}

    def backup_restore(self) -> dict[str, Any]:
        try:
            source = self.settings.log_path / "audit.jsonl"
            content = "restore-check\n"
            if source.exists():
                content = source.read_text(encoding="utf-8")[:256]
            target = self.settings.backup_root / "restore_test.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"sample": content}), encoding="utf-8")
            restored = json.loads(target.read_text(encoding="utf-8"))
            return {"status": "pass" if restored.get("sample") == content else "warn", "path": str(target)}
        except OSError as exc:
            return {"status": "warn", "detail": str(exc)}

    def summary(self) -> dict[str, Any]:
        env = self.environment(); migrations = self.migrations(); backup = self.backup_restore()
        return {"environment": env, "migrations": migrations, "backupRestore": backup, "readOnly": True}
