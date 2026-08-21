"""Agent lifecycle and message orchestration with no tool execution."""

from __future__ import annotations

import secrets

from app.audit.logger import AuditLogger
from app.model_router import ModelRouter, TaskType
from app.security.permissions import PermissionLevel
from app.security.sandbox import validate_project_name
from app.security.validator import ApprovalError, ResourceNotFound, ValidationFailed

from .models import Agent, AgentRole, AgentStatus, ROLE_PERMISSIONS
from .protocol import AgentMessage
from .storage import AgentStorage


_ALLOWED: dict[AgentStatus, frozenset[AgentStatus]] = {
    AgentStatus.CREATED: frozenset({AgentStatus.ACTIVE, AgentStatus.FAILED}),
    AgentStatus.ACTIVE: frozenset({AgentStatus.PAUSED, AgentStatus.COMPLETED, AgentStatus.FAILED}),
    AgentStatus.PAUSED: frozenset({AgentStatus.ACTIVE, AgentStatus.COMPLETED, AgentStatus.FAILED}),
    AgentStatus.COMPLETED: frozenset(),
    AgentStatus.FAILED: frozenset(),
}


class AgentManager:
    def __init__(self, *, storage: AgentStorage, audit: AuditLogger, router: ModelRouter | None = None) -> None:
        self.storage = storage
        self.audit = audit
        self.router = router or ModelRouter()

    def list(self, project: str | None = None) -> list[Agent]:
        agents = self.storage.all()
        if project:
            agents = [agent for agent in agents if agent.project == project]
        return sorted(agents, key=lambda agent: agent.updated_at, reverse=True)

    def get(self, agent_id: str) -> Agent:
        if not agent_id.startswith("ag_"):
            raise ValidationFailed("Invalid agent id")
        return self.storage.get(agent_id)

    def create(
        self,
        *,
        project: str,
        session_id: str,
        role: str,
        memory_scope: str,
        model_id: str | None = None,
        permissions: list[str] | None = None,
        workflow_id: str | None = None,
        stage_id: str | None = None,
    ) -> Agent:
        project = validate_project_name(project)
        if not session_id.startswith("ses_"):
            raise ValidationFailed("Agent must be bound to a persistent session")
        try:
            agent_role = AgentRole((role or "").strip().upper())
        except ValueError as exc:
            raise ValidationFailed("Unknown agent role") from exc
        scope = (memory_scope or "").strip()
        if not scope or len(scope) > 200:
            raise ValidationFailed("Agent memory scope must contain 1-200 characters")
        allowed = ROLE_PERMISSIONS[agent_role]
        requested = sorted(set(permissions or allowed))
        if not set(requested).issubset(allowed):
            raise ApprovalError("Agent permissions exceed the role allowlist")
        task_type = {
            AgentRole.PLANNER: TaskType.ARCHITECTURE,
            AgentRole.ARCHITECT: TaskType.ARCHITECTURE,
            AgentRole.CODER: TaskType.CODING,
            AgentRole.TESTER: TaskType.TESTING,
            AgentRole.REVIEWER: TaskType.REVIEW,
        }[agent_role]
        route = self.router.route(task_type.value, task_type=task_type.value, preferred_model=model_id)
        now = Agent.now()
        agent = Agent(
            id=f"ag_{secrets.token_hex(8)}",
            project=project,
            session_id=session_id,
            role=agent_role,
            model_id=route.model.id,
            memory_scope=scope,
            permissions=requested,
            status=AgentStatus.CREATED,
            created_at=now,
            updated_at=now,
            workflow_id=workflow_id,
            stage_id=stage_id,
            history=[{"from": "", "to": AgentStatus.CREATED.value, "at": now}],
        )
        self.storage.save(agent)
        self._audit(agent, "agent_created", "Created scoped agent metadata")
        return agent

    def transition(self, agent_id: str, target: str) -> Agent:
        agent = self.get(agent_id)
        try:
            next_status = AgentStatus((target or "").strip().upper())
        except ValueError as exc:
            raise ValidationFailed("Unknown agent status") from exc
        if next_status not in _ALLOWED[agent.status]:
            raise ApprovalError(f"Agent {agent.id} cannot transition {agent.status.value} -> {next_status.value}")
        now = Agent.now()
        previous = agent.status
        agent.status = next_status
        agent.updated_at = now
        agent.history.append({"from": previous.value, "to": next_status.value, "at": now})
        self.storage.save(agent)
        self._audit(agent, "agent_transition", f"{previous.value} -> {next_status.value}")
        return agent

    def send_message(
        self,
        *,
        from_agent: str,
        to_agent: str,
        task: str,
        context_reference: str,
    ) -> AgentMessage:
        sender = self.get(from_agent)
        receiver = self.get(to_agent)
        if sender.project != receiver.project:
            raise ValidationFailed("Agents may only communicate within one project")
        if sender.status not in {AgentStatus.CREATED, AgentStatus.ACTIVE, AgentStatus.PAUSED}:
            raise ApprovalError("Completed or failed agents cannot send messages")
        if receiver.status in {AgentStatus.COMPLETED, AgentStatus.FAILED}:
            raise ApprovalError("Messages cannot target a completed or failed agent")
        message = AgentMessage.create(
            from_agent=from_agent,
            to_agent=to_agent,
            task=task,
            context_reference=context_reference,
        )
        self.storage.save_message(message)
        self.audit.record(
            action="agent_message",
            path=f"{sender.project}:agents/{from_agent}->{to_agent}",
            permission=PermissionLevel.LEVEL_1.value,
            approved=True,
            result="success",
            detail=f"Agent message {message.message_id}",
        )
        return message

    def messages(self, project: str | None = None, *, limit: int = 100) -> list[dict[str, object]]:
        records = self.storage.messages(limit=limit)
        if not project:
            return records
        ids = {agent.id for agent in self.list(project)}
        return [record for record in records if record.get("fromAgent") in ids or record.get("toAgent") in ids]

    def _audit(self, agent: Agent, action: str, detail: str) -> None:
        self.audit.record(
            action=action,
            path=f"{agent.project}:agent/{agent.id}",
            permission=PermissionLevel.LEVEL_1.value,
            approved=True,
            result="success",
            detail=detail,
        )
