"""Workflow execution helpers.

Two responsibilities:

1. Handle the special approval action ``workflow_stage_approval`` — resolving
   a stage approval delegates back to :class:`WorkflowManager` and returns a
   summary result to the audit log.
2. Suggest and queue memory writes (tasks.md, changelog.md, architecture.md,
   decisions.md) as regular approval requests, so the approval system stays
   the single execution entry point.
"""

from __future__ import annotations

from typing import Any

from app.memory.manager import MemoryManager
from app.memory.models import DecisionInput, MemoryDocument
from app.security.permissions import ApprovalStore

from .models import StageType, Workflow, WorkflowStage
from .stages import REQUIRED_SECTIONS


#: Which stage suggests which memory documents.
STAGE_MEMORY_MAP: dict[StageType, tuple[MemoryDocument, ...]] = {
    StageType.REQUIREMENT: (MemoryDocument.PROJECT, MemoryDocument.TASKS),
    StageType.ANALYSIS: (MemoryDocument.TASKS,),
    StageType.ARCHITECTURE: (MemoryDocument.ARCHITECTURE, MemoryDocument.DECISIONS),
    StageType.IMPLEMENTATION: (MemoryDocument.CHANGELOG, MemoryDocument.TASKS),
    StageType.TESTING: (MemoryDocument.CHANGELOG,),
    StageType.DEBUG: (MemoryDocument.CHANGELOG,),
    StageType.DELIVERY: (MemoryDocument.CHANGELOG, MemoryDocument.TASKS),
}


def stage_execution_summary(
    workflow: Workflow,
    stage: WorkflowStage,
    approved: bool,
    approved_actions: list[str],
) -> dict[str, Any]:
    """Result payload returned to the caller of /permission/approve."""
    return {
        "workflowId": workflow.id,
        "stageId": stage.id,
        "stageType": stage.stage_type.value,
        "workflowStatus": workflow.status.value,
        "currentStage": workflow.current_stage.value,
        "approved": approved,
        "approvedActions": approved_actions,
        "size": len(approved_actions),
    }


def build_stage_memory_writes(
    workflow: Workflow, stage: WorkflowStage
) -> list[dict[str, Any]]:
    """Suggest memory append operations for a completed stage.

    The caller queues each entry through the normal ``/memory/append`` (or
    ``/memory/decision``) endpoint so that user approval is still required.
    """
    if not stage.report:
        return []

    suggestions: list[dict[str, Any]] = []
    documents = STAGE_MEMORY_MAP.get(stage.stage_type, ())
    header = (
        f"### Workflow {workflow.name} — {stage.stage_type.value}\n\n"
        f"Stage: `{stage.id}` | Workflow: `{workflow.id}`\n\n"
    )
    body = header + (stage.report_title or "") + "\n\n" + stage.report

    for document in documents:
        if document is MemoryDocument.DECISIONS:
            # Decisions must be structured, not free-form appended.
            decision = _extract_decision(workflow, stage)
            if decision is not None:
                suggestions.append(
                    {
                        "action": "memory_decision",
                        "document": document.value,
                        "payload": {
                            "title": decision.title,
                            "context": decision.context,
                            "decision": decision.decision,
                            "consequence": decision.consequence,
                        },
                    }
                )
            continue
        suggestions.append(
            {
                "action": "memory_append",
                "document": document.value,
                "payload": {"content": body},
            }
        )
    return suggestions


def _extract_decision(
    workflow: Workflow, stage: WorkflowStage
) -> DecisionInput | None:
    """Best-effort ADR extraction from an ARCHITECTURE report."""
    if stage.stage_type is not StageType.ARCHITECTURE or not stage.report:
        return None

    sections = _sections(stage.report)
    tech = sections.get("technology")
    modules = sections.get("modules")
    risks = sections.get("risks")
    tradeoffs = sections.get("trade-offs")

    if not (tech and modules and risks and tradeoffs):
        return None

    title = stage.report_title or f"Architecture for {workflow.name}"
    context = f"Modules:\n{modules}\n\nRisks:\n{risks}"
    decision = f"Adopt technology stack:\n{tech}"
    consequence = f"Trade-offs:\n{tradeoffs}"
    try:
        return DecisionInput.build(
            title=title,
            context=context,
            decision=decision,
            consequence=consequence,
        )
    except Exception:  # pragma: no cover - defensive branch
        return None


def _sections(body: str) -> dict[str, str]:
    from .stages import _extract_sections  # local import to avoid cycles

    return _extract_sections(body)


def stage_sections(stage_type: StageType) -> tuple[str, ...]:
    return REQUIRED_SECTIONS[stage_type]


def workflow_memory_agent(
    approvals: ApprovalStore, memory: MemoryManager, workflow: Workflow, stage: WorkflowStage
) -> list[str]:
    """Optionally queue memory suggestions as approval requests.

    Returns the list of new approval request ids. The caller decides whether
    to expose this behaviour — nothing is executed without user approval.
    """
    queued: list[str] = []
    for suggestion in build_stage_memory_writes(workflow, stage):
        action = suggestion["action"]
        document = suggestion["document"]
        payload = dict(suggestion["payload"])
        payload["document"] = document
        preview = (
            memory.preview_decision(workflow.project, DecisionInput.build(**payload))
            if action == "memory_decision"
            else memory.preview_append(workflow.project, document, payload["content"])
        )
        request = approvals.create(
            action=action,
            project=workflow.project,
            path=f"memory/{document}",
            payload=payload,
            reason=f"Workflow {workflow.id}: sync {stage.stage_type.value} into {document}",
            preview=preview,
            workflow_id=workflow.id,
            stage_id=stage.id,
        )
        queued.append(request.request_id)
    return queued
