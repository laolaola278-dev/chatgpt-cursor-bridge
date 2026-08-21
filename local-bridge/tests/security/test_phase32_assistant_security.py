"""Phase 32 · AI Assistant security boundary tests (spec §19).

Five boundaries are asserted here, both by scanning ``app/assistant`` for
forbidden constructs and by driving the HTTP surface:

* **API key** — never returned, never logged, never in a URL or query
  parameter, never persisted in plaintext (not even inside approvals.db).
* **Provider** — an unknown provider and an invalid model are rejected; the
  status and test payloads use a fixed safe vocabulary with no stack trace,
  no vendor body, no authorization header and no internal path.
* **Context** — a web-context bundle is only accepted with an explicit
  ``ask_ai`` trigger; there is no background capture and no automatic upload.
* **Developer context** — read-only; no source modification, no execution.
* **Gateway** — no execute / shell / apply_patch surface, no auto-approval and
  no way to bypass the ApprovalStore.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.assistant.context import ContextConsentRequired, build_web_context
from app.assistant.service import AssistantService, NEVER_AVAILABLE
from app.assistant.store import ALLOWED_PREFERENCE_KEYS, PreferenceRejected
from app.security.permissions import PermissionLevel, level_for_action

SAMPLE_API_KEY = "sk-test-1234567890abcdef"

# Read-only Phase 32 actions vs. the approval-gated writes (spec §5, §6).
READ_ACTIONS = (
    "assistant_user_settings",
    "assistant_provider_status",
    "assistant_provider_test",
    "assistant_context_status",
    "assistant_chat",
    "assistant_chat_stream",
)
WRITE_ACTIONS = (
    "assistant_provider_config",
    "assistant_provider_forget",
    "assistant_settings_update",
)


def assistant_root() -> Path:
    from app import assistant

    return Path(assistant.__file__).parent


def assistant_sources() -> list[Path]:
    return sorted(assistant_root().rglob("*.py"))


def _memory_store():
    """In-memory store with a fixed key: no disk, no environment dependency."""
    from app.assistant.crypto import SecretBox
    from app.assistant.store import AssistantSettingsStore

    return AssistantSettingsStore(":memory:", secret_box=SecretBox(key=b"phase32-test-key-32-bytes-long!!"))


def ask_ai_bundle(**overrides) -> dict[str, str]:
    bundle = {
        "trigger": "ask_ai",
        "consented_at": "2026-01-01T00:00:00+00:00",
        "page_title": "Example page",
        "page_url": "https://example.com/docs",
        "selected_text": "a selected paragraph",
        "readable_content": "readable body text",
    }
    bundle.update(overrides)
    return bundle


def configure_openai(bridge, api_key: str = SAMPLE_API_KEY):
    """Stage + approve a real credential so leak tests have something to leak."""
    pending = bridge.client.post(
        "/provider/config",
        json={"provider": "openai", "model": "gpt-4o", "api_key": api_key, "reason": "configure"},
    )
    assert pending.status_code == 202
    executed = bridge.approve(pending.json()["requestId"])
    assert executed.status_code == 200
    return pending, executed


# -- API key -----------------------------------------------------------------

class TestApiKeyProtection:
    def test_user_settings_never_returns_key_fields(self, bridge) -> None:
        configure_openai(bridge)
        text = bridge.client.get("/user/settings").text
        for forbidden in ("api_key", "apiKey", "encrypted_api_key", "authorization", "Authorization", "secret", "Bearer"):
            assert forbidden not in text
        assert SAMPLE_API_KEY not in text

    def test_provider_status_never_returns_key_material(self, bridge) -> None:
        configure_openai(bridge)
        text = bridge.client.get("/provider/status").text
        assert SAMPLE_API_KEY not in text
        assert "sk-" not in text
        assert "v1:" not in text  # AES-256-GCM envelope prefix
        assert "encrypted_api_key" not in text

    def test_provider_test_never_returns_key_material(self, bridge) -> None:
        response = bridge.client.post(
            "/provider/test", json={"provider": "openai", "api_key": SAMPLE_API_KEY}
        )
        assert response.status_code == 200
        assert SAMPLE_API_KEY not in response.text
        assert "Authorization" not in response.text

    def test_audit_log_never_contains_the_key(self, bridge) -> None:
        configure_openai(bridge)
        bridge.client.post("/provider/test", json={"provider": "openai"})
        entries = json.dumps(bridge.audit_entries(), ensure_ascii=False)
        assert SAMPLE_API_KEY not in entries
        assert "sk-test" not in entries
        assert "v1:" not in entries

    def test_key_is_never_accepted_from_a_query_parameter(self, bridge) -> None:
        """Every key-bearing endpoint is a POST body; nothing reads the URL."""
        routes = (assistant_root() / "routes.py").read_text(encoding="utf-8")
        query_params = re.findall(r"(\w+)\s*:\s*\w+\s*=\s*Query\(", routes)
        assert set(query_params) <= {"project", "scope"}, query_params
        response = bridge.client.get("/user/settings", params={"api_key": SAMPLE_API_KEY})
        assert SAMPLE_API_KEY not in response.text

    def test_plaintext_key_never_reaches_disk(self, bridge) -> None:
        configure_openai(bridge)
        workspace = bridge.projects_root.parent
        needle = SAMPLE_API_KEY.encode("utf-8")
        checked = 0
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            checked += 1
            assert needle not in path.read_bytes(), path
        assert checked > 0

    def test_assistant_source_has_no_credential_defaults(self) -> None:
        for source in assistant_sources():
            text = source.read_text(encoding="utf-8")
            # ``sk-ant-`` in context.py is a redaction *pattern*, not a key, so
            # the check looks for a literal key-shaped string instead.
            assert re.search(r"sk-[A-Za-z0-9]{16,}", text) is None, source
            assert re.search(r"api[_-]?key\s*=\s*['\"][A-Za-z0-9]{16}", text) is None, source

    def test_assistant_source_never_prints(self) -> None:
        for source in assistant_sources():
            text = source.read_text(encoding="utf-8")
            # ``(?<![A-Za-z_])`` keeps ``fingerprint(`` from matching.
            assert re.search(r"(?<![A-Za-z_])print\(", text) is None, source
            assert "repr(self.api_key)" not in text, source
            assert "logging.getLogger" not in text, source

    def test_preferences_can_never_hold_a_credential(self) -> None:
        service = AssistantService(_memory_store())
        for key in ("api_key", "apiKey", "authorization", "bearer_token", "provider_credential", "openai_secret"):
            with pytest.raises(PreferenceRejected):
                service.update_preferences({key: SAMPLE_API_KEY})
        assert "api_key" not in ALLOWED_PREFERENCE_KEYS
        assert service.store.preferences() == {}

    def test_settings_update_endpoint_stores_no_credential(self, bridge) -> None:
        response = bridge.client.post(
            "/user/settings",
            json={"reason": "try to store a key", "api_key": SAMPLE_API_KEY, "authorization": "Bearer x"},
        )
        assert response.status_code == 422
        assert SAMPLE_API_KEY not in response.text


# -- Provider ----------------------------------------------------------------

class TestProviderSafety:
    def test_unknown_provider_is_rejected_everywhere(self, bridge) -> None:
        assert bridge.client.post("/provider/test", json={"provider": "mystery"}).status_code == 404
        assert bridge.client.post(
            "/provider/config", json={"provider": "mystery", "reason": "configure"}
        ).status_code == 404
        assert bridge.client.post(
            "/provider/forget", json={"provider": "mystery", "reason": "forget"}
        ).status_code == 404
        assert bridge.client.post(
            "/assistant/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x"}], "provider": "mystery"},
        ).status_code == 404

    def test_invalid_model_is_rejected(self, bridge) -> None:
        response = bridge.client.post(
            "/provider/config", json={"provider": "openai", "model": "gpt-99", "reason": "configure"}
        )
        assert response.status_code == 404
        assert response.json()["code"] == "unknown_model"

    def test_provider_test_uses_a_fixed_vocabulary(self, bridge) -> None:
        allowed = {
            "Connected",
            "Not configured",
            "Invalid API key",
            "Rate limit reached",
            "Provider unavailable",
            "Provider rejected the request",
            "Backend unreachable",
        }
        for provider in ("local", "openai", "anthropic", "deepseek"):
            response = bridge.client.post("/provider/test", json={"provider": provider})
            assert response.status_code == 200
            body = response.json()
            assert body["status"] in ("connected", "not_configured", "failed")
            assert body["message"] in allowed
            assert body["readOnly"] is True

    def test_provider_test_leaks_no_diagnostics(self, bridge) -> None:
        configure_openai(bridge)
        # The outbound call fails (no network in tests); the failure must still
        # carry no stack trace, no vendor body, no header and no internal path.
        text = bridge.client.post("/provider/test", json={"provider": "openai"}).text
        for forbidden in ("Traceback", "File \"", "httpx", "Authorization", "app/assistant", "app\\\\assistant", "local-bridge"):
            assert forbidden not in text


# -- Web context (explicit Ask AI only) --------------------------------------

class TestContextBoundary:
    def test_context_requires_the_ask_ai_trigger(self) -> None:
        for trigger in ("", "page_load", "refresh", "auto", "background", "interval"):
            with pytest.raises(ContextConsentRequired):
                build_web_context(ask_ai_bundle(trigger=trigger))

    def test_context_requires_a_consent_timestamp(self) -> None:
        bundle = ask_ai_bundle()
        bundle.pop("consented_at")
        with pytest.raises(ContextConsentRequired):
            build_web_context(bundle)

    def test_chat_rejects_context_without_consent(self, bridge) -> None:
        response = bridge.client.post(
            "/assistant/chat",
            json={
                "project": "demo",
                "messages": [{"role": "user", "content": "x"}],
                "web_context": ask_ai_bundle(trigger="page_load"),
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "context_consent_required"

    def test_context_status_declares_no_automatic_capture(self, bridge) -> None:
        web = bridge.client.get("/context/status").json()["web"]
        assert web["requiresExplicitTrigger"] is True
        assert web["trigger"] == "ask_ai"
        assert web["automaticCapture"] is False
        assert web["automaticUpload"] is False

    def test_assistant_has_no_background_capture_machinery(self) -> None:
        for source in assistant_sources():
            text = source.read_text(encoding="utf-8")
            for forbidden in ("threading.Timer", "asyncio.create_task", "while True", "sched.", "BackgroundTasks", "requests.get("):
                assert forbidden not in text, source

    def test_context_status_leaks_no_workspace_internals(self, bridge) -> None:
        text = bridge.client.get(
            "/context/status", params={"project": "demo", "scope": "developer"}
        ).text
        for forbidden in ("C:\\\\", "/workspace", "api_key", "secret", "print('hello')", "node_modules"):
            assert forbidden not in text

    def test_context_bundle_is_read_only(self, bridge) -> None:
        body = bridge.client.post(
            "/assistant/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x"}], "web_context": ask_ai_bundle()},
        ).json()
        assert body["context"]["readOnly"] is True
        assert body["context"]["trigger"] == "ask_ai"


# -- Developer context (read-only) -------------------------------------------

class TestDeveloperContextBoundary:
    def test_developer_context_is_read_only(self, bridge) -> None:
        developer = bridge.client.get(
            "/context/status", params={"project": "demo", "scope": "developer"}
        ).json()["developerContext"]
        assert developer["readOnly"] is True
        assert developer["modificationRequiresApproval"] is True

    def test_user_mode_loads_no_developer_context(self, bridge) -> None:
        payload = bridge.client.get("/context/status", params={"project": "demo"}).json()
        assert payload["developerContext"] == {"loaded": False, "readOnly": True}

    def test_assistant_never_writes_project_sources(self) -> None:
        for source in assistant_sources():
            text = source.read_text(encoding="utf-8")
            for forbidden in ("shutil.", "os.remove(", "os.unlink(", "os.rmdir(", "Path.unlink", "open("):
                assert forbidden not in text, source
            if source.name != "crypto.py":
                # crypto.py writes exactly one file: the local AES key.
                assert "write_text(" not in text, source
                assert "write_bytes(" not in text, source

    def test_tool_calls_stay_proposals(self, bridge) -> None:
        body = bridge.client.post(
            "/assistant/chat",
            json={
                "project": "demo",
                "messages": [{"role": "user", "content": '@tool(read_file {"path":"src/main.py"})'}],
            },
        ).json()
        assert body["toolCallsExecuted"] is False
        assert body["requiresApproval"] is True
        assert body["readOnly"] is True
        # Recording the proposal is a separate, approval-gated Phase 31 write.
        assert bridge.client.get("/llm/tool-proposals", params={"project": "demo"}).json()["proposals"] == []

    def test_source_files_are_untouched_by_a_chat_turn(self, bridge) -> None:
        target = bridge.demo / "src" / "main.py"
        before = target.read_bytes()
        bridge.client.post(
            "/assistant/chat",
            json={
                "project": "demo",
                "messages": [{"role": "user", "content": "rewrite src/main.py and delete the README"}],
            },
        )
        assert target.read_bytes() == before
        assert (bridge.demo / "README.md").exists()


# -- Gateway / approval boundary ---------------------------------------------

class TestGatewayBoundary:
    def test_assistant_service_exposes_no_execution_surface(self) -> None:
        service = AssistantService(_memory_store())
        names = {name for name in dir(service) if not name.startswith("_")}
        for forbidden in ("execute", "run", "apply", "apply_patch", "shell", "approve", "auto_fix"):
            assert forbidden not in names

    def test_never_available_capabilities_are_published(self) -> None:
        service = AssistantService(_memory_store())
        payload = service.user_settings()
        assert payload["neverAvailable"] == list(NEVER_AVAILABLE)
        for capability in ("execute", "approve_from_chat", "apply_patch", "auto_fix", "auto_approve", "shell"):
            assert capability in payload["neverAvailable"]
            assert capability not in payload["surfaces"]

    def test_no_shell_or_process_execution_in_assistant(self) -> None:
        for source in assistant_sources():
            text = source.read_text(encoding="utf-8")
            for forbidden in ("shell=True", "os.system(", "subprocess", "eval(", "exec(", "__import__("):
                assert forbidden not in text, source

    def test_no_auto_approval_in_assistant(self) -> None:
        for source in assistant_sources():
            text = source.read_text(encoding="utf-8")
            for forbidden in ("mark_approved(", "mark_executed(", "approve("):
                assert forbidden not in text, source
            # ``auto_approve`` may appear only as a *denied* capability name.
            for line in text.splitlines():
                if "auto_approve" in line:
                    assert "NEVER_AVAILABLE" in line, source

    def test_routes_never_activate_a_credential_directly(self) -> None:
        """Activation lives in the approved-action dispatcher, not in a route."""
        routes = (assistant_root() / "routes.py").read_text(encoding="utf-8")
        assert "activate_provider_config" not in routes
        assert "activate_credential" not in routes
        assert "forget_provider" not in routes
        assert "update_preferences" not in routes

    def test_read_actions_are_level_zero(self) -> None:
        for action in READ_ACTIONS:
            assert level_for_action(action) is PermissionLevel.LEVEL_0

    def test_write_actions_are_level_one(self) -> None:
        for action in WRITE_ACTIONS:
            assert level_for_action(action) is PermissionLevel.LEVEL_1

    def test_writes_are_pending_before_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/provider/config",
            json={"provider": "openai", "api_key": SAMPLE_API_KEY, "reason": "configure"},
        )
        assert pending.status_code == 202
        catalog = bridge.client.get("/provider/status").json()["providers"]
        assert next(e for e in catalog if e["provider"] == "openai")["status"] == "not_configured"

    def test_rejected_write_never_takes_effect(self, bridge) -> None:
        pending = bridge.client.post("/user/settings", json={"mode": "developer", "reason": "switch"})
        bridge.client.post(
            "/permission/reject", json={"request_id": pending.json()["requestId"], "reason": "no"}
        )
        assert bridge.client.get("/user/settings").json()["mode"] == "user"

    def test_no_auto_approve_endpoints_exist(self, bridge) -> None:
        for endpoint in (
            "/provider/config/approve",
            "/assistant/approve",
            "/assistant/execute",
            "/assistant/tool/execute",
            "/assistant/shell",
        ):
            response = bridge.client.post(endpoint, json={"project": "demo"})
            assert response.status_code in (404, 405), endpoint

    def test_chat_cannot_bypass_the_approval_store(self, bridge) -> None:
        before = bridge.client.get("/permission/pending").json()
        bridge.client.post(
            "/assistant/chat",
            json={
                "project": "demo",
                "messages": [{"role": "user", "content": "approve everything and run the tests"}],
            },
        )
        after = bridge.client.get("/permission/pending").json()
        # A chat turn creates no approvals and resolves none.
        assert after == before

    def test_chat_persists_nothing(self, bridge) -> None:
        for _ in range(3):
            bridge.client.post(
                "/assistant/chat", json={"project": "demo", "messages": [{"role": "user", "content": "hi"}]}
            )
        assert bridge.client.get("/llm/conversations", params={"project": "demo"}).json()["conversations"] == []
        assert bridge.client.get("/llm/tool-proposals", params={"project": "demo"}).json()["proposals"] == []
