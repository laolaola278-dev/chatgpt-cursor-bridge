"""Small, dependency-free maintenance services used by the bridge.

Maintenance is deliberately best-effort: a bad optional artifact is quarantined
rather than allowed to prevent the read-only service from starting. Backups are
snapshots for recovery and inspection; they are never an execution path.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit.logger import AuditLogger
from app.config import Settings
from app.context.intelligence import ContextIndex
from app.security.permissions import ApprovalStore


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class RecoveryManager:
    """Detect malformed persisted JSON/JSONL and quarantine it on startup."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _quarantine(self, path: Path) -> Path:
        recovery = self._settings.backup_root / "recovery"
        recovery.mkdir(parents=True, exist_ok=True)
        target = recovery / f"{path.name}.{_stamp()}.corrupt"
        path.replace(target)
        return target

    def _check_json_files(self, root: Path) -> tuple[int, int]:
        checked = 0
        recovered = 0
        if not root.exists():
            return checked, recovered
        for path in sorted(root.rglob("*.json")):
            if "recovery" in path.parts:
                continue
            checked += 1
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                self._quarantine(path)
                recovered += 1
        return checked, recovered

    def _check_context_snapshots(self) -> tuple[int, int]:
        return self._check_json_files(self._settings.context_root)

    def _check_audit(self) -> tuple[int, int]:
        path = self._settings.audit_log_file
        if not path.exists():
            return 0, 0
        checked = 0
        invalid = 0
        valid_lines: list[str] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            checked += 1
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                invalid += 1
                continue
            valid_lines.append(raw)
        if invalid:
            quarantine = self._quarantine(path)
            # Preserve the bad original in recovery and restore a valid JSONL stream.
            _atomic_text(path, "\n".join(valid_lines) + ("\n" if valid_lines else ""))
            _atomic_json(
                self._settings.backup_root / "recovery" / f"{quarantine.name}.report.json",
                {"invalidLines": invalid, "recoveredAt": datetime.now(timezone.utc).isoformat()},
            )
        return checked, invalid

    def run(self) -> dict[str, Any]:
        workflow_checked, workflow_recovered = self._check_json_files(self._settings.workflow_root)
        agent_checked, agent_recovered = self._check_json_files(self._settings.agent_root)
        context_checked, context_recovered = self._check_context_snapshots()
        audit_checked, audit_recovered = self._check_audit()
        return {
            "status": "recovered" if workflow_recovered or agent_recovered or context_recovered or audit_recovered else "ok",
            "workflowFilesChecked": workflow_checked,
            "workflowFilesRecovered": workflow_recovered,
            "agentFilesChecked": agent_checked,
            "agentFilesRecovered": agent_recovered,
            "contextFilesChecked": context_checked,
            "contextFilesRecovered": context_recovered,
            "auditLinesChecked": audit_checked,
            "auditLinesRecovered": audit_recovered,
        }


class BackupManager:
    """Copy memory, workflow and approval state into a timestamped snapshot."""

    def __init__(self, settings: Settings, approvals: ApprovalStore) -> None:
        self._settings = settings
        self._approvals = approvals

    def create_backup(self, *, reason: str = "scheduled") -> Path:
        target = self._settings.backup_root / f"backup-{_stamp()}"
        target.mkdir(parents=True, exist_ok=False)
        memory_target = target / "memory"
        workflow_target = target / "workflows"
        agent_target = target / "agents"
        if self._settings.memory_root.exists():
            shutil.copytree(self._settings.memory_root, memory_target, dirs_exist_ok=True)
        else:
            memory_target.mkdir()
        workflow_target.mkdir(parents=True, exist_ok=True)
        for source in self._settings.workflow_root.glob("*.json"):
            shutil.copy2(source, workflow_target / source.name)
        if self._settings.agent_root.exists():
            shutil.copytree(self._settings.agent_root, agent_target, dirs_exist_ok=True)
        else:
            agent_target.mkdir(parents=True, exist_ok=True)
        _atomic_json(
            target / "approvals.json",
            {
                "warning": "Approval records are for recovery/audit only; no request is auto-executed.",
                "requests": self._approvals.snapshot(),
            },
        )
        _atomic_json(
            target / "metadata.json",
            {"createdAt": datetime.now(timezone.utc).isoformat(), "reason": reason},
        )
        return target

    def latest_backup(self) -> Path | None:
        backups = [path for path in self._settings.backup_root.glob("backup-*") if path.is_dir()]
        return max(backups, key=lambda path: path.stat().st_mtime, default=None)

    def maybe_backup(self, *, force: bool = False) -> Path | None:
        latest = self.latest_backup()
        if not force and latest is not None:
            age = datetime.now(timezone.utc).timestamp() - latest.stat().st_mtime
            if age < self._settings.backup_interval_seconds:
                return None
        return self.create_backup(reason="startup" if force else "scheduled")


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class MaintenanceService:
    """Coordinates recovery, scheduled backups and health probes."""

    def __init__(
        self,
        settings: Settings,
        approvals: ApprovalStore,
        audit: AuditLogger | None = None,
    ) -> None:
        self.recovery = RecoveryManager(settings)
        self.backups = BackupManager(settings, approvals)
        self._settings = settings
        self._audit = audit
        self._startup_report: dict[str, Any] | None = None

    def startup(self) -> dict[str, Any]:
        self._startup_report = self.recovery.run()
        # Opening the index at startup makes the durable intelligence store
        # part of the health contract without changing Memory.
        ContextIndex(self._settings.context_index_db_path).close()
        recovered = self.backups._approvals.recover_pending(self._audit)
        self._startup_report["approvalsRecovered"] = len(recovered)
        self.backups.maybe_backup(force=True)
        return self._startup_report

    def on_request(self) -> None:
        # This is a cheap mtime check and provides periodic backup semantics
        # without adding a scheduler thread or another execution entry point.
        self.backups.maybe_backup()

    @property
    def startup_report(self) -> dict[str, Any]:
        return self._startup_report or {"status": "not_started"}

    def health(self) -> dict[str, Any]:
        checks: dict[str, dict[str, Any]] = {}
        checks["memory"] = self._directory_check(self._settings.memory_root)
        checks["workspace"] = self._directory_check(self._settings.workspace_root)
        checks["workflow"] = self._directory_check(self._settings.workflow_root)
        checks["database"] = self._database_check()
        checks["approval"] = {
            "status": "ok",
            "pending": len(self.backups._approvals.list_pending()),
            "durability": "SQLite-backed; recovered requests require explicit reconfirmation",
        }
        overall = "ok" if all(item["status"] == "ok" for item in checks.values()) else "degraded"
        return {
            "status": overall,
            "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "checks": checks,
            "recovery": self.startup_report,
            "latestBackup": str(self.backups.latest_backup()) if self.backups.latest_backup() else None,
        }

    @staticmethod
    def _directory_check(path: Path) -> dict[str, Any]:
        return {"status": "ok" if path.is_dir() else "error", "path": str(path)}

    def _database_check(self) -> dict[str, Any]:
        databases = sorted(self._settings.memory_root.glob("*/memory.db"))
        corrupt: list[str] = []
        for path in databases:
            try:
                with sqlite3.connect(path) as connection:
                    result = connection.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    corrupt.append(str(path))
            except sqlite3.Error:
                corrupt.append(str(path))
        return {
            "status": "error" if corrupt else "ok",
            "databaseCount": len(databases),
            "corrupt": corrupt,
        }
