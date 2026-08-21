"""Phase 31 · LLM Provider Integration Layer tests.

Covers the unified message protocol, provider registry, model registry,
stateless chat, streaming, conversation persistence (approval-gated),
tool-call proposals (record-only) and the API surface.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.llm_gateway import (
    ChatMessage,
    ChatRequest,
    ConversationStore,
    LLMGateway,
    MessageRole,
    ModelRegistry,
    ProviderRegistry,
    ToolCall,
)
from app.llm_gateway.providers.base import ProviderError


def make_gateway() -> tuple[LLMGateway, str]:
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "llm.db")
    return LLMGateway(llm_db_path=db), db


def user_message(content: str) -> ChatMessage:
    return ChatMessage(role=MessageRole.USER, content=content)


# -- Task 1 · Unified Message Protocol -------------------------------------

class TestMessageProtocol:
    def test_roles_roundtrip(self) -> None:
        for role in MessageRole:
            message = ChatMessage(role=role, content=f"content-{role.value}")
            restored = ChatMessage.from_dict(message.as_dict())
            assert restored.role is role
            assert restored.content == f"content-{role.value}"

    def test_unknown_role_coerces_to_user(self) -> None:
        restored = ChatMessage.from_dict({"role": "robot", "content": "x"})
        assert restored.role is MessageRole.USER

    def test_tool_calls_roundtrip(self) -> None:
        tool = ToolCall(name="read_file", arguments='{"path":"a.py"}', call_id="tool_1")
        message = ChatMessage(role=MessageRole.ASSISTANT, content="", tool_calls=(tool,))
        restored = ChatMessage.from_dict(message.as_dict())
        assert len(restored.tool_calls) == 1
        assert restored.tool_calls[0].name == "read_file"
        assert restored.tool_calls[0].arguments == '{"path":"a.py"}'

    def test_protocol_preserves_system_user_assistant_tool(self) -> None:
        messages = (
            ChatMessage(role=MessageRole.SYSTEM, content="system prompt"),
            ChatMessage(role=MessageRole.USER, content="user text"),
            ChatMessage(role=MessageRole.ASSISTANT, content="assistant text"),
            ChatMessage(role=MessageRole.TOOL, content="tool result"),
        )
        request = ChatRequest(project="demo", messages=messages, model="local/simulator-v1")
        restored = ChatRequest.from_dict(request.as_dict())
        assert [item.role for item in restored.messages] == [
            MessageRole.SYSTEM,
            MessageRole.USER,
            MessageRole.ASSISTANT,
            MessageRole.TOOL,
        ]

    def test_chat_request_defaults(self) -> None:
        request = ChatRequest.from_dict({"project": "demo", "messages": [{"role": "user", "content": "hi"}]})
        assert request.model == "local/simulator-v1"
        assert request.temperature == 0.4
        assert request.max_tokens == 2048


# -- Task 2 · Provider Registry ---------------------------------------------

class TestProviderRegistry:
    def test_registered_providers(self) -> None:
        registry = ProviderRegistry(providers={})
        registry.register("local", _FakeProvider("local"))
        registry.register("openai", _FakeProvider("openai"))
        assert registry.names() == ["local", "openai"]

    def test_duplicate_register_rejected(self) -> None:
        registry = ProviderRegistry(providers={})
        registry.register("local", _FakeProvider("local"))
        with pytest.raises(ValueError):
            registry.register("local", _FakeProvider("local"))

    def test_unknown_provider_raises(self) -> None:
        registry = ProviderRegistry(providers={})
        with pytest.raises(ProviderError):
            registry.get("nope")

    def test_default_registry_contains_all_vendors(self) -> None:
        registry = ProviderRegistry()
        names = registry.names()
        assert "local" in names
        assert "openai" in names
        assert "anthropic" in names
        assert "deepseek" in names

    def test_vendor_providers_disabled_without_keys(self) -> None:
        registry = ProviderRegistry()
        for info in registry.providers():
            if info["name"] == "local":
                assert info["enabled"] is True
            else:
                assert info["enabled"] is False  # no API keys in tests

    def test_provider_info_never_exposes_keys(self) -> None:
        registry = ProviderRegistry()
        for info in registry.providers():
            assert "key" not in json.dumps(info).lower() or "keyenv" in json.dumps(info).lower()
            assert "sk-" not in json.dumps(info)
            assert "Bearer" not in json.dumps(info)

    def test_resolve_returns_provider_and_model(self) -> None:
        registry = ProviderRegistry()
        provider, entry = registry.resolve("local", "local/simulator-v1")
        assert entry["id"] == "local/simulator-v1"

    def test_resolve_unknown_model_raises(self) -> None:
        registry = ProviderRegistry()
        with pytest.raises(ProviderError):
            registry.resolve("local", "local/nope")


# -- Task 2 · Model Registry ------------------------------------------------

class TestModelRegistry:
    def test_model_catalogue_contains_required_models(self) -> None:
        registry = ModelRegistry()
        ids = {model["id"] for model in registry.all()}
        assert {"gpt-5", "gpt-4o", "gpt-4-turbo", "claude-3-5-sonnet", "claude-3-7-sonnet", "deepseek-chat", "deepseek-reasoner"}.issubset(ids)

    def test_models_by_provider(self) -> None:
        registry = ModelRegistry()
        openai_models = registry.by_provider("openai")
        assert all(model["provider"] == "openai" for model in openai_models)
        assert any(model["id"] == "gpt-5" for model in openai_models)

    def test_get_model(self) -> None:
        registry = ModelRegistry()
        model = registry.get("deepseek-chat")
        assert model is not None
        assert model["provider"] == "deepseek"

    def test_get_missing_model(self) -> None:
        registry = ModelRegistry()
        assert registry.get("nope/nope") is None

    def test_model_entries_carry_capabilities(self) -> None:
        registry = ModelRegistry()
        gpt5 = registry.get("gpt-5")
        assert gpt5 is not None
        assert "tool_calling" in gpt5["capabilities"]
        assert gpt5["contextWindow"] > 0


# -- Task 3 · Local Simulator Chat ------------------------------------------

class TestLocalChat:
    def test_chat_returns_simulated_reply(self) -> None:
        gateway, _ = make_gateway()
        result = gateway.chat(ChatRequest(project="demo", messages=(user_message("hello world"),)))
        assert result.simulated is True
        assert result.provider == "local"
        assert "simulated" in result.reply
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] > 0

    def test_chat_detects_tool_calls_as_proposals(self) -> None:
        gateway, _ = make_gateway()
        result = gateway.chat(
            ChatRequest(project="demo", messages=(user_message('@tool(read_file {"path":"a.py"})'),))
        )
        assert len(result.tool_calls) == 1
        tool = result.tool_calls[0]
        assert tool.name == "read_file"
        assert "a.py" in tool.arguments
        assert result.finish_reason == "tool_calls"

    def test_chat_with_empty_messages_adds_user_placeholder(self) -> None:
        gateway, _ = make_gateway()
        result = gateway.chat(ChatRequest(project="demo", messages=(ChatMessage(role=MessageRole.SYSTEM, content="s"),)))
        assert result.simulated is True

    def test_chat_is_stateless(self) -> None:
        gateway, db = make_gateway()
        gateway.chat(ChatRequest(project="demo", messages=(user_message("hi"),)))
        store = ConversationStore(db)
        assert store.list_conversations("demo") == []

    def test_chat_deterministic(self) -> None:
        gateway, _ = make_gateway()
        request = ChatRequest(project="demo", messages=(user_message("same input"),))
        first = gateway.chat(request)
        second = gateway.chat(request)
        assert first.reply == second.reply


# -- Task 3 · Streaming -----------------------------------------------------

class TestStreaming:
    def test_stream_emits_deltas_then_done(self) -> None:
        gateway, _ = make_gateway()
        events = list(gateway.stream(ChatRequest(project="demo", messages=(user_message("stream me"),))))
        assert events[-1].kind == "done"
        deltas = [event for event in events if event.kind == "delta"]
        assert len(deltas) > 0
        assert all(event.content for event in deltas)

    def test_stream_reassembles_reply(self) -> None:
        gateway, _ = make_gateway()
        events = list(gateway.stream(ChatRequest(project="demo", messages=(user_message("reassemble"),))))
        text = "".join(event.content for event in events if event.kind == "delta")
        assert "simulated" in text
        assert text.endswith(".")

    def test_stream_emits_tool_call_events(self) -> None:
        gateway, _ = make_gateway()
        events = list(gateway.stream(ChatRequest(project="demo", messages=(user_message('@tool(read_file {})'),))))
        tool_events = [event for event in events if event.kind == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0].tool_call is not None
        assert tool_events[0].tool_call.name == "read_file"


# -- Task 4 · Gateway Errors ------------------------------------------------

class TestGatewayErrors:
    def test_unknown_provider_raises_404(self) -> None:
        gateway, _ = make_gateway()
        with pytest.raises(ProviderError) as exc:
            gateway.chat(ChatRequest(project="demo", messages=(user_message("x"),), provider="nope", model="local/simulator-v1"))
        assert exc.value.status == 404

    def test_unknown_model_raises_404(self) -> None:
        gateway, _ = make_gateway()
        with pytest.raises(ProviderError) as exc:
            gateway.chat(ChatRequest(project="demo", messages=(user_message("x"),), model="gpt-99"))
        assert exc.value.status == 404

    def test_unconfigured_vendor_raises_422(self) -> None:
        gateway, _ = make_gateway()
        with pytest.raises(ProviderError) as exc:
            gateway.chat(ChatRequest(project="demo", messages=(user_message("x"),), provider="openai", model="gpt-4o"))
        assert exc.value.status == 422
        assert "not configured" in exc.value.message


# -- Task 5 · Conversation Persistence --------------------------------------

class TestConversationStore:
    def test_create_and_get(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t", agent="ASSISTANT")
        assert store.get_conversation(conversation.conversation_id, "demo") is not None
        assert store.get_conversation(conversation.conversation_id) is not None

    def test_project_isolation(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="alpha", provider="local", model="local/simulator-v1", title="t")
        assert store.get_conversation(conversation.conversation_id, "beta") is None
        assert store.list_conversations("beta") == []

    def test_list_filters_by_agent(self) -> None:
        store = ConversationStore(":memory:")
        store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="a", agent="PLANNER")
        store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="b", agent="CODER")
        assert len(store.list_conversations("demo")) == 2
        assert len(store.list_conversations("demo", agent="CODER")) == 1

    def test_append_and_list_messages(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        first = store.append_message(conversation_id=conversation.conversation_id, role=MessageRole.USER, content="one")
        second = store.append_message(conversation_id=conversation.conversation_id, role=MessageRole.ASSISTANT, content="two")
        messages = store.list_messages(conversation.conversation_id)
        assert [message.content for message in messages] == ["one", "two"]
        assert messages[0].message_id == first.message_id
        assert messages[1].message_id == second.message_id

    def test_messages_carry_tool_calls(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        tool = ToolCall(name="search", arguments="{}", call_id="c1")
        message = store.append_message(conversation_id=conversation.conversation_id, role=MessageRole.ASSISTANT, content="", tool_calls=(tool,))
        restored = store.list_messages(conversation.conversation_id)[0]
        assert restored.message_id == message.message_id
        assert restored.tool_calls[0].name == "search"

    def test_append_updates_timestamp(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        before = conversation.updated_at
        store.append_message(conversation_id=conversation.conversation_id, role=MessageRole.USER, content="x")
        after = store.get_conversation(conversation.conversation_id, "demo")
        assert after is not None
        assert after.updated_at >= before


# -- Task 6 · Tool-Call Proposals -------------------------------------------

class TestToolProposals:
    def test_proposal_recorded_with_approval_id(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        message = store.append_message(conversation_id=conversation.conversation_id, role=MessageRole.USER, content="use tool")
        proposal = store.save_tool_proposal(
            conversation_id=conversation.conversation_id,
            project="demo",
            message_id=message.message_id,
            tool_name="read_file",
            arguments='{"path":"x"}',
            reason="model requested a read",
            approval_request_id="req_42",
        )
        assert proposal.status.value == "recorded"
        assert proposal.approval_request_id == "req_42"
        assert proposal.as_dict()["executed"] is False

    def test_proposal_list_and_get(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        message = store.append_message(conversation_id=conversation.conversation_id, role=MessageRole.USER, content="use tool")
        proposal = store.save_tool_proposal(
            conversation_id=conversation.conversation_id, project="demo",
            message_id=message.message_id, tool_name="run", arguments="{}", reason="r",
        )
        assert store.get_tool_proposal(proposal.proposal_id, "demo") is not None
        assert store.get_tool_proposal(proposal.proposal_id, "other") is None
        assert len(store.list_tool_proposals("demo")) == 1
        assert len(store.list_tool_proposals("demo", conversation_id=conversation.conversation_id)) == 1

    def test_proposal_project_isolation(self) -> None:
        store = ConversationStore(":memory:")
        conversation = store.create_conversation(project="alpha", provider="local", model="local/simulator-v1", title="t")
        store.save_tool_proposal(conversation_id=conversation.conversation_id, project="alpha", message_id="m", tool_name="x", arguments="{}", reason="r")
        assert store.list_tool_proposals("beta") == []

    def test_gateway_record_tool_proposal(self) -> None:
        gateway, _ = make_gateway()
        conversation = gateway.create_conversation(project="demo", provider="local", model="local/simulator-v1", title="t")
        message = gateway.append_message(conversation_id=conversation.conversation_id, project="demo", role=MessageRole.USER, content="hi")
        proposal = gateway.record_tool_proposal(
            conversation_id=conversation.conversation_id, project="demo",
            message_id=message.message_id, tool_name="read_file", arguments="{}",
            reason="model request", approval_request_id="req_7",
        )
        assert proposal.tool_name == "read_file"
        assert proposal.approval_request_id == "req_7"

    def test_gateway_rejects_unknown_conversation(self) -> None:
        gateway, _ = make_gateway()
        with pytest.raises(ValueError):
            gateway.append_message(conversation_id="missing", project="demo", role=MessageRole.USER, content="x")


# -- Task 7 · API -----------------------------------------------------------

class TestLlmApi:
    def test_get_providers(self, bridge) -> None:
        response = bridge.client.get("/llm/providers")
        assert response.status_code == 200
        names = {item["name"] for item in response.json()["providers"]}
        assert {"local", "openai", "anthropic", "deepseek"}.issubset(names)

    def test_get_models(self, bridge) -> None:
        response = bridge.client.get("/llm/models")
        assert response.status_code == 200
        ids = {model["id"] for model in response.json()["models"]}
        assert "gpt-5" in ids
        assert "deepseek-reasoner" in ids
        assert "claude-3-5-sonnet" in ids

    def test_get_models_filtered_by_provider(self, bridge) -> None:
        response = bridge.client.get("/llm/models", params={"provider": "deepseek"})
        assert response.status_code == 200
        models = response.json()["models"]
        assert all(model["provider"] == "deepseek" for model in models)

    def test_chat_post_stateless(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "hello"}], "model": "local/simulator-v1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["simulated"] is True
        assert body["readOnly"] is True
        assert "simulated" in body["reply"]

    def test_chat_post_rejects_bad_project(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "../evil", "messages": [{"role": "user", "content": "x"}]},
        )
        assert response.status_code in (403, 422)

    def test_chat_post_rejects_empty_messages(self, bridge) -> None:
        response = bridge.client.post("/llm/chat", json={"project": "demo", "messages": []})
        assert response.status_code == 422

    def test_chat_post_unconfigured_provider(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x"}], "provider": "openai", "model": "gpt-4o"},
        )
        assert response.status_code == 422
        assert "not configured" in response.json()["detail"]

    def test_chat_post_unknown_model(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat",
            json={"project": "demo", "messages": [{"role": "user", "content": "x"}], "model": "gpt-99"},
        )
        assert response.status_code == 404

    def test_chat_stream_sse(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/chat/stream",
            json={"project": "demo", "messages": [{"role": "user", "content": "stream api"}], "model": "local/simulator-v1"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        text = response.text
        assert "data: " in text
        assert '"type": "done"' in text
        assert "delta" in text

    def test_chat_does_not_persist(self, bridge) -> None:
        bridge.client.post("/llm/chat", json={"project": "demo", "messages": [{"role": "user", "content": "hello"}]})
        response = bridge.client.get("/llm/conversations", params={"project": "demo"})
        assert response.json()["conversations"] == []

    def test_conversation_create_requires_approval(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "demo", "provider": "local", "model": "local/simulator-v1", "title": "my chat", "reason": "start a conversation"},
        )
        assert pending.status_code == 202
        assert pending.json()["status"] == "pending"

    def test_conversation_create_approval_persists(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "demo", "provider": "local", "model": "local/simulator-v1", "title": "my chat"},
        )
        executed = bridge.approve(pending.json()["requestId"])
        assert executed.status_code == 200
        result = executed.json()["result"]
        assert result["readOnlyAnalysis"] is True
        conversation_id = result["conversation"]["conversationId"]
        detail = bridge.client.get("/llm/conversations", params={"project": "demo"}).json()
        assert any(item["conversationId"] == conversation_id for item in detail["conversations"])

    def test_conversation_create_rejects_bad_project(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/conversations",
            json={"project": "../evil", "title": "t"},
        )
        assert response.status_code in (403, 422)

    def test_message_append_approval_persists(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "demo", "provider": "local", "model": "local/simulator-v1", "title": "chat"},
        )
        conversation_id = bridge.approve(pending.json()["requestId"]).json()["result"]["conversation"]["conversationId"]

        message_pending = bridge.client.post(
            f"/llm/conversations/{conversation_id}/messages",
            json={"project": "demo", "content": "remember this", "reason": "log a message"},
        )
        assert message_pending.status_code == 202
        executed = bridge.approve(message_pending.json()["requestId"])
        assert executed.status_code == 200

        detail = bridge.client.get(f"/llm/conversations/{conversation_id}", params={"project": "demo"}).json()
        assert any(message["content"] == "remember this" for message in detail["messages"])

    def test_message_append_unknown_conversation(self, bridge) -> None:
        response = bridge.client.post(
            "/llm/conversations/missing/messages",
            json={"project": "demo", "content": "x"},
        )
        assert response.status_code == 404

    def test_tool_proposal_approval_records_only(self, bridge) -> None:
        pending = bridge.client.post(
            "/llm/conversations",
            json={"project": "demo", "provider": "local", "model": "local/simulator-v1", "title": "chat"},
        )
        conversation_id = bridge.approve(pending.json()["requestId"]).json()["result"]["conversation"]["conversationId"]

        tool_pending = bridge.client.post(
            f"/llm/conversations/{conversation_id}/tool-proposal",
            json={"project": "demo", "message_id": "msg_1", "tool_name": "read_file", "arguments": '{"path":"x"}', "reason": "model wants to read a file"},
        )
        assert tool_pending.status_code == 202
        executed = bridge.approve(tool_pending.json()["requestId"])
        assert executed.status_code == 200
        result = executed.json()["result"]
        assert result["executed"] is False
        assert result["proposal"]["toolName"] == "read_file"

        proposals = bridge.client.get("/llm/tool-proposals", params={"project": "demo"}).json()["proposals"]
        assert len(proposals) == 1
        assert proposals[0]["executed"] is False
        assert proposals[0]["status"] == "recorded"

    def test_conversation_detail_unknown(self, bridge) -> None:
        response = bridge.client.get("/llm/conversations/nope", params={"project": "demo"})
        assert response.status_code == 404

    def test_tool_proposals_empty(self, bridge) -> None:
        response = bridge.client.get("/llm/tool-proposals", params={"project": "demo"})
        assert response.status_code == 200
        assert response.json()["proposals"] == []


class _FakeProvider:
    """Tiny provider stub for registry tests."""

    name = ""
    enabled = True

    def __init__(self, name: str) -> None:
        self.name = name

    def list_models(self) -> list[dict]:
        return [{"id": f"{self.name}/model", "provider": self.name, "displayName": self.name, "capabilities": [], "contextWindow": 1000, "enabled": True}]
