"""Planner facade: creates collaboration plans, never actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollaborationPlan:
    workflow_id: str
    ordered_roles: tuple[str, ...]
    task_proposals: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]: return {"workflowId": self.workflow_id, "orderedRoles": list(self.ordered_roles), "taskProposals": [dict(item) for item in self.task_proposals], "requiresApproval": True}


class CollaborationPlanner:
    ROLES = ("PLANNER", "ARCHITECT", "CODER", "TESTER", "REVIEWER")

    def plan(self, *, workflow_id: str, task_ids: list[str] | None = None) -> CollaborationPlan:
        ids = task_ids or []
        proposals = tuple({"role": role, "taskId": ids[index] if index < len(ids) else None, "kind": "coordination_proposal"} for index, role in enumerate(self.ROLES))
        return CollaborationPlan(workflow_id, self.ROLES, proposals)
