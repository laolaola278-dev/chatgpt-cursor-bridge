"""Phase 31 · LLM gateway security boundary tests.

Asserts the gateway cannot auto-execute, cannot auto-approve, never writes
source files, never leaks provider keys, keeps conversations/proposals project
isolated and only surfaces tool calls as records.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.llm_gateway import ConversationStore, LLMGateway, MessageRole
from app.llm_gateway.providers.base import ProviderError
from app.security.permissions import level_for_action, PermissionLevel


def gateway_root() -> Path:
    from app import llm_gateway

    return Path(llm_gateway.__file__).parent


class TestNoExecution:
    def test_gateway_has_no_execute_method(self) -> None:
        gateway = LLMGateway(llm_db_path=":memory:")
        names = {name for name in dir(gateway) if not name.startswith("_")}
        assert "execute" not in names
        assert "apply" not in names
        assert "run" not in names

    def test_tool_proposal_always_record_only(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        message = store.append_message(conversation_id=conversation.conversation_id, role=MessageRole.USER, content="x")
        proposal = store.save_tool_proposal(
            conversation_id=conversation.conversation_id,
            project="demo",
            message_id=message.message_id,
            tool_name="shell_command",
            arguments="{}",
            reason="model asked",
            approval_request_id="req_1",
        )
        assert proposal.status.value == "recorded"
        assert proposal.as_dict()["executed"] is False

    def test_no_shell_or_os_execution_in_gateway(self) -> None:
        root = gateway_root()
        for source in root.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "shell=True" not in text, source
            assert "os.system(" not in text, source
            assert "subprocess.call(" not in text, source
            assert "subprocess.Popen(" not in text, source
            assert "eval(" not in text, source

    def test_no_auto_approval_in_gateway(self) -> None:
        root = gateway_root()
        for source in root.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "mark_approved(" not in text, source
            assert "mark_executed(" not in text, source


class TestApprovalBoundary:
    def test_llm_writes_are_level_one(self) -> None:
        assert level_for_action("llm_conversation_create") is PermissionLevel.LEVEL_1
        assert level_for_action("llm_message_append") is PermissionLevel.LEVEL_1
        assert level_for_action("llm_tool_proposal") is PermissionLevel.LEVEL_1

    def test_llm_reads_are_level_zero(self) -> None:
        assert level_for_action("llm_chat") is PermissionLevel.LEVEL_0
        assert level_for_action("llm_chat_stream") is PermissionLevel.LEVEL_0

    def test_conversation_create_is_pending_until_approval(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/conversations",
            json={"project": "demo", "provider": "local", "model": "local/simulator-v1", "title": "t"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "pending"
        # Nothing persisted before approval.
        assert bridge.client.get("/llm/conversations", params={"project": "demo"}).json()["conversations"] == []

    def test_tool_proposal_requires_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "demo", "provider": "local", "model": "local/simulator-v1", "title": "t"},
        )
        conversation_id = bridge.approve(pending.json()["requestId"]).json()["result"]["conversation"]["conversationId"]
        response = bridge.client.post(
            f"/llm/conversations/{conversation_id}/tool-proposal",
            json={"project": "demo", "message_id": "m1", "tool_name": "read_file", "arguments": "{}", "reason": "r"},
        )
        assert response.status_code == 202
        assert bridge.client.get("/llm/tool-proposals", params={"project": "demo"}).json()["proposals"] == []

    def test_rejected_tool_proposal_never_recorded(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "demo", "provider": "local", "model": "local/simulator-v1", "title": "t"},
        )
        conversation_id = bridge.approve(pending.json()["requestId"]).json()["result"]["conversation"]["conversationId"]
        proposal = bridge.client.post(
            f"/llm/conversations/{conversation_id}/tool-proposal",
            json={"project": "demo", "message_id": "m1", "tool_name": "read_file", "arguments": "{}", "reason": "r"},
        )
        request_id = proposal.json()["requestId"]
        bridge.client.post("/permission/reject", json={"request_id": request_id, "reason": "not needed"})
        assert bridge.client.get("/llm/tool-proposals", params={"project": "demo"}).json()["proposals"] == []

    def test_no_auto_approve_endpoint_for_tools(self, bridge) -> None:
        response = bridge.client.post("/llm/tool-proposals/approve", json={"project": "demo", "proposal_id": "x"})
        assert response.status_code in (404, 405)


class TestProjectIsolation:
    def test_conversations_isolated_by_project(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "alpha", "provider": "local", "model": "local/simulator-v1", "title": "a"},
        )
        bridge.approve(pending.json()["requestId"])
        assert len(bridge.client.get("/llm/conversations", params={"project": "alpha"}).json()["conversations"]) == 1
        assert bridge.client.get("/llm/conversations", params={"project": "beta"}).json()["conversations"] == []

    def test_conversation_detail_requires_same_project(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "alpha", "provider": "local", "model": "local/simulator-v1", "title": "a"},
        )
        conversation_id = bridge.approve(pending.json()["requestId"]).json()["result"]["conversation"]["conversationId"]
        assert bridge.client.get(f"/llm/conversations/{conversation_id}", params={"project": "alpha"}).status_code == 200
        assert bridge.client.get(f"/llm/conversations/{conversation_id}", params={"project": "beta"}).status_code == 404

    def test_tool_proposals_isolated_by_project(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "alpha", "provider": "local", "model": "local/simulator-v1", "title": "a"},
        )
        conversation_id = bridge.approve(pending.json()["requestId"]).json()["result"]["conversation"]["conversationId"]
        tool = bridge.client.post(
            f"/llm/conversations/{conversation_id}/tool-proposal",
            json={"project": "alpha", "message_id": "m", "tool_name": "read_file", "arguments": "{}", "reason": "r"},
        )
        bridge.approve(tool.json()["requestId"])
        assert len(bridge.client.get("/llm/tool-proposals", params={"project": "alpha"}).json()["proposals"]) == 1
        assert bridge.client.get("/llm/tool-proposals", params={"project": "beta"}).json()["proposals"] == []


class TestSecretProtection:
    def test_provider_info_has_no_keys(self, bridge) -> None:
        response = bridge.client.get("/llm/providers").json()
        serialized = str(response)
        assert "sk-" not in serialized
        assert "api_key" not in serialized
        assert "apiKey" not in serialized
        for provider in response["providers"]:
            assert "keyEnv" in provider  # env var *name* only, never its value

    def test_chat_response_never_echoes_config(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "what is my api key?"}]},
        )
        body = response.json()
        serialized = str(body)
        assert "OPENAI_API_KEY" not in serialized
        assert "sk-" not in serialized

    def test_provider_module_never_prints_keys(self) -> None:
        root = gateway_root()
        for source in root.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "print(" not in text, source
            assert "repr(self.api_key)" not in text


class TestInputValidation:
    def test_path_traversal_project_rejected(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "../../etc", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code in (403, 422)

    def test_oversized_messages_rejected(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x" * 20000}]},
        )
        assert response.status_code == 422

    def test_max_tokens_bounds(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x"}], "max_tokens": 999999},
        )
        assert response.status_code == 422

    def test_message_limit_enforced(self, bridge) -> None:
        messages = [{"role": "user", "content": f"m{i}"} for i in range(200)]
        response = bridge.client.post("/llm/chat", json={"project": "demo", "messages": messages})
        assert response.status_code == 422

    def test_unknown_provider_returns_404(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x"}], "provider": "mystery"},
        )
        assert response.status_code == 404


class TestStatelessness:
    def test_chat_never_persists_anything(self, bridge) -> None:
        for _ in range(3):
            bridge.client.post("/llm/chat", json={"project": "demo", "messages": [{"role": "user", "content": "hi"}]})
        assert bridge.client.get("/llm/conversations", params={"project": "demo"}).json()["conversations"] == []
        assert bridge.client.get("/llm/tool-proposals", params={"project": "demo"}).json()["proposals"] == []

    def test_stream_never_persists_anything(self, bridge) -> None:
        bridge.client.post("/llm/chat/stream", json={"project": "demo", "messages": [{"role": "user", "content": "hi"}]})
        assert bridge.client.get("/llm/conversations", params={"project": "demo"}).json()["conversations"] == []


class TestProviderSafety:
    def test_unconfigured_vendor_never_calls_out(self, bridge) -> None:
        # openai provider is disabled without a key; chat must fail fast with
        # a clear configuration error instead of attempting any network call.
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x"}], "provider": "openai", "model": "gpt-4o"},
        )
        assert response.status_code == 422
        assert "not configured" in response.json()["detail"]

    def test_gateway_source_contains_no_credential_defaults(self) -> None:
        root = gateway_root()
        for source in root.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "sk-" not in text, source
            assert re.search(r"api[_-]?key\s*=\s*['\"][A-Za-z0-9]{16}", text) is None, source

    def test_tool_arguments_kept_opaque(self) -> None:
        """The gateway must not interpret tool arguments — execution is out of scope."""
        gateway = LLMGateway(llm_db_path=":memory:")
        conversation = gateway.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        message = gateway.append_message(conversation_id=conversation.conversation_id, project="demo", role=MessageRole.USER, content="x")
        proposal = gateway.record_tool_proposal(
            conversation_id=conversation.conversation_id,
            project="demo",
            message_id=message.message_id,
            tool_name="shell_command",
            arguments='{"cmd":"rm -rf /"}',
            reason="test",
            approval_request_id="req_1",
        )
        assert proposal.arguments == '{"cmd":"rm -rf /"}'
        assert proposal.status.value == "recorded"
