"""Phase 31 · LLM Gateway API.

Read-only GETs expose the provider registry, model registry, conversations and
tool proposals. ``POST /llm/chat`` and ``POST /llm/chat/stream`` are stateless
computations (no persistence, no execution). Every persistent write — creating
a conversation, appending messages, recording a tool-call proposal — is
approval-gated (202 pending) through the existing ApprovalStore; tool
proposals are records only and are never executed here.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.models.request import (
    LlmChatRequest,
    LlmConversationCreateRequest,
    LlmConversationMessageRequest,
    LlmToolProposalRequest,
)
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.sandbox import SandboxViolation, validate_project_name
from app.security.validator import ResourceNotFound, ValidationFailed


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _gateway(settings: Settings):
    from app.llm_gateway import LLMGateway, default_llm_db_path

    return LLMGateway(llm_db_path=default_llm_db_path())


def _error_response(exc: Exception) -> JSONResponse:
    from app.llm_gateway.providers.base import ProviderError

    if isinstance(exc, ProviderError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.message, "code": exc.code})
    if isinstance(exc, SandboxViolation):
        return JSONResponse(status_code=403, content={"detail": str(exc), "code": "sandbox_violation"})
    if isinstance(exc, ResourceNotFound):
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    if isinstance(exc, ValidationFailed):
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": f"LLM gateway unavailable: {exc}"})


def register_llm_gateway_routes(app: Any) -> None:
    @app.get("/llm/providers", tags=["llm-gateway"])
    def llm_providers(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        gateway = _gateway(settings)
        result = gateway.providers_info()
        audit.record(
            action="llm_providers",
            path="llm:providers",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(result)} provider(s)",
        )
        return {"providers": result, "readOnly": True}

    @app.get("/llm/models", tags=["llm-gateway"])
    def llm_models(
        provider: str = Query(default="", max_length=64),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        gateway = _gateway(settings)
        result = gateway.models(provider)
        audit.record(
            action="llm_models",
            path=f"llm:models/{provider or '*' }",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(result)} model(s)",
        )
        return {"models": result, "readOnly": True}

    @app.get("/llm/conversations", tags=["llm-gateway"])
    def llm_conversations(
        project: str = Query(..., min_length=1, max_length=100),
        agent: str = Query(default="", max_length=64),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        gateway = _gateway(settings)
        conversations = gateway.store.list_conversations(project, agent)
        audit.record(
            action="llm_conversations",
            path=f"{project}:llm/conversations",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(conversations)} conversation(s)",
        )
        return {"project": project, "conversations": [item.as_dict() for item in conversations], "readOnly": True}

    @app.get("/llm/conversations/{conversation_id}", tags=["llm-gateway"])
    def llm_conversation_detail(
        conversation_id: str,
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
            gateway = _gateway(settings)
            conversation = gateway.store.get_conversation(conversation_id, project)
            if conversation is None:
                raise ResourceNotFound(f"Conversation '{conversation_id}' was not found for this project")
            messages = gateway.store.list_messages(conversation_id)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(
            action="llm_conversation_detail",
            path=f"{project}:llm/conversations/{conversation_id}",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(messages)} message(s)",
        )
        return {
            "conversation": conversation.as_dict(),
            "messages": [message.as_dict() for message in messages],
            "readOnly": True,
        }

    @app.get("/llm/tool-proposals", tags=["llm-gateway"])
    def llm_tool_proposals(
        project: str = Query(..., min_length=1, max_length=100),
        conversation_id: str = Query(default="", max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            project = validate_project_name(project)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        gateway = _gateway(settings)
        proposals = gateway.store.list_tool_proposals(project, conversation_id)
        audit.record(
            action="llm_tool_proposals",
            path=f"{project}:llm/tool-proposals",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(proposals)} proposal(s)",
        )
        return {"project": project, "proposals": [item.as_dict() for item in proposals], "readOnly": True}

    # -- Stateless chat (no persistence, no execution) -------------------

    @app.post("/llm/chat", tags=["llm-gateway"])
    def llm_chat(
        body: LlmChatRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        from app.llm_gateway import ChatRequest as GatewayChatRequest

        try:
            project = validate_project_name(body.project)
            request = GatewayChatRequest.from_dict(
                {
                    "project": project,
                    "messages": [message.model_dump() for message in body.messages],
                    "model": body.model,
                    "provider": body.provider,
                    "agent": body.agent,
                    "temperature": body.temperature,
                    "max_tokens": body.max_tokens,
                }
            )
            result = _gateway(settings).chat(request)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(
            action="llm_chat",
            path=f"{project}:llm/chat",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"provider={result.provider} model={result.model} toolCalls={len(result.tool_calls)}",
        )
        return result.as_dict()

    @app.post("/llm/chat/stream", tags=["llm-gateway"])
    def llm_chat_stream(
        body: LlmChatRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> StreamingResponse:
        from app.llm_gateway import ChatRequest as GatewayChatRequest

        try:
            project = validate_project_name(body.project)
            request = GatewayChatRequest.from_dict(
                {
                    "project": project,
                    "messages": [message.model_dump() for message in body.messages],
                    "model": body.model,
                    "provider": body.provider,
                    "agent": body.agent,
                    "temperature": body.temperature,
                    "max_tokens": body.max_tokens,
                }
            )
            events = _gateway(settings).stream(request)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

        def generate():
            for event in events:
                yield f"data: {json.dumps(event.as_dict(), ensure_ascii=False)}\n\n"

        audit.record(
            action="llm_chat_stream",
            path=f"{project}:llm/chat/stream",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"model={request.model}",
        )
        return StreamingResponse(generate(), media_type="text/event-stream")

    # -- Approval-gated persistence --------------------------------------

    @app.post("/llm/conversations", status_code=status.HTTP_202_ACCEPTED, tags=["llm-gateway"])
    def llm_conversation_create(
        body: LlmConversationCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ):
        from app.main import _register_pending

        try:
            project = validate_project_name(body.project)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        return _register_pending(
            action="llm_conversation_create",
            project=project,
            path=f"llm/conversations",
            payload={
                "project": project,
                "provider": body.provider,
                "model": body.model,
                "title": body.title,
                "agent": body.agent,
            },
            reason=body.reason,
            preview_factory=lambda: (
                f"CREATE conversation '{body.title}' for {project} "
                f"(provider={body.provider}, model={body.model}); metadata only, no execution"
            ),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/llm/conversations/{conversation_id}/messages", status_code=status.HTTP_202_ACCEPTED, tags=["llm-gateway"])
    def llm_conversation_message(
        conversation_id: str,
        body: LlmConversationMessageRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ):
        from app.main import _register_pending

        try:
            project = validate_project_name(body.project)
            gateway = _gateway(settings)
            if gateway.store.get_conversation(conversation_id, project) is None:
                raise ResourceNotFound(f"Conversation '{conversation_id}' was not found for this project")
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        return _register_pending(
            action="llm_message_append",
            project=project,
            path=f"llm/conversations/{conversation_id}/messages",
            payload={
                "project": project,
                "conversation_id": conversation_id,
                "content": body.content,
                "agent": body.agent,
                "model": body.model,
                "provider": body.provider,
            },
            reason=body.reason,
            preview_factory=lambda: (
                f"APPEND user message ({len(body.content)} chars) to conversation {conversation_id} "
                f"for {project}; stored history only, no execution"
            ),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/llm/conversations/{conversation_id}/tool-proposal", status_code=status.HTTP_202_ACCEPTED, tags=["llm-gateway"])
    def llm_tool_proposal(
        conversation_id: str,
        body: LlmToolProposalRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ):
        from app.main import _register_pending

        try:
            project = validate_project_name(body.project)
            gateway = _gateway(settings)
            if gateway.store.get_conversation(conversation_id, project) is None:
                raise ResourceNotFound(f"Conversation '{conversation_id}' was not found for this project")
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        return _register_pending(
            action="llm_tool_proposal",
            project=project,
            path=f"llm/conversations/{conversation_id}/tool-proposal",
            payload={
                "project": project,
                "conversation_id": conversation_id,
                "message_id": body.message_id,
                "tool_name": body.tool_name,
                "arguments": body.arguments,
                "reason": body.reason,
            },
            reason=body.reason or f"Tool call proposal: {body.tool_name}",
            preview_factory=lambda: (
                f"RECORD tool-call proposal {body.tool_name} for conversation {conversation_id} "
                f"({project}); record only — the tool is never executed by the LLM gateway"
            ),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )
