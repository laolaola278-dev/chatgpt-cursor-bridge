"""JSONL persistence for workflows.

We use a simple append + snapshot strategy: each workflow lives in its own
`<WORKFLOW_ROOT>/<id>.json` file. This keeps human review and Git diffs easy
while avoiding the operational complexity of an extra database.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from typing import Iterable

from app.security.validator import ResourceNotFound

from .models import Workflow, WorkflowStage, WorkflowStatus, StageStatus, StageType


class WorkflowStorage:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, workflow_id: str) -> Path:
        return self._root / f"{workflow_id}.json"

    # -- serialisation --------------------------------------------------

    @staticmethod
    def _to_dict(workflow: Workflow) -> dict:
        return {
            "id": workflow.id,
            "project": workflow.project,
            "name": workflow.name,
            "description": workflow.description,
            "current_stage": workflow.current_stage.value,
            "status": workflow.status.value,
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
            "completed_at": workflow.completed_at,
            "cancelled_reason": workflow.cancelled_reason,
            "stages": [
                {
                    **asdict(stage),
                    "stage_type": stage.stage_type.value,
                    "status": stage.status.value,
                }
                for stage in workflow.stages
            ],
        }

    @staticmethod
    def _from_dict(data: dict) -> Workflow:
        stages = [
            WorkflowStage(
                id=stage["id"],
                workflow_id=stage["workflow_id"],
                stage_type=StageType(stage["stage_type"]),
                status=StageStatus(stage["status"]),
                created_at=stage["created_at"],
                updated_at=stage["updated_at"],
                report=stage.get("report"),
                report_title=stage.get("report_title"),
                approval_request_id=stage.get("approval_request_id"),
                approved_at=stage.get("approved_at"),
                approved_by=stage.get("approved_by"),
                action_ids=list(stage.get("action_ids") or []),
                agent_ids=list(stage.get("agent_ids") or []),
                quality_gate=stage.get("quality_gate"),
            )
            for stage in data.get("stages", [])
        ]
        return Workflow(
            id=data["id"],
            project=data["project"],
            name=data["name"],
            description=data.get("description", ""),
            current_stage=StageType(data["current_stage"]),
            status=WorkflowStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            stages=stages,
            cancelled_reason=data.get("cancelled_reason"),
            completed_at=data.get("completed_at"),
        )

    # -- IO -------------------------------------------------------------

    def save(self, workflow: Workflow) -> None:
        payload = json.dumps(self._to_dict(workflow), ensure_ascii=False, indent=2)
        target = self._path(workflow.id)
        tmp = target.with_suffix(".json.tmp")
        with self._lock:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(target)

    def load(self, workflow_id: str) -> Workflow:
        path = self._path(workflow_id)
        if not path.exists():
            raise ResourceNotFound(f"Workflow '{workflow_id}' was not found")
        with self._lock:
            data = json.loads(path.read_text(encoding="utf-8"))
        return self._from_dict(data)

    def exists(self, workflow_id: str) -> bool:
        return self._path(workflow_id).exists()

    def all(self) -> Iterable[Workflow]:
        with self._lock:
            files = sorted(self._root.glob("*.json"))
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            yield self._from_dict(data)

    def delete(self, workflow_id: str) -> None:
        path = self._path(workflow_id)
        if path.exists():
            path.unlink()
