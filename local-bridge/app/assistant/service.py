"""Phase 32 · Assistant service.

Product-level orchestration on top of the Phase 31 LLM Gateway:

* user settings (non-sensitive only),
* provider configuration staging + connection testing,
* context status (capability flags, never content),
* assistant chat that injects an explicitly-consented web-context bundle.

Boundaries preserved from earlier phases: no execution, no source modification,
no auto-approval. Tool calls returned by a provider stay proposals and are
surfaced as records for the operator to route through the ApprovalStore.
"""

from __future__ import annotations

from typing import Any

from app.llm_gateway.models import ChatMessage, ChatRequest, MessageRole

from .context import WebContext, build_web_context, render_context_block
from .crypto import crypto_available
from .providers import SELECTABLE_PROVIDERS, build_registry, provider_catalog, test_provider, validate_model, validate_provider
from .store import AssistantSettingsStore, default_assistant_db_path

DEFAULT_PROVIDER = "local"
DEFAULT_MODEL = "local/simulator-v1"
USER_MODE = "user"
DEVELOPER_MODE = "developer"
MODES = (USER_MODE, DEVELOPER_MODE)

# Surfaces the extension may render per mode (spec §2). The Bridge publishes the
# same list the UI enforces so the two cannot drift apart silently.
USER_MODE_SURFACES = ("chat", "model_selector", "context", "history", "settings")
DEVELOPER_MODE_SURFACES = USER_MODE_SURFACES + (
    "project_context",
    "code_context",
    "tool_proposal",
    "engineering_graph",
)
# Capabilities that no mode may ever expose.
NEVER_AVAILABLE = ("execute", "approve_from_chat", "apply_patch", "auto_fix", "auto_approve", "shell")

SYSTEM_PREAMBLE = (
    "You are the local AI assistant of the ChatGPT Cursor Bridge. You may explain, "
    "analyse and draft. You cannot execute commands, run shells, apply patches or "
    "approve anything: every change is a proposal a human must approve."
)


class AssistantService:
    def __init__(self, store: AssistantSettingsStore | None = None, *, transport: Any = None) -> None:
        self.store = store or AssistantSettingsStore(default_assistant_db_path())
        self._transport = transport

    # -- settings ---------------------------------------------------------

    def user_settings(self) -> dict[str, Any]:
        """Non-sensitive settings only (spec §6).

        No ``api_key``, ``encrypted_api_key``, ``authorization`` or ``secret``
        key ever appears in this payload — only which provider/model is selected
        and whether *a* key exists.
        """
        preferences = self.store.preferences()
        mode = preferences.get("mode", USER_MODE)
        if mode not in MODES:
            mode = USER_MODE
        provider = preferences.get("selected_provider", DEFAULT_PROVIDER)
        if provider not in SELECTABLE_PROVIDERS:
            provider = DEFAULT_PROVIDER
        model = preferences.get("selected_model", "")
        return {
            "mode": mode,
            "provider": provider,
            "model": model or (DEFAULT_MODEL if provider == DEFAULT_PROVIDER else ""),
            "baseUrl": self._base_url_for(provider),
            "preferences": {key: preferences[key] for key in sorted(preferences)},
            "surfaces": list(USER_MODE_SURFACES if mode == USER_MODE else DEVELOPER_MODE_SURFACES),
            "neverAvailable": list(NEVER_AVAILABLE),
            "providers": [
                {
                    "provider": entry["provider"],
                    "status": entry["status"],
                    "hasStoredKey": entry["hasStoredKey"],
                    "models": entry["models"],
                }
                for entry in provider_catalog(self.store, transport=self._transport)
            ],
            # Named ``keyStorage`` rather than ``secretStorage`` so that the
            # forbidden-substring checks on this payload (§6: no ``api_key``,
            # ``encrypted_api_key``, ``authorization`` or ``secret``) stay strict.
            "keyStorage": {
                "algorithm": "AES-256-GCM",
                "available": crypto_available(),
                "location": "local-bridge encrypted store",
            },
            "readOnly": True,
        }

    def _base_url_for(self, provider: str) -> str:
        record = self.store.active_credential(provider)
        return record.base_url if record is not None else ""

    def provider_status(self) -> list[dict[str, Any]]:
        return provider_catalog(self.store, transport=self._transport)

    def stage_provider_config(
        self, *, provider: str, model: str = "", base_url: str = "", api_key: str = "", keep_existing_key: bool = False
    ):
        """Encrypt the submitted key immediately, then wait for approval.

        The plaintext key is consumed here and never enters the approval
        payload, the audit log, or any response body.
        """
        validate_provider(provider)
        if model:
            validate_model(self.store, provider, model, transport=self._transport)
        return self.store.stage_credential(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            keep_existing_key=keep_existing_key,
        )

    def activate_provider_config(self, credential_id: str, *, approval_request_id: str = "") -> dict[str, Any]:
        record = self.store.activate_credential(credential_id, approval_request_id=approval_request_id)
        if record is None:
            return {"activated": False, "provider": "", "readOnly": True}
        self.store.set_preference("selected_provider", record.provider)
        if record.model:
            self.store.set_preference("selected_model", record.model)
        return {"activated": True, **record.public_dict()}

    def forget_provider(self, provider: str) -> dict[str, Any]:
        validate_provider(provider)
        removed = self.store.forget_provider(provider)
        return {"provider": provider, "removed": removed, "readOnly": True}

    def test_provider(self, *, provider: str, model: str = "", api_key: str = "") -> dict[str, Any]:
        outcome = test_provider(
            self.store,
            provider=provider,
            model=model,
            transport=self._transport,
            api_key_override=api_key,
        )
        return outcome.as_dict()

    def set_mode(self, mode: str) -> dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"Unknown mode '{mode}'")
        self.store.set_preference("mode", mode)
        return {"mode": mode, "surfaces": list(USER_MODE_SURFACES if mode == USER_MODE else DEVELOPER_MODE_SURFACES)}

    def update_preferences(self, values: dict[str, str]) -> dict[str, Any]:
        for key, value in values.items():
            self.store.set_preference(key, value)
        return {"preferences": self.store.preferences(), "readOnly": True}

    # -- context ----------------------------------------------------------

    def context_status(self, *, project: str = "", scope: str = USER_MODE) -> dict[str, Any]:
        """Capability flags only (spec §7).

        Never returns file contents, secrets, absolute paths or workspace
        internals. ``scope="user"`` deliberately does not touch the developer
        context engine at all, so User Mode loads no engineering data.
        """
        payload: dict[str, Any] = {
            "scope": DEVELOPER_MODE if scope == DEVELOPER_MODE else USER_MODE,
            "web": {
                "requiresExplicitTrigger": True,
                "trigger": "ask_ai",
                "automaticCapture": False,
                "automaticUpload": False,
                "fields": ["pageTitle", "pageUrl", "selectedText", "readableContent", "timestamp"],
            },
            "developerContext": {"loaded": False, "readOnly": True},
            "readOnly": True,
        }
        if scope != DEVELOPER_MODE:
            return payload
        payload["developerContext"] = {
            "loaded": bool(project),
            "readOnly": True,
            "project": project,
            "sources": [
                "project_files",
                "code_symbols",
                "dependencies",
                "git_diff",
                "test_results",
                "architecture_metadata",
            ],
            "endpoint": "/context/dev/status",
            "modificationRequiresApproval": True,
        }
        return payload

    # -- chat -------------------------------------------------------------

    def build_messages(
        self, *, messages: list[dict[str, Any]], web_context: WebContext | None
    ) -> list[ChatMessage]:
        prepared: list[ChatMessage] = [ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PREAMBLE)]
        if web_context is not None and not web_context.is_empty:
            prepared.append(ChatMessage(role=MessageRole.SYSTEM, content=render_context_block(web_context)))
        prepared.extend(ChatMessage.from_dict(item) for item in messages)
        return prepared

    def chat(
        self,
        *,
        project: str,
        messages: list[dict[str, Any]],
        provider: str = "",
        model: str = "",
        temperature: float = 0.4,
        max_tokens: int = 2048,
        web_context_raw: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from app.llm_gateway import LLMGateway

        context = build_web_context(web_context_raw)
        settings = self.user_settings()
        provider_name = provider or settings["provider"]
        validate_provider(provider_name)
        model_name = model or settings["model"] or DEFAULT_MODEL
        registry = build_registry(self.store, transport=self._transport)
        gateway = LLMGateway(providers=registry, store=_ephemeral_store())
        request = ChatRequest(
            project=project,
            messages=tuple(self.build_messages(messages=messages, web_context=context)),
            model=model_name,
            provider=provider_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        result = gateway.chat(request)
        payload = result.as_dict()
        payload["contextIncluded"] = context is not None and not context.is_empty
        payload["context"] = context.as_dict() if context is not None else None
        # Tool calls stay proposals: recording one is a separate approval-gated
        # POST (/llm/conversations/{id}/tool-proposal).
        payload["toolCallsExecuted"] = False
        payload["requiresApproval"] = bool(result.tool_calls)
        return payload

    def stream_events(
        self,
        *,
        project: str,
        messages: list[dict[str, Any]],
        provider: str = "",
        model: str = "",
        temperature: float = 0.4,
        max_tokens: int = 2048,
        web_context_raw: dict[str, Any] | None = None,
    ):
        from app.llm_gateway import LLMGateway

        context = build_web_context(web_context_raw)
        settings = self.user_settings()
        provider_name = provider or settings["provider"]
        validate_provider(provider_name)
        model_name = model or settings["model"] or DEFAULT_MODEL
        registry = build_registry(self.store, transport=self._transport)
        gateway = LLMGateway(providers=registry, store=_ephemeral_store())
        request = ChatRequest(
            project=project,
            messages=tuple(self.build_messages(messages=messages, web_context=context)),
            model=model_name,
            provider=provider_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return gateway.stream(request)


def _ephemeral_store():
    """In-memory conversation store: assistant chat stays stateless.

    Persisting a conversation remains the approval-gated Phase 31 path; nothing
    in the chat request writes history.
    """
    from app.llm_gateway.conversation import ConversationStore

    return ConversationStore(":memory:")


__all__ = [
    "AssistantService",
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "DEVELOPER_MODE",
    "DEVELOPER_MODE_SURFACES",
    "MODES",
    "NEVER_AVAILABLE",
    "SYSTEM_PREAMBLE",
    "USER_MODE",
    "USER_MODE_SURFACES",
]
