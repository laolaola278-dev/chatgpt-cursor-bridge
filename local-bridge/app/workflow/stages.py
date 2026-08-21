"""Stage transition rules and stage report contract.

Every stage must produce a report before it can be approved. Report sections
are stage-specific (e.g. Architecture must document technology choices,
module design, risks and trade-offs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.security.validator import ValidationFailed

from .models import STAGE_ORDER, StageStatus, StageType, WorkflowStatus


# Legal FSM transitions for the *workflow* status.
WORKFLOW_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.CREATED: frozenset(
        {
            WorkflowStatus.ANALYZING,
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.ANALYZING: frozenset(
        {
            WorkflowStatus.DESIGNING,
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.DESIGNING: frozenset(
        {
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.IMPLEMENTING,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.WAITING_APPROVAL: frozenset(
        {
            WorkflowStatus.CREATED,
            WorkflowStatus.IMPLEMENTING,
            WorkflowStatus.DESIGNING,
            WorkflowStatus.TESTING,
            WorkflowStatus.ANALYZING,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.IMPLEMENTING: frozenset(
        {
            WorkflowStatus.TESTING,
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.TESTING: frozenset(
        {
            WorkflowStatus.WAITING_APPROVAL,
            WorkflowStatus.IMPLEMENTING,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.FAILED,
        }
    ),
    WorkflowStatus.COMPLETED: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
}


# Legal transitions for a *stage*'s status.
STAGE_TRANSITIONS: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.PENDING: frozenset({StageStatus.IN_PROGRESS, StageStatus.SKIPPED}),
    StageStatus.IN_PROGRESS: frozenset(
        {StageStatus.REPORTED, StageStatus.SKIPPED}
    ),
    StageStatus.REPORTED: frozenset(
        {StageStatus.WAITING_APPROVAL, StageStatus.IN_PROGRESS}
    ),
    StageStatus.WAITING_APPROVAL: frozenset(
        {StageStatus.APPROVED, StageStatus.REJECTED, StageStatus.IN_PROGRESS}
    ),
    StageStatus.APPROVED: frozenset(),
    StageStatus.REJECTED: frozenset({StageStatus.IN_PROGRESS}),
    StageStatus.SKIPPED: frozenset(),
}


class WorkflowTransitionError(ValidationFailed):
    """Raised for illegal state jumps."""

    code = "workflow_transition_error"


def assert_workflow_transition(current: WorkflowStatus, target: WorkflowStatus) -> None:
    if target not in WORKFLOW_TRANSITIONS.get(current, frozenset()):
        raise WorkflowTransitionError(
            f"Illegal workflow transition: {current.value} -> {target.value}"
        )


def assert_stage_transition(current: StageStatus, target: StageStatus) -> None:
    if target not in STAGE_TRANSITIONS.get(current, frozenset()):
        raise WorkflowTransitionError(
            f"Illegal stage transition: {current.value} -> {target.value}"
        )


def next_stage(current: StageType) -> StageType | None:
    order = STAGE_ORDER
    for index, stage in enumerate(order[:-1]):
        if stage is current:
            return order[index + 1]
    return None


@dataclass(frozen=True)
class StageReport:
    """Validated stage report."""

    title: str
    body: str
    sections: dict[str, str]
    stage_type: StageType


# Required section headings per stage. Case-insensitive match against `##` headings.
REQUIRED_SECTIONS: dict[StageType, tuple[str, ...]] = {
    StageType.REQUIREMENT: ("Goal", "Scope", "Constraints"),
    StageType.ANALYSIS: ("Findings", "Risks", "Assumptions"),
    StageType.ARCHITECTURE: ("Technology", "Modules", "Risks", "Trade-offs"),
    StageType.IMPLEMENTATION: ("Summary", "Files Touched", "Follow-ups"),
    StageType.TESTING: ("Coverage", "Results", "Gaps"),
    StageType.DEBUG: ("Symptom", "Root Cause", "Fix"),
    StageType.DELIVERY: ("Outcome", "Artifacts", "Next Steps"),
}


SECTION_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
MAX_REPORT_BYTES = 128 * 1024
MAX_TITLE_LENGTH = 200


def _extract_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_HEADING.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[heading] = body[start:end].strip()
    return sections


def validate_stage_report(
    stage_type: StageType, *, title: str, body: str
) -> StageReport:
    """Validate a stage report against its required sections."""
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise ValidationFailed("Stage report requires a title")
    if len(cleaned_title) > MAX_TITLE_LENGTH:
        raise ValidationFailed("Stage report title exceeds 200 characters")

    cleaned_body = (body or "").strip()
    if not cleaned_body:
        raise ValidationFailed("Stage report body must not be empty")
    if len(cleaned_body.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValidationFailed("Stage report exceeds 128KB")

    sections = _extract_sections(cleaned_body)
    missing = [
        name
        for name in REQUIRED_SECTIONS[stage_type]
        if name.lower() not in sections
    ]
    if missing:
        raise ValidationFailed(
            f"{stage_type.value} report is missing required section(s): {', '.join(missing)}"
        )

    return StageReport(
        title=cleaned_title,
        body=cleaned_body,
        sections=sections,
        stage_type=stage_type,
    )


def humanise_actions(action_ids: Iterable[str]) -> str:
    items = list(action_ids)
    return f"{len(items)} action(s) attached" if items else "no actions attached"
