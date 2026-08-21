"""Agent Coordinator: lifecycle and proposals only; no action execution."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.audit.logger import AuditLogger
from app.event import EventBus
from app.security.permissions import PermissionLevel
from app.security.validator import ApprovalError, ValidationFailed

from .models import AgentTeam, AgentTeamStatus
from .planner import CollaborationPlan, CollaborationPlanner
from .storage import CollaborationStorage

_ALLOWED: dict[AgentTeamStatus, set[AgentTeamStatus]] = {
    AgentTeamStatus.CREATED: {AgentTeamStatus.PLANNING, AgentTeamStatus.FAILED},
    AgentTeamStatus.PLANNING: {AgentTeamStatus.EXECUTING, AgentTeamStatus.WAITING_APPROVAL, AgentTeamStatus.FAILED},
    AgentTeamStatus.EXECUTING: {AgentTeamStatus.WAITING_APPROVAL, AgentTeamStatus.REVIEWING, AgentTeamStatus.FAILED},
    AgentTeamStatus.WAITING_APPROVAL: {AgentTeamStatus.EXECUTING, AgentTeamStatus.REVIEWING, AgentTeamStatus.FAILED},
    AgentTeamStatus.REVIEWING: {AgentTeamStatus.COMPLETED, AgentTeamStatus.FAILED},
    AgentTeamStatus.COMPLETED: set(), AgentTeamStatus.FAILED: set(),
}


class AgentCoordinator:
    def __init__(self, storage: CollaborationStorage, audit: AuditLogger | None = None, events: EventBus | None = None) -> None: self.storage, self.audit, self.events = storage, audit, events

    def create_team(self, *, workflow_id: str, members: list[str], leader: str) -> AgentTeam:
        if not workflow_id or len(members) < 2 or leader not in members: raise ValidationFailed("Team requires a workflow, at least two members and a member leader")
        team = AgentTeam.create(workflow_id=workflow_id, members=members, leader=leader); self.storage.save_team(team); self._audit(team, "team_created", "Created collaboration metadata"); return team

    def get(self, team_id: str) -> AgentTeam: return self.storage.get_team(team_id)
    def list(self, workflow_id: str | None = None) -> list[AgentTeam]: return self.storage.list_teams(workflow_id)

    def transition(self, team_id: str, target: AgentTeamStatus | str) -> AgentTeam:
        team = self.get(team_id)
        try: next_status = target if isinstance(target, AgentTeamStatus) else AgentTeamStatus(target.upper())
        except ValueError as exc: raise ValidationFailed("Unknown team status") from exc
        if next_status not in _ALLOWED[team.status]: raise ApprovalError(f"Team {team.id} cannot transition {team.status.value} -> {next_status.value}")
        previous = team.status; team.status = next_status; team.updated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds"); team.history.append({"from": previous.value, "to": next_status.value, "at": team.updated_at}); self.storage.save_team(team); self._audit(team, "team_transition", f"{previous.value} -> {next_status.value}"); return team

    def plan(self, team_id: str, task_ids: list[str] | None = None) -> CollaborationPlan:
        team = self.get(team_id); return CollaborationPlanner().plan(workflow_id=team.workflow_id, task_ids=task_ids)

    def propose_assignment(self, team_id: str, *, agent_id: str, task_id: str) -> dict[str, Any]:
        team = self.get(team_id)
        if agent_id not in team.members: raise ValidationFailed("Agent is not a member of the team")
        proposal = {"teamId": team.id, "workflowId": team.workflow_id, "agentId": agent_id, "taskId": task_id, "requiresApproval": True, "execution": "blocked"}
        if self.audit: self.audit.record(action="team_task_proposal", path=f"team/{team.id}/task/{task_id}", permission=PermissionLevel.LEVEL_1.value, approved=False, result="proposal", detail="Coordinator only proposes assignment")
        return proposal

    def execute(self, *_args: Any, **_kwargs: Any) -> None: raise ApprovalError("Agent Coordinator cannot execute actions")
    def collect_result(self, team_id: str, result: dict[str, Any]) -> dict[str, Any]: return {"teamId": self.get(team_id).id, "result": dict(result), "execution": "not performed"}

    def _audit(self, team: AgentTeam, action: str, detail: str) -> None:
        if self.audit: self.audit.record(action=action, path=f"workflow/{team.workflow_id}/team/{team.id}", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=detail)
        if self.events: self.events.publish("collaboration.team", source="collaboration.coordinator", payload=team.as_dict())
