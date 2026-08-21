"""Phase 32 · Assistant API (settings, providers, context status, chat).

Route boundaries:

* ``GET /user/settings``, ``GET /provider/status`` and ``GET /context/status``
  are read-only projections. None of them can return ``api_key``,
  ``encrypted_api_key``, ``authorization`` or ``secret``.
* ``POST /provider/test`` runs one probe and answers with a fixed vocabulary
  only (Connected / Failed / Not configured): no stack trace, no provider body,
  no header, no internal path.
* ``POST /provider/config``, ``POST /provider/forget`` and
  ``POST /user/settings`` are approval-gated (202 pending). A submitted API key
  is encrypted on arrival and never enters the approval payload or the audit log.
* ``POST /assistant/chat`` (+ ``/stream``) is a stateless computation. Tool
  calls come back as proposals; nothing is executed here.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.audit.logger import AuditLogger, get_audit_logger
from app.config import Settings, get_settings
from app.models.request import (
    AssistantChatRequest,
    AssistantWebContextRequest,
    ProviderConfigRequest,
    ProviderForgetRequest,
    ProviderTestRequest,
    UserSettingsUpdateRequest,
)
from app.security.permissions import ApprovalStore, PermissionLevel, get_approval_store
from app.security.sandbox import SandboxViolation, validate_project_name
from app.security.validator import ResourceNotFound, ValidationFailed

from .service import AssistantService

def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


def _service(settings: Settings) -> AssistantService:
    # Mirrors the Phase 31 ``_gateway(settings)`` pattern: one short-lived
    # instance per request, no module-level state.
    return AssistantService()


def _error_response(exc: Exception) -> JSONResponse:
    """Map a failure to a safe body.

    Phase 34 · every assistant failure now answers with the same envelope
    (:func:`app.assistant.errors.safe_error_body`): ``error`` + ``message`` for
    the extension, ``code`` + ``detail`` for the Phase 31/32/33 callers that
    already read them. ``message`` is always one sentence from
    :data:`app.assistant.errors.SAFE_MESSAGES`, so the envelope can never carry
    a stack trace, an internal path, a key, a header or a vendor response body.

    ``provider_not_configured`` is the one status that changed in Phase 34: the
    assistant API reports the documented ``400`` (the Phase 31 ``/llm/chat``
    gateway still answers ``422``).

    The generic fallback deliberately omits ``str(exc)``: a provider exception
    that reaches this point may embed the vendor's raw response text.
    """
    from app.llm_gateway.providers.base import ProviderError

    from .errors import (
        NOT_CONFIGURED_DETAIL,
        NOT_CONFIGURED_HTTP_STATUS,
        safe_error_body,
        safe_message_for_http,
        safe_provider_failure,
    )

    if isinstance(exc, ProviderError):
        if exc.code == "provider_not_configured":
            # Phase 34 · unified "no provider" answer for the extension.
            return JSONResponse(
                status_code=NOT_CONFIGURED_HTTP_STATUS,
                content=safe_error_body(exc.code, NOT_CONFIGURED_DETAIL),
            )
        if exc.code in ("unknown_provider", "unknown_model"):
            # ``exc.message`` here is a caller-side mistake ("Unknown provider
            # 'x'"), never vendor text, so it is kept as ``detail``.
            return JSONResponse(
                status_code=exc.status,
                content=safe_error_body(exc.code, safe_message_for_http(exc.status), exc.message),
            )
        # Vendor text is replaced by the same fixed vocabulary /provider/test uses.
        safe = safe_provider_failure("", exc).message
        return JSONResponse(status_code=exc.status, content=safe_error_body(exc.code, safe))
    code = getattr(exc, "code", "")
    exc_status = getattr(exc, "status", 0)
    if code and isinstance(exc_status, int) and exc_status:
        # Assistant-local failures (consent, preference, secret storage) already
        # carry a safe message plus an HTTP status.
        return JSONResponse(
            status_code=exc_status,
            content=safe_error_body(code, safe_message_for_http(exc_status), str(exc)),
        )
    if isinstance(exc, SandboxViolation):
        return JSONResponse(
            status_code=403,
            content=safe_error_body("sandbox_violation", safe_message_for_http(403), str(exc)),
        )
    if isinstance(exc, ResourceNotFound):
        return JSONResponse(
            status_code=404,
            content=safe_error_body("not_found", safe_message_for_http(404), str(exc)),
        )
    if isinstance(exc, ValidationFailed):
        return JSONResponse(
            status_code=422,
            content=safe_error_body("validation_failed", safe_message_for_http(422), str(exc)),
        )
    return JSONResponse(
        status_code=500,
        content=safe_error_body("assistant_error", safe_message_for_http(500), "Assistant unavailable"),
    )


def _stream_error_event(exc: Exception) -> dict[str, Any]:
    """Phase 34 · terminate a broken SSE stream with one safe ``error`` event.

    A provider that fails *after* the first token cannot be reported as JSON any
    more (the response has already started). Without this the connection would
    simply break and the panel would sit in "streaming" forever. The event body
    is one sentence from the fixed vocabulary — never the vendor payload, the
    exception object, a header or a path.
    """
    from app.llm_gateway.providers.base import ProviderError

    from .errors import NOT_CONFIGURED_DETAIL, PROVIDER_UNAVAILABLE, safe_provider_failure

    if isinstance(exc, ProviderError):
        if exc.code == "provider_not_configured":
            message = NOT_CONFIGURED_DETAIL
        else:
            message = safe_provider_failure("", exc).message
    else:
        message = PROVIDER_UNAVAILABLE
    return {"type": "error", "content": message, "toolCall": None, "provider": "", "model": ""}


def _web_context_payload(model: AssistantWebContextRequest | None) -> dict[str, Any] | None:
    """Hand the raw bundle to :func:`app.assistant.context.build_web_context`.

    Consent is validated there, not here, so every caller shares one gate.
    """
    if model is None:
        return None
    return model.model_dump()


def register_assistant_routes(app: Any) -> None:
    # -- read-only projections -------------------------------------------

    @app.get("/user/settings", tags=["assistant"])
    def user_settings(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> Any:
        try:
            payload = _service(settings).user_settings()
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(
            action="assistant_user_settings",
            path="assistant:user/settings",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"mode={payload['mode']} provider={payload['provider']}",
        )
        return payload

    @app.get("/provider/status", tags=["assistant"])
    def provider_status(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> Any:
        try:
            catalog = _service(settings).provider_status()
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(
            action="assistant_provider_status",
            path="assistant:provider/status",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(catalog)} provider(s)",
        )
        return {"providers": catalog, "readOnly": True}

    @app.get("/context/status", tags=["assistant"])
    def context_status(
        project: str = Query(default="", max_length=100),
        scope: str = Query(default="user", max_length=16),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> Any:
        try:
            if project:
                project = validate_project_name(project)
            payload = _service(settings).context_status(project=project, scope=scope)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(
            action="assistant_context_status",
            path=f"assistant:context/status/{payload['scope']}",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"scope={payload['scope']} developerContextLoaded={payload['developerContext']['loaded']}",
        )
        return payload

    # -- connection test (safe messages only) ----------------------------

    @app.post("/provider/test", tags=["assistant"])
    def provider_test(
        body: ProviderTestRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> Any:
        try:
            outcome = _service(settings).test_provider(
                provider=body.provider, model=body.model, api_key=body.api_key
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(
            action="assistant_provider_test",
            path=f"assistant:provider/test/{body.provider}",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result=outcome["status"],
            # Only the fixed vocabulary is logged; no key, header or vendor body.
            detail=f"provider={body.provider} status={outcome['status']}",
        )
        return outcome

    # -- stateless chat ---------------------------------------------------

    @app.post("/assistant/chat", tags=["assistant"])
    def assistant_chat(
        body: AssistantChatRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> Any:
        try:
            project = validate_project_name(body.project)
            payload = _service(settings).chat(
                project=project,
                messages=[message.model_dump() for message in body.messages],
                provider=body.provider,
                model=body.model,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                web_context_raw=_web_context_payload(body.web_context),
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        audit.record(
            action="assistant_chat",
            path=f"{project}:assistant/chat",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=(
                f"provider={payload['provider']} model={payload['model']} "
                f"contextIncluded={payload['contextIncluded']} toolCallsExecuted=False"
            ),
        )
        return payload

    @app.post("/assistant/chat/stream", tags=["assistant"])
    def assistant_chat_stream(
        body: AssistantChatRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> Any:
        try:
            project = validate_project_name(body.project)
            events = _service(settings).stream_events(
                project=project,
                messages=[message.model_dump() for message in body.messages],
                provider=body.provider,
                model=body.model,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                web_context_raw=_web_context_payload(body.web_context),
            )
            # ``stream_events`` validates consent and the provider name eagerly,
            # but the gateway's own generator only resolves the model and checks
            # that the provider is configured once it is started. Pull the first
            # event here so those failures surface as JSON rather than as a
            # broken event stream.
            iterator = iter(events)
            first = next(iterator, None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

        def generate():
            if first is not None:
                yield f"data: {json.dumps(first.as_dict(), ensure_ascii=False)}\n\n"
            try:
                for event in iterator:
                    yield f"data: {json.dumps(event.as_dict(), ensure_ascii=False)}\n\n"
            except Exception as exc:  # noqa: BLE001
                # Phase 34 · a mid-stream failure ends the stream with a safe
                # ``error`` event instead of a dropped connection.
                yield f"data: {json.dumps(_stream_error_event(exc), ensure_ascii=False)}\n\n"

        audit.record(
            action="assistant_chat_stream",
            path=f"{project}:assistant/chat/stream",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"provider={body.provider or 'default'} streaming",
        )
        return StreamingResponse(generate(), media_type="text/event-stream")

    # -- approval-gated writes -------------------------------------------

    @app.post("/provider/config", status_code=status.HTTP_202_ACCEPTED, tags=["assistant"])
    def provider_config(
        body: ProviderConfigRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> Any:
        from app.main import _register_pending

        try:
            # The plaintext key is encrypted here and dropped. The staged row is
            # inert until a human approves the activation below.
            record = _service(settings).stage_provider_config(
                provider=body.provider,
                model=body.model,
                base_url=body.base_url,
                api_key=body.api_key,
                keep_existing_key=body.keep_existing_key,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        return _register_pending(
            action="assistant_provider_config",
            project="",
            path=f"assistant/provider/{record.provider}",
            # Payload is persisted as JSON in approvals.db, so it carries the
            # credential id only — never the key or its envelope.
            payload={
                "provider": record.provider,
                "model": record.model,
                "base_url": record.base_url,
                "credential_id": record.credential_id,
                "key_fingerprint": record.key_fingerprint,
                "has_key": record.has_key,
            },
            reason=body.reason,
            preview_factory=lambda: (
                f"ACTIVATE {record.provider} provider configuration "
                f"(model={record.model or 'unset'}, key={record.key_hint or 'none'}); "
                "the API key is already AES-256-GCM encrypted and is never shown, "
                "logged or exported"
            ),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/provider/forget", status_code=status.HTTP_202_ACCEPTED, tags=["assistant"])
    def provider_forget(
        body: ProviderForgetRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> Any:
        from app.assistant.providers import validate_provider
        from app.main import _register_pending

        try:
            provider = validate_provider(body.provider)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)
        return _register_pending(
            action="assistant_provider_forget",
            project="",
            path=f"assistant/provider/{provider}",
            payload={"provider": provider},
            reason=body.reason,
            preview_factory=lambda: (
                f"DELETE every stored credential for {provider}; the encrypted key "
                "is destroyed and the provider returns to 'Not configured'"
            ),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/user/settings", status_code=status.HTTP_202_ACCEPTED, tags=["assistant"])
    def user_settings_update(
        body: UserSettingsUpdateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> Any:
        from app.main import _register_pending

        # Only the allowlisted, non-sensitive preference keys can be submitted;
        # ``AssistantSettingsStore.set_preference`` rejects anything else again.
        values = {
            key: value
            for key, value in {
                "mode": body.mode,
                "selected_provider": body.selected_provider,
                "selected_model": body.selected_model,
                "onboarding_state": body.onboarding_state,
                "theme": body.theme,
                "language": body.language,
            }.items()
            if value
        }
        if not values:
            from .errors import REQUEST_REJECTED, safe_error_body

            return JSONResponse(
                status_code=422,
                content=safe_error_body(
                    "preference_rejected", REQUEST_REJECTED, "No storable preference was supplied"
                ),
            )
        return _register_pending(
            action="assistant_settings_update",
            project="",
            path="assistant/user/settings",
            payload={"preferences": values},
            reason=body.reason,
            preview_factory=lambda: (
                "UPDATE assistant preferences: "
                + ", ".join(f"{key}={value}" for key, value in sorted(values.items()))
                + "; display preferences only, no credential material"
            ),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )


__all__ = ["register_assistant_routes"]
