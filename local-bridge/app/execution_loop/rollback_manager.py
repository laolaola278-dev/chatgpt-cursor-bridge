from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

from app.config import Settings
from app.security.sandbox import validate_path
from app.security.validator import ResourceNotFound, ValidationFailed

from .models import ExecutionLoop


class ExecutionLoopRollbackManager:
    """Restore loop snapshots in reverse execution order.

    Restoration is approval-gated at the API level; this class performs the
    deterministic restore only after an explicit human approval.
    """

    def __init__(self, settings: Settings, snapshot_root: Path | None = None) -> None:
        self.settings = settings
        self.snapshot_root = snapshot_root or (settings.workspace_root.parent / "execution_snapshots")

    def collect_snapshots(self, loop: ExecutionLoop) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for task_id in loop.task_ids:
            segment = loop.workflow_id or "standalone"
            metadata = self.snapshot_root / segment / task_id / "metadata.json"
            if metadata.is_file():
                snapshots.append(json.loads(metadata.read_text(encoding="utf-8")))
        if not snapshots:
            raise ResourceNotFound("No execution snapshots exist for this loop; rollback is unavailable")
        snapshots.sort(key=lambda item: int(item.get("capturedAt", 0)), reverse=True)
        return snapshots

    def preview(self, loop: ExecutionLoop) -> dict[str, Any]:
        snapshots = self.collect_snapshots(loop)
        return {
            "loopId": loop.id,
            "snapshots": len(snapshots),
            "files": [
                {"taskId": item["taskId"], "path": file["path"], "existed": file["existed"]}
                for item in snapshots
                for file in item.get("files", [])
            ],
            "order": "reverse_execution_order",
        }

    def restore(self, loop: ExecutionLoop) -> dict[str, Any]:
        snapshots = self.collect_snapshots(loop)
        restored: list[str] = []
        git_head: str | None = None
        for item in snapshots:
            for file in item.get("files", []):
                target = validate_path(loop.project, file["path"], self.settings)
                if file.get("existed"):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(base64.b64decode(file["contentBase64"]))
                elif target.exists():
                    target.unlink()
                restored.append(file["path"])
            if git_head is None and item.get("gitHead"):
                git_head = item["gitHead"]
        if git_head:
            self._reset_git(loop.project, git_head)
        return {
            "loopId": loop.id,
            "restoredFiles": list(dict.fromkeys(restored)),
            "gitResetTo": git_head,
            "count": len(restored),
            "order": "reverse_execution_order",
        }

    def _reset_git(self, project: str, git_head: str) -> None:
        from app.security.sandbox import get_project_dir

        root = get_project_dir(project, self.settings)
        if not (root / ".git").exists():
            return
        result = subprocess.run(
            ["git", "reset", "--mixed", git_head],
            cwd=str(root),
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise ValidationFailed(result.stderr.strip() or "Git reset failed during loop rollback")
