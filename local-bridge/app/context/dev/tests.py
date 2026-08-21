"""Read-only test / build context.

Surfaces the last recorded test result (from workflow TESTING stages) and a
best-effort build status derived from recorded implementation/delivery reports
and the latest workflow state. It never executes tests or builds.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.workflow.manager import WorkflowManager
from app.workflow.models import StageStatus, StageType


class TestBuildContextService:
    def __init__(self, settings: Settings, workflow_manager: WorkflowManager) -> None:
        self._settings = settings
        self._workflows = workflow_manager

    def build(self, project: str) -> dict[str, Any]:
        workflow = self._latest_workflow(project)
        return {"testStatus": self._last_test(workflow), "buildStatus": self._build_status(workflow)}

    def _latest_workflow(self, project: str) -> Any | None:
        try:
            summaries = self._workflows.list()
        except Exception:
            return None
        for summary in summaries:
            if getattr(summary, "project", None) != project:
                continue
            try:
                return self._workflows.get(summary.id)
            except Exception:
                continue
        return None

    @staticmethod
    def _last_test(workflow: Any | None) -> dict[str, Any] | None:
        if workflow is None:
            return None
        stages = getattr(workflow, "stages", []) or []
        for stage in reversed(stages):
            if stage.stage_type is not StageType.TESTING:
                continue
            report = (stage.report or "").strip()
            if not report:
                continue
            verdict = "passed" if re.search(r"\bpassed\b", report, re.IGNORECASE) else "failed"
            return {
                "status": verdict,
                "stageId": stage.id,
                "command": (stage.report_title or "").replace("Testing Report — ", ""),
                "updatedAt": stage.updated_at,
                "excerpt": report[:2000],
            }
        return None

    @staticmethod
    def _build_status(workflow: Any | None) -> dict[str, Any] | None:
        if workflow is None:
            return None
        stages = getattr(workflow, "stages", []) or []
        build_stages = [
            stage for stage in stages
            if stage.stage_type in {StageType.IMPLEMENTATION, StageType.DELIVERY}
            and stage.status in {StageStatus.REPORTED, StageStatus.APPROVED}
        ]
        if not build_stages:
            return {"status": "unknown", "message": "No recorded build output yet"}
        latest = build_stages[-1]
        report = (latest.report or "").strip()
        status = "passed" if report and re.search(r"\b(passed|success|built)\b", report, re.IGNORECASE) else "unknown"
        return {"status": status, "stageId": latest.id, "stageType": latest.stage_type.value, "updatedAt": latest.updated_at, "excerpt": report[:2000]}
