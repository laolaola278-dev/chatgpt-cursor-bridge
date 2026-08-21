from __future__ import annotations

import re

from app.security.validator import ValidationFailed

from .models import ExecutionTask


class ImplementationTaskBuilder:
    """Convert an Engineering Plan (metadata) into implementation task drafts.

    The builder is purely deterministic: it never opens project files and never
    mutates anything. It only splits plan text into bounded task proposals.
    """

    SECTION_HEADINGS = (
        "## Problem",
        "## Current State",
        "## Selected Scenario",
        "## Files",
        "## Implementation Steps",
        "## Testing Plan",
        "## Rollback Plan",
        "## Risks",
    )

    @staticmethod
    def _extract_files(plan_content: str) -> list[str]:
        files: list[str] = []
        in_files = False
        for raw in plan_content.splitlines():
            line = raw.strip()
            if line.startswith("## "):
                in_files = line == "## Files"
                continue
            if not in_files:
                continue
            match = re.match(r"^- `([^`]+)`$", line)
            if match:
                files.append(match.group(1))
        return list(dict.fromkeys(files))

    @staticmethod
    def _extract_steps(plan_content: str) -> list[str]:
        steps: list[str] = []
        in_steps = False
        for raw in plan_content.splitlines():
            line = raw.strip()
            if line.startswith("## "):
                in_steps = line == "## Implementation Steps"
                continue
            if not in_steps:
                continue
            match = re.match(r"^\d+\.\s+(.+)$", line)
            if match:
                steps.append(match.group(1))
        return steps

    def build(self, *, plan_id: str, project: str, workflow_id: str | None, plan_content: str) -> list[ExecutionTask]:
        if not plan_content.strip():
            raise ValidationFailed("Cannot build tasks from an empty engineering plan")
        files = self._extract_files(plan_content)
        if not files:
            raise ValidationFailed("Engineering plan must list at least one affected file")
        steps = self._extract_steps(plan_content)
        if not steps:
            raise ValidationFailed("Engineering plan must contain implementation steps")
        tasks = []
        for zero_index, step in enumerate(steps):
            task_index = zero_index + 1
            risk_score = 25 + min(40, task_index * 5)
            risk = "low" if risk_score < 35 else "medium" if risk_score < 60 else "high"
            task = ExecutionTask(
                id=f"et_{plan_id[4:12]}_{task_index}" if len(plan_id) >= 12 else f"et_{task_index}",
                workflow_id=workflow_id,
                plan_id=plan_id,
                project=project,
                title=step,
                task_type="implementation",
                files=files,
                dependencies=[steps[other] for other in range(len(steps)) if other != zero_index],
                risk=risk,
                risk_score=risk_score,
            )
            tasks.append(task)
        return tasks
