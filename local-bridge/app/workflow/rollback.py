"""Stage-level rollback snapshots and reverse restoration.

Snapshots are captured immediately before an approved action executes. A stage
rollback is itself a LEVEL_1 approval action; no restore occurs at preview time.
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.security.permissions import ApprovalRequest
from app.security.sandbox import get_project_dir, validate_memory_path, validate_path
from app.security.validator import ResourceNotFound, ValidationFailed

FILE_ACTIONS = {"file_create", "file_write", "patch_apply"}
MEMORY_ACTIONS = {"memory_append", "memory_decision"}


class RollbackManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _stage_dir(self, workflow_id: str, stage_id: str) -> Path:
        target = self._settings.rollback_root / workflow_id / stage_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _snapshot_path(self, request: ApprovalRequest) -> Path:
        if not request.workflow_id or not request.stage_id:
            raise ValidationFailed("Rollback snapshot requires workflow and stage binding")
        return self._stage_dir(request.workflow_id, request.stage_id) / f"{request.request_id}.json"

    def capture(self, request: ApprovalRequest) -> None:
        """Capture pre-execution state; idempotent per request."""
        if not request.workflow_id or not request.stage_id:
            return
        target = self._snapshot_path(request)
        if target.exists():
            return
        snapshot: dict[str, Any] = {
            "requestId": request.request_id,
            "action": request.action,
            "project": request.project,
            "path": request.path,
            "capturedAt": time.time_ns(),
        }
        if request.action in FILE_ACTIONS:
            file_path = validate_path(request.project, request.path, self._settings)
            snapshot.update(self._capture_file(file_path))
        elif request.action in MEMORY_ACTIONS:
            document = request.payload.get("document", "decisions.md")
            file_path = validate_memory_path(
                request.project, document, self._settings, create_dir=True
            )
            snapshot.update(self._capture_file(file_path))
            snapshot["memoryDocument"] = document
        elif request.action == "git_commit":
            root = get_project_dir(request.project, self._settings)
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True,
                text=True, shell=False, check=False, timeout=30
            )
            snapshot["gitHead"] = result.stdout.strip() if result.returncode == 0 else None
        else:
            return
        target.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    @staticmethod
    def _capture_file(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"existed": False, "contentBase64": None}
        if not path.is_file():
            raise ValidationFailed("Rollback target is not a regular file")
        return {
            "existed": True,
            "contentBase64": base64.b64encode(path.read_bytes()).decode("ascii"),
        }

    def preview(self, workflow_id: str, stage_id: str) -> dict[str, Any]:
        stage_dir = self._settings.rollback_root / workflow_id / stage_id
        snapshots = []
        if stage_dir.is_dir():
            snapshots = self._ordered_snapshots(stage_dir)
        if not snapshots:
            raise ResourceNotFound("No rollback snapshots exist for this stage")
        return {
            "workflowId": workflow_id,
            "stageId": stage_id,
            "actions": [
                {"requestId": item["requestId"], "action": item["action"], "path": item["path"]}
                for item in snapshots
            ],
            "count": len(snapshots),
        }

    def restore(self, workflow_id: str, stage_id: str) -> dict[str, Any]:
        preview = self.preview(workflow_id, stage_id)
        stage_dir = self._settings.rollback_root / workflow_id / stage_id
        restored: list[str] = []
        failed: list[dict[str, str]] = []
        for item in self._ordered_snapshots(stage_dir):
            try:
                self._restore_one(item)
                restored.append(item["requestId"])
            except Exception as exc:  # continue restoring earlier actions
                failed.append({"requestId": item["requestId"], "error": str(exc)})
        if failed:
            raise ValidationFailed(f"Rollback partially failed: {failed}")
        return {
            "workflowId": workflow_id,
            "stageId": stage_id,
            "restoredActions": restored,
            "count": len(restored),
            "size": len(restored),
            "preview": preview,
        }

    @staticmethod
    def _ordered_snapshots(stage_dir: Path) -> list[dict[str, Any]]:
        """Order newest captures first, independent of coarse filesystem mtimes."""
        snapshots: list[tuple[int, int, dict[str, Any]]] = []
        for path in stage_dir.glob("*.json"):
            item = json.loads(path.read_text(encoding="utf-8"))
            captured = int(item.get("capturedAt", 0))
            snapshots.append((captured, path.stat().st_mtime_ns, item))
        snapshots.sort(key=lambda value: (value[0], value[1]), reverse=True)
        return [item for _, _, item in snapshots]

    def _restore_one(self, item: dict[str, Any]) -> None:
        action = item["action"]
        if action in FILE_ACTIONS:
            target = validate_path(item["project"], item["path"], self._settings)
            self._restore_file(target, item)
        elif action in MEMORY_ACTIONS:
            target = validate_memory_path(
                item["project"], item["memoryDocument"], self._settings, create_dir=True
            )
            self._restore_file(target, item)
        elif action == "git_commit" and item.get("gitHead"):
            root = get_project_dir(item["project"], self._settings)
            result = subprocess.run(
                ["git", "reset", "--mixed", item["gitHead"]], cwd=str(root),
                capture_output=True, text=True, shell=False, check=False, timeout=30
            )
            if result.returncode != 0:
                raise ValidationFailed(result.stderr.strip() or "Git reset failed")

    @staticmethod
    def _restore_file(target: Path, item: dict[str, Any]) -> None:
        if item.get("existed"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(item["contentBase64"]))
        elif target.exists():
            target.unlink()
