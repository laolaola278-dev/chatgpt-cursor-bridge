import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderLlmGatewayDashboard } from "../src/llm/llm-dashboard";
import type { LlmGatewaySnapshot } from "../src/llm/types";
import { ExtensionStore, createInitialState } from "../src/state/store";

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

function snapshotFixture(overrides: Partial<LlmGatewaySnapshot> = {}): LlmGatewaySnapshot {
  return {
    providers: [
      { name: "local", enabled: true, keyEnv: "", models: ["local/simulator-v1", "local/architect-v1"] },
      { name: "openai", enabled: false, keyEnv: "OPENAI_API_KEY", models: ["gpt-5", "gpt-4o"] },
      { name: "anthropic", enabled: false, keyEnv: "ANTHROPIC_API_KEY", models: ["claude-3-5-sonnet"] },
      { name: "deepseek", enabled: false, keyEnv: "DEEPSEEK_API_KEY", models: ["deepseek-chat", "deepseek-reasoner"] },
    ],
    models: [
      { id: "local/simulator-v1", provider: "local", displayName: "Local Simulator", capabilities: ["chat", "stream", "tool_calling"], contextWindow: 32000, enabled: true },
      { id: "gpt-5", provider: "openai", displayName: "GPT-5", capabilities: ["chat", "stream", "tool_calling"], contextWindow: 275000, enabled: false },
      { id: "deepseek-reasoner", provider: "deepseek", displayName: "DeepSeek Reasoner", capabilities: ["chat", "stream"], contextWindow: 64000, enabled: false },
    ],
    conversations: [
      {
        conversationId: "conv_1",
        project: "demo",
        provider: "local",
        model: "local/simulator-v1",
        title: "debug auth 500",
        agent: "ASSISTANT",
        status: "active",
        createdAt: "2026-08-19T00:00:00Z",
        updatedAt: "2026-08-19T01:00:00Z",
        readOnly: true,
      },
    ],
    toolProposals: [
      {
        proposalId: "tool_1",
        conversationId: "conv_1",
        project: "demo",
        messageId: "msg_1",
        toolName: "read_file",
        arguments: '{"path":"src/auth/service.py"}',
        reason: "model wants to inspect the auth service",
        status: "recorded",
        approvalRequestId: "req_1",
        createdAt: "2026-08-19T00:30:00Z",
        executed: false,
        readOnly: true,
      },
    ],
    readOnly: true,
    ...overrides,
  };
}

function render(snapshot: LlmGatewaySnapshot | null) {
  return renderLlmGatewayDashboard(document, snapshot);
}

describe("Phase 31 dashboard shell", () => {
  it("renders the heading", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("LLM Gateway");
  });

  it("renders the READ ONLY badge", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("READ ONLY");
  });

  it("renders the empty state without a snapshot", () => {
    const root = render(null);
    expect(root.textContent).toContain("No LLM gateway data loaded");
  });

  it("renders all sections", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Provider Registry");
    expect(root.textContent).toContain("Model Registry");
    expect(root.textContent).toContain("Conversations");
    expect(root.textContent).toContain("Tool-Call Proposals");
  });

  it("has no interactive execute/approve/apply controls", () => {
    const root = render(snapshotFixture());
    expect(root.querySelectorAll("button").length).toBe(0);
    expect(root.querySelectorAll('input[type="submit"]').length).toBe(0);
    expect(root.textContent).toContain("No execute, approve, apply, fix, auto-learn or auto-govern");
  });
});

describe("Phase 31 provider registry rendering", () => {
  it("renders every registered provider", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("local");
    expect(root.textContent).toContain("openai");
    expect(root.textContent).toContain("anthropic");
    expect(root.textContent).toContain("deepseek");
  });

  it("marks the local provider as configured", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("local — configured");
  });

  it("marks unconfigured vendor providers", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("openai — not configured");
    expect(root.textContent).toContain("anthropic — not configured");
    expect(root.textContent).toContain("deepseek — not configured");
  });

  it("explains that vendor providers need env keys", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("API key");
  });

  it("renders empty providers list", () => {
    const root = render(snapshotFixture({ providers: [] }));
    expect(root.textContent).toContain("No providers registered.");
  });
});

describe("Phase 31 model registry rendering", () => {
  it("renders enabled model ids", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("local/simulator-v1");
  });

  it("renders model capabilities", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("chat, stream, tool_calling");
  });

  it("does not list disabled vendor models as usable", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).not.toContain("gpt-5 — openai");
    expect(root.textContent).not.toContain("deepseek-reasoner — deepseek");
  });

  it("counts disabled vendor models", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("2 vendor model(s) disabled");
  });

  it("caps the enabled model list at ten", () => {
    const models = Array.from({ length: 12 }, (_, index) => ({
      id: `local/model-${index}`,
      provider: "local",
      displayName: `Model ${index}`,
      capabilities: ["chat"],
      contextWindow: 1000,
      enabled: true,
    }));
    const root = render(snapshotFixture({ models }));
    const matches = root.textContent!.match(/local\/model-\d+ — local/g) ?? [];
    expect(matches.length).toBe(10);
    expect(root.textContent).toContain("+2 more enabled model(s)");
  });

  it("renders empty models list", () => {
    const root = render(snapshotFixture({ models: [] }));
    expect(root.textContent).toContain("No models in the registry.");
  });
});

describe("Phase 31 conversations rendering", () => {
  it("renders conversation titles", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("debug auth 500");
  });

  it("renders provider/model binding", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("local/local/simulator-v1");
  });

  it("renders the agent binding", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("agent=ASSISTANT");
  });

  it("notes that persistence is approval-gated", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("approval-gated");
  });

  it("renders empty conversations state", () => {
    const root = render(snapshotFixture({ conversations: [] }));
    expect(root.textContent).toContain("No persisted conversations for this project yet.");
  });

  it("caps conversations at six", () => {
    const conversations = Array.from({ length: 8 }, (_, index) => ({
      ...snapshotFixture().conversations[0],
      conversationId: `conv_${index}`,
      title: `conversation ${index}`,
    }));
    const root = render(snapshotFixture({ conversations }));
    const matches = root.textContent!.match(/conversation \d — /g) ?? [];
    expect(matches.length).toBe(6);
  });
});

describe("Phase 31 tool proposals rendering", () => {
  it("renders tool names and status", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("read_file");
    expect(root.textContent).toContain("recorded");
  });

  it("renders proposal reasons", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("inspect the auth service");
  });

  it("emphasises record-only boundary", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("never executed by the gateway");
  });

  it("renders empty proposals state", () => {
    const root = render(snapshotFixture({ toolProposals: [] }));
    expect(root.textContent).toContain("No recorded tool-call proposals for this project.");
  });

  it("caps proposals at six", () => {
    const proposals = Array.from({ length: 8 }, (_, index) => ({
      ...snapshotFixture().toolProposals[0],
      proposalId: `tool_${index}`,
      reason: `reason ${index}`,
    }));
    const root = render(snapshotFixture({ toolProposals: proposals }));
    const matches = root.textContent!.match(/reason \d/g) ?? [];
    expect(matches.length).toBe(6);
  });
});

describe("Phase 31 snapshot data integrity", () => {
  it("flags read-only at the snapshot level", () => {
    expect(snapshotFixture().readOnly).toBe(true);
  });

  it("never marks a tool proposal executed", () => {
    for (const proposal of snapshotFixture().toolProposals) {
      expect(proposal.executed).toBe(false);
    }
  });

  it("keeps key env names but never their values", () => {
    const serialized = JSON.stringify(snapshotFixture());
    expect(serialized).toContain("OPENAI_API_KEY");
    expect(serialized).not.toContain("sk-");
    expect(serialized).not.toContain("Bearer ");
  });

  it("provider info exposes model counts", () => {
    const local = snapshotFixture().providers.find((provider) => provider.name === "local");
    expect(local?.models.length).toBe(2);
  });

  it("models carry context windows", () => {
    for (const model of snapshotFixture().models) {
      expect(model.contextWindow).toBeGreaterThan(0);
    }
  });
});

describe("Phase 31 store state", () => {
  it("initialises llm gateway state empty", () => {
    const state = createInitialState();
    expect(state.llmProviders).toEqual([]);
    expect(state.llmModels).toEqual([]);
    expect(state.llmConversations).toEqual([]);
    expect(state.llmToolProposals).toEqual([]);
  });

  it("updates llm providers", async () => {
    const store = new ExtensionStore();
    await store.update({ llmProviders: snapshotFixture().providers });
    expect(store.getState().llmProviders.length).toBe(4);
  });

  it("updates llm models", async () => {
    const store = new ExtensionStore();
    await store.update({ llmModels: snapshotFixture().models });
    expect(store.getState().llmModels[0].id).toBe("local/simulator-v1");
  });

  it("updates llm conversations", async () => {
    const store = new ExtensionStore();
    await store.update({ llmConversations: snapshotFixture().conversations });
    expect(store.getState().llmConversations[0].conversationId).toBe("conv_1");
  });

  it("updates llm tool proposals", async () => {
    const store = new ExtensionStore();
    await store.update({ llmToolProposals: snapshotFixture().toolProposals });
    expect(store.getState().llmToolProposals[0].toolName).toBe("read_file");
  });

  it("resets llm gateway state via update", async () => {
    const store = new ExtensionStore();
    await store.update({ llmProviders: snapshotFixture().providers });
    await store.update({ llmProviders: [] });
    expect(store.getState().llmProviders).toEqual([]);
  });

  it("merges without clobbering other state", async () => {
    const store = new ExtensionStore();
    await store.update({ llmConversations: snapshotFixture().conversations });
    expect(store.getState().bridgeStatus).toBe("unknown");
    expect(store.getState().phase30Intelligence).toBeNull();
  });
});

describe("Phase 31 bridge client", () => {
  it("fetches providers", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/llm/providers");
      return response({ providers: snapshotFixture().providers, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmProviders();
    expect(result.providers.length).toBe(4);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches models with optional provider filter", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/llm/models?provider=deepseek");
      return response({ models: [], readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmModels("deepseek");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches models without a filter", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/llm/models");
      expect(String(input)).not.toContain("provider");
      return response({ models: [], readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmModels();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches conversations for a project", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/llm/conversations?project=demo");
      return response({ project: "demo", conversations: snapshotFixture().conversations, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversations("demo");
    expect(result.conversations[0].conversationId).toBe("conv_1");
  });

  it("fetches conversation detail with messages", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/llm/conversations/conv_1?project=demo");
      return response({
        conversation: snapshotFixture().conversations[0],
        messages: [{ messageId: "msg_1", conversationId: "conv_1", role: "user", content: "hi", toolCalls: [], createdAt: "t", approvalRequestId: "", readOnly: true }],
        readOnly: true,
      });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversationDetail("conv_1", "demo");
    expect(result.messages[0].content).toBe("hi");
  });

  it("fetches tool proposals", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/llm/tool-proposals?project=demo");
      return response({ project: "demo", proposals: snapshotFixture().toolProposals, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmToolProposals("demo");
    expect(result.proposals[0].toolName).toBe("read_file");
    expect(result.proposals[0].executed).toBe(false);
  });

  it("posts a stateless chat request", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/llm/chat");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.project).toBe("demo");
      expect(body.messages[0].content).toBe("hello");
      return response({ reply: "[simulated] hi", toolCalls: [], provider: "local", model: "local/simulator-v1", finishReason: "stop", usage: {}, simulated: true, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmChat({ project: "demo", messages: [{ role: "user", content: "hello" }] });
    expect(result.simulated).toBe(true);
    expect(result.toolCalls).toEqual([]);
  });

  it("stages a conversation create via POST", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/llm/conversations");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.project).toBe("demo");
      expect(body.title).toBe("my chat");
      return response({ requestId: "req_1", status: "pending", preview: "CREATE conversation" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversationCreate({ project: "demo", title: "my chat" });
    expect(result.requestId).toBe("req_1");
  });

  it("stages a conversation message via POST", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/llm/conversations/conv_1/messages");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.content).toBe("remember this");
      return response({ requestId: "req_2", status: "pending", preview: "APPEND message" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversationMessage({ project: "demo", content: "remember this" }, "conv_1");
    expect(result.requestId).toBe("req_2");
  });

  it("stages a tool proposal via POST", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/llm/conversations/conv_1/tool-proposal");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.tool_name).toBe("read_file");
      expect(body.project).toBe("demo");
      return response({ requestId: "req_3", status: "pending", preview: "RECORD tool-call proposal" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmToolProposal({ project: "demo", message_id: "msg_1", tool_name: "read_file", reason: "r" }, "conv_1");
    expect(result.requestId).toBe("req_3");
  });

  it("issues GET requests without a body", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBeUndefined();
      expect(init?.body).toBeUndefined();
      return response({ providers: [], readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmProviders();
  });
});

describe("Phase 31 client error handling", () => {
  async function expectStatus(call: Promise<unknown>, status: number): Promise<void> {
    try {
      await call;
    } catch (error) {
      expect((error as { status: number }).status).toBe(status);
      return;
    }
    throw new Error("expected BridgeRequestError");
  }

  it("rejects providers on 500", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "boom" }), { status: 500 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmProviders(), 500);
  });

  it("rejects models on 403", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "forbidden" }), { status: 403 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmModels(), 403);
  });

  it("rejects conversations on 404", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "not_found" }), { status: 404 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmConversations("demo"), 404);
  });

  it("rejects tool proposals on 500", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "boom" }), { status: 500 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmToolProposals("demo"), 500);
  });

  it("rejects chat on 422", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ detail: "bad project" }), { status: 422 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmChat({ project: "bad", messages: [{ role: "user", content: "x" }] }), 422);
  });

  it("rejects conversation create on 400", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "bad_request" }), { status: 400 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmConversationCreate({ project: "demo", title: "t" }), 400);
  });

  it("rejects message append on 404", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "missing" }), { status: 404 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmConversationMessage({ project: "demo", content: "x" }, "conv_1"), 404);
  });

  it("rejects tool proposal on 422", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ detail: "invalid" }), { status: 422 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.llmToolProposal({ project: "demo", message_id: "m", tool_name: "x", reason: "r" }, "conv_1"), 422);
  });
});

describe("Phase 31 chat payload handling", () => {
  it("returns tool calls from a chat response", async () => {
    const fetchImpl = vi.fn(async () =>
      response({
        reply: "proposing a tool",
        toolCalls: [{ name: "read_file", arguments: '{"path":"a.py"}', callId: "tool_1" }],
        provider: "local",
        model: "local/simulator-v1",
        finishReason: "tool_calls",
        usage: { prompt_tokens: 1, completion_tokens: 1 },
        simulated: true,
        readOnly: true,
      }),
    );
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmChat({ project: "demo", messages: [{ role: "user", content: "use a tool" }] });
    expect(result.toolCalls.length).toBe(1);
    expect(result.toolCalls[0].name).toBe("read_file");
    expect(result.finishReason).toBe("tool_calls");
  });

  it("passes model and provider to chat", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.model).toBe("gpt-4o");
      expect(body.provider).toBe("openai");
      return response({ reply: "x", toolCalls: [], provider: "openai", model: "gpt-4o", finishReason: "stop", usage: {}, simulated: false, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmChat({ project: "demo", messages: [{ role: "user", content: "x" }], model: "gpt-4o", provider: "openai" });
    expect(result.provider).toBe("openai");
  });

  it("passes agent binding to chat", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.agent).toBe("ASSISTANT");
      return response({ reply: "x", toolCalls: [], provider: "local", model: "local/simulator-v1", finishReason: "stop", usage: {}, simulated: true, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmChat({ project: "demo", messages: [{ role: "user", content: "x" }], agent: "ASSISTANT" });
  });

  it("passes temperature and max tokens to chat", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.temperature).toBe(0.7);
      expect(body.max_tokens).toBe(512);
      return response({ reply: "x", toolCalls: [], provider: "local", model: "local/simulator-v1", finishReason: "stop", usage: {}, simulated: true, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmChat({ project: "demo", messages: [{ role: "user", content: "x" }], temperature: 0.7, max_tokens: 512 });
  });

  it("preserves system and tool roles in the message list", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.messages.map((item: { role: string }) => item.role)).toEqual(["system", "user", "assistant", "tool"]);
      return response({ reply: "x", toolCalls: [], provider: "local", model: "local/simulator-v1", finishReason: "stop", usage: {}, simulated: true, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmChat({
      project: "demo",
      messages: [
        { role: "system", content: "s" },
        { role: "user", content: "u" },
        { role: "assistant", content: "a" },
        { role: "tool", content: "t" },
      ],
    });
  });
});

describe("Phase 31 approval payload handling", () => {
  it("passes provider and model on conversation create", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.provider).toBe("local");
      expect(body.model).toBe("local/simulator-v1");
      expect(body.agent).toBe("CODER");
      return response({ requestId: "req_1", status: "pending", preview: "CREATE" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmConversationCreate({ project: "demo", provider: "local", model: "local/simulator-v1", title: "t", agent: "CODER" });
  });

  it("passes agent and model on message append", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.agent).toBe("ASSISTANT");
      expect(body.model).toBe("local/simulator-v1");
      return response({ requestId: "req_2", status: "pending", preview: "APPEND" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmConversationMessage(
      { project: "demo", content: "x", agent: "ASSISTANT", model: "local/simulator-v1" },
      "conv_1",
    );
  });

  it("passes tool arguments on tool proposal", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.tool_name).toBe("shell_command");
      expect(body.arguments).toBe('{"cmd":"ls"}');
      return response({ requestId: "req_3", status: "pending", preview: "RECORD" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.llmToolProposal(
      { project: "demo", message_id: "m1", tool_name: "shell_command", arguments: '{"cmd":"ls"}', reason: "r" },
      "conv_1",
    );
  });
});

describe("Phase 31 dashboard edge cases", () => {
  it("omits the agent suffix when no agent is bound", () => {
    const conversation = { ...snapshotFixture().conversations[0], agent: "" };
    const root = render(snapshotFixture({ conversations: [conversation] }));
    expect(root.textContent).toContain("debug auth 500");
    expect(root.textContent).not.toContain("agent=");
  });

  it("truncates long conversation titles", () => {
    const longTitle = "x".repeat(200);
    const conversation = { ...snapshotFixture().conversations[0], title: longTitle };
    const root = render(snapshotFixture({ conversations: [conversation] }));
    expect(root.textContent).toContain(longTitle.slice(0, 80));
    expect(root.textContent).not.toContain(longTitle.slice(80));
  });

  it("truncates long proposal reasons", () => {
    const longReason = "y".repeat(200);
    const proposal = { ...snapshotFixture().toolProposals[0], reason: longReason };
    const root = render(snapshotFixture({ toolProposals: [proposal] }));
    expect(root.textContent).toContain(longReason.slice(0, 80));
    expect(root.textContent).not.toContain(longReason.slice(80));
  });

  it("renders the record-only line even with proposals", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Recorded proposals only");
  });

  it("renders the approval-gated note even with conversations", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Conversation persistence is approval-gated");
  });

  it("renders enabled and disabled model counts together", () => {
    const models = [
      { id: "local/a", provider: "local", displayName: "A", capabilities: ["chat"], contextWindow: 1, enabled: true },
      { id: "openai/gpt-5", provider: "openai", displayName: "GPT-5", capabilities: ["chat"], contextWindow: 1, enabled: false },
    ];
    const root = render(snapshotFixture({ models }));
    expect(root.textContent).toContain("local/a — local");
    expect(root.textContent).toContain("1 vendor model(s) disabled");
  });

  it("renders multiple enabled models up to ten", () => {
    const models = Array.from({ length: 11 }, (_, index) => ({
      id: `local/m-${index}`,
      provider: "local",
      displayName: `M${index}`,
      capabilities: ["chat"],
      contextWindow: 1000,
      enabled: true,
    }));
    const root = render(snapshotFixture({ models }));
    const matches = root.textContent!.match(/local\/m-\d+ — local/g) ?? [];
    expect(matches.length).toBe(10);
    expect(root.textContent).toContain("+1 more enabled model(s)");
  });

  it("renders multiple providers with per-provider model counts", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("local — configured · 2 model(s)");
    expect(root.textContent).toContain("openai — not configured · 2 model(s)");
  });
});

describe("Phase 31 snapshot data integrity (extended)", () => {
  it("conversations carry timestamps", () => {
    const conversation = snapshotFixture().conversations[0];
    expect(conversation.createdAt).toBeTruthy();
    expect(conversation.updatedAt).toBeTruthy();
  });

  it("conversations are read-only records", () => {
    expect(snapshotFixture().conversations[0].readOnly).toBe(true);
  });

  it("proposals carry approval request ids", () => {
    expect(snapshotFixture().toolProposals[0].approvalRequestId).toBe("req_1");
  });

  it("proposals carry opaque arguments", () => {
    expect(snapshotFixture().toolProposals[0].arguments).toContain("auth/service.py");
  });

  it("proposals are read-only records", () => {
    expect(snapshotFixture().toolProposals[0].readOnly).toBe(true);
  });

  it("models carry display names", () => {
    expect(snapshotFixture().models[0].displayName).toBe("Local Simulator");
  });

  it("model entries reference their provider", () => {
    for (const model of snapshotFixture().models) {
      expect(model.provider).toBeTruthy();
    }
  });

  it("provider key env entries are names only", () => {
    for (const provider of snapshotFixture().providers) {
      expect(provider.keyEnv).not.toContain("sk-");
      expect(provider.keyEnv).not.toContain("=");
    }
  });

  it("model ids are unique across the catalogue", () => {
    const ids = snapshotFixture().models.map((model) => model.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const model of snapshotFixture().models) {
      expect(model.id).toBeTruthy();
      expect(model.provider).toBeTruthy();
    }
  });
});

describe("Phase 31 store extended", () => {
  it("updates all four gateway fields together", async () => {
    const store = new ExtensionStore();
    const snapshot = snapshotFixture();
    await store.update({
      llmProviders: snapshot.providers,
      llmModels: snapshot.models,
      llmConversations: snapshot.conversations,
      llmToolProposals: snapshot.toolProposals,
    });
    const state = store.getState();
    expect(state.llmProviders.length).toBe(4);
    expect(state.llmModels.length).toBe(3);
    expect(state.llmConversations.length).toBe(1);
    expect(state.llmToolProposals.length).toBe(1);
  });

  it("resets each gateway field individually", async () => {
    const store = new ExtensionStore();
    const snapshot = snapshotFixture();
    await store.update({ llmModels: snapshot.models, llmToolProposals: snapshot.toolProposals });
    await store.update({ llmModels: [], llmToolProposals: [] });
    expect(store.getState().llmModels).toEqual([]);
    expect(store.getState().llmToolProposals).toEqual([]);
  });

  it("keeps gateway data after unrelated updates", async () => {
    const store = new ExtensionStore();
    await store.update({ llmProviders: snapshotFixture().providers });
    await store.update({ lastResult: "refreshed" });
    expect(store.getState().llmProviders.length).toBe(4);
  });

  it("persists conversation records for rendering", async () => {
    const store = new ExtensionStore();
    await store.update({ llmConversations: snapshotFixture().conversations });
    expect(store.getState().llmConversations[0].conversationId).toBe("conv_1");
  });
});

describe("Phase 31 conversation detail data", () => {
  it("conversation detail messages carry roles and content", async () => {
    const fetchImpl = vi.fn(async () =>
      response({
        conversation: snapshotFixture().conversations[0],
        messages: [
          { messageId: "m1", conversationId: "conv_1", role: "user", content: "hello", toolCalls: [], createdAt: "t1", approvalRequestId: "", readOnly: true },
          { messageId: "m2", conversationId: "conv_1", role: "assistant", content: "hi", toolCalls: [], createdAt: "t2", approvalRequestId: "", readOnly: true },
        ],
        readOnly: true,
      }),
    );
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversationDetail("conv_1", "demo");
    expect(result.messages.map((item) => item.role)).toEqual(["user", "assistant"]);
    expect(result.messages.map((item) => item.content)).toEqual(["hello", "hi"]);
  });

  it("conversation detail messages carry tool calls", async () => {
    const fetchImpl = vi.fn(async () =>
      response({
        conversation: snapshotFixture().conversations[0],
        messages: [
          { messageId: "m1", conversationId: "conv_1", role: "assistant", content: "", toolCalls: [{ name: "search", arguments: "{}", callId: "c1" }], createdAt: "t", approvalRequestId: "", readOnly: true },
        ],
        readOnly: true,
      }),
    );
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversationDetail("conv_1", "demo");
    expect(result.messages[0].toolCalls[0].name).toBe("search");
  });

  it("messages are read-only records", async () => {
    const fetchImpl = vi.fn(async () =>
      response({
        conversation: snapshotFixture().conversations[0],
        messages: [{ messageId: "m1", conversationId: "conv_1", role: "user", content: "x", toolCalls: [], createdAt: "t", approvalRequestId: "", readOnly: true }],
        readOnly: true,
      }),
    );
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversationDetail("conv_1", "demo");
    expect(result.messages[0].readOnly).toBe(true);
    expect(result.readOnly).toBe(true);
  });

  it("message approval ids surface on persisted records", async () => {
    const fetchImpl = vi.fn(async () =>
      response({
        conversation: snapshotFixture().conversations[0],
        messages: [{ messageId: "m1", conversationId: "conv_1", role: "user", content: "x", toolCalls: [], createdAt: "t", approvalRequestId: "req_9", readOnly: true }],
        readOnly: true,
      }),
    );
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmConversationDetail("conv_1", "demo");
    expect(result.messages[0].approvalRequestId).toBe("req_9");
  });
});

describe("Phase 31 conversation status data", () => {
  it("conversations carry a status", () => {
    expect(snapshotFixture().conversations[0].status).toBe("active");
  });

  it("provider entries list their model ids", () => {
    const openai = snapshotFixture().providers.find((provider) => provider.name === "openai");
    expect(openai?.models).toContain("gpt-5");
  });

  it("the local provider is always enabled in fixtures", () => {
    const local = snapshotFixture().providers.find((provider) => provider.name === "local");
    expect(local?.enabled).toBe(true);
  });

  it("vendor providers start disabled in fixtures", () => {
    for (const name of ["openai", "anthropic", "deepseek"]) {
      const provider = snapshotFixture().providers.find((item) => item.name === name);
      expect(provider?.enabled).toBe(false);
    }
  });

  it("chat usage metadata is carried through", async () => {
    const fetchImpl = vi.fn(async () =>
      response({
        reply: "x",
        toolCalls: [],
        provider: "local",
        model: "local/simulator-v1",
        finishReason: "stop",
        usage: { prompt_tokens: 10, completion_tokens: 5 },
        simulated: true,
        readOnly: true,
      }),
    );
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.llmChat({ project: "demo", messages: [{ role: "user", content: "x" }] });
    expect(result.usage.prompt_tokens).toBe(10);
    expect(result.usage.completion_tokens).toBe(5);
  });
});

describe("Phase 31 empty snapshot rendering", () => {
  it("renders every section no-data state", () => {
    const root = render(snapshotFixture({ providers: [], models: [], conversations: [], toolProposals: [] }));
    expect(root.textContent).toContain("No providers registered.");
    expect(root.textContent).toContain("No models in the registry.");
    expect(root.textContent).toContain("No persisted conversations for this project yet.");
    expect(root.textContent).toContain("No recorded tool-call proposals for this project.");
  });

  it("still renders the footer boundary note", () => {
    const root = render(snapshotFixture({ providers: [], models: [], conversations: [], toolProposals: [] }));
    expect(root.textContent).toContain("No execute, approve, apply");
  });

  it("a null snapshot skips all sections", () => {
    const root = render(null);
    expect(root.querySelectorAll(".llm-block").length).toBe(0);
    expect(root.textContent).toContain("No LLM gateway data loaded");
  });

  it("a full snapshot renders four sections", () => {
    const root = render(snapshotFixture());
    expect(root.querySelectorAll(".llm-block").length).toBe(4);
  });
});
