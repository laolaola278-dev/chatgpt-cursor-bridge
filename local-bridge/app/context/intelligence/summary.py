"""Small deterministic helpers for selecting useful project context."""

from __future__ import annotations

from typing import Any


class ContextCompressor:
    """Keep context responses bounded without changing source-of-truth files."""

    def __init__(self, *, max_items: int = 20, max_text: int = 2000) -> None:
        self.max_items = max_items
        self.max_text = max_text

    def compress(self, context: dict[str, Any]) -> dict[str, Any]:
        result = dict(context)
        for key in ("recentDecisions", "openTasks", "pendingApprovals", "recentChanges"):
            value = result.get(key)
            if isinstance(value, list):
                result[key] = value[-self.max_items :]
        for key in ("recentErrors",):
            value = result.get(key)
            if isinstance(value, list):
                result[key] = value[-10:]
        return result

    def excerpt(self, value: Any) -> str:
        text = str(value or "").strip()
        return text if len(text) <= self.max_text else text[: self.max_text] + "…"


class ContextSummaryGenerator:
    """Generate a stable, human-readable summary from read-only context."""

    def __init__(self, compressor: ContextCompressor | None = None) -> None:
        self.compressor = compressor or ContextCompressor()

    def generate(self, context: dict[str, Any]) -> str:
        context = self.compressor.compress(context)
        workflow = context.get("currentWorkflow") or {}
        stage = context.get("currentStage") or {}
        workflow_name = workflow.get("name") or "No active workflow"
        workflow_status = workflow.get("status") or "—"
        stage_name = stage.get("stageType") or workflow.get("currentStage") or "—"
        tasks = len(context.get("openTasks") or [])
        decisions = len(context.get("recentDecisions") or [])
        approvals = len(context.get("pendingApprovals") or [])
        test = (context.get("lastTestResult") or {}).get("status", "no result")
        return (
            f"{context.get('project', 'project')}: {workflow_name} ({workflow_status}); "
            f"stage {stage_name}; {tasks} open task(s), {decisions} recent decision(s), "
            f"{approvals} pending approval(s), latest test {test}."
        )
