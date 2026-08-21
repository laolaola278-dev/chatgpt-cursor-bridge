/**
 * Phase 32 · AI Assistant productization — extension tests (spec §19/§20).
 *
 * Covers the User/Developer mode surfaces, the Provider Settings page, API-key
 * containment, chat + streaming, extension-only history, Ask AI consent, safe
 * Markdown, inert tool proposals and the read-only developer context.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderAssistantChat, renderChatTurn, renderToolProposal } from "../src/assistant/chat-view";
import type { AssistantChatViewState } from "../src/assistant/chat-view";
import { renderDeveloperContext } from "../src/assistant/dev-context-view";
import { renderMarkdown } from "../src/assistant/markdown";
import {
  renderModelSelector,
  renderModeToggle,
  renderProviderSettings,
  statusLabel,
} from "../src/assistant/settings-view";
import type { AssistantSettingsViewState } from "../src/assistant/settings-view";
import {
  ASK_AI_TRIGGER,
  collectWebContext,
  renderAskAiButton,
  renderWebContextPreview,
} from "../src/assistant/web-context";
import type {
  AssistantChatTurn,
  AssistantContextStatus,
  AssistantConversationView,
  AssistantProviderEntry,
  AssistantStreamEvent,
  AssistantToolCall,
  AssistantUserSettings,
  WebContextBundle,
} from "../src/assistant/types";
import { BridgeClient } from "../src/bridge/client";
import { Controller } from "../src/content/controller";
import type { PendingAction } from "../src/models/action";
import {
  createInitialState,
  ExtensionStore,
  isForbiddenStateKey,
  STORAGE_KEY,
  stripForbiddenKeys,
  TRANSIENT_STATE_KEYS,
} from "../src/state/store";
import type { ExtensionState } from "../src/state/store";
import { Panel } from "../src/ui/panel";
import type { PanelHandlers } from "../src/ui/panel";

vi.mock("../src/ui/styles.css?inline", () => ({ default: ".panel{}" }));

function source(relative: string): string {
  return readFileSync(resolve(__dirname, "../src", relative), "utf8");
}

/** Source with comments stripped, so a docstring cannot satisfy a scan. */
function code(relative: string): string {
  return source(relative)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|\s)\/\/.*$/gm, "");
}

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

/** A fake SSE response: deterministic chunks, split where the test wants. */
function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () =>
          index < chunks.length
            ? { done: false, value: encoder.encode(chunks[index++]) }
            : { done: true, value: undefined },
      }),
    },
    text: async () => chunks.join(""),
  } as unknown as Response;
}

function frame(event: Partial<AssistantStreamEvent>): string {
  const payload: AssistantStreamEvent = {
    type: "token",
    content: "",
    toolCall: null,
    provider: "openai",
    model: "gpt-5",
    ...event,
  };
  return `data: ${JSON.stringify(payload)}\n\n`;
}

function providerEntry(overrides: Partial<AssistantProviderEntry> = {}): AssistantProviderEntry {
  return {
    provider: "openai",
    displayName: "OpenAI",
    status: "connected",
    requiresApiKey: true,
    keyEnv: "OPENAI_API_KEY",
    hasStoredKey: true,
    keyHint: "****cdef",
    keyFingerprint: "fp_openai",
    baseUrl: "https://api.openai.com/v1",
    selectedModel: "gpt-5",
    lastTestedAt: "2026-01-01T00:00:00Z",
    models: ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"],
    ...overrides,
  };
}

const DEEPSEEK = providerEntry({
  provider: "deepseek",
  displayName: "DeepSeek",
  status: "not_configured",
  hasStoredKey: false,
  keyHint: "",
  keyEnv: "DEEPSEEK_API_KEY",
  baseUrl: "",
  selectedModel: "deepseek-chat",
  models: ["deepseek-chat", "deepseek-reasoner"],
});

function userSettings(): AssistantUserSettings {
  return {
    mode: "user",
    provider: "openai",
    model: "gpt-5",
    baseUrl: "",
    preferences: { theme: "dark" },
    surfaces: ["chat", "model_selector", "context", "history", "settings"],
    neverAvailable: ["execute", "apply_patch", "auto_approve", "shell"],
    providers: [{ provider: "openai", status: "connected", hasStoredKey: true, models: ["gpt-5"] }],
    keyStorage: { algorithm: "AES-256-GCM", available: true, location: "bridge key store" },
    readOnly: true,
  };
}

function contextStatus(): AssistantContextStatus {
  return {
    scope: "developer",
    web: {
      requiresExplicitTrigger: true,
      trigger: "ask_ai",
      automaticCapture: false,
      automaticUpload: false,
      fields: ["page_title", "page_url", "selected_text", "readable_content", "timestamp"],
    },
    developerContext: {
      loaded: true,
      readOnly: true,
      project: "demo",
      sources: ["workflow", "tests", "git"],
      endpoint: "/context/dev",
      modificationRequiresApproval: true,
    },
    readOnly: true,
  };
}

function settingsState(
  overrides: Partial<AssistantSettingsViewState> = {},
): AssistantSettingsViewState {
  return {
    uiMode: "user",
    provider: "openai",
    model: "gpt-5",
    providers: [providerEntry(), DEEPSEEK],
    settings: userSettings(),
    test: null,
    ...overrides,
  };
}

function chatState(overrides: Partial<AssistantChatViewState> = {}): AssistantChatViewState {
  return {
    uiMode: "user",
    conversations: [],
    activeConversation: null,
    streaming: false,
    status: "",
    ...overrides,
  };
}

function toolCall(): AssistantToolCall {
  return { name: "file_write", arguments: '{"path":"src/a.ts"}', callId: "call_1" };
}

function turn(overrides: Partial<AssistantChatTurn> = {}): AssistantChatTurn {
  return {
    id: "turn_1",
    role: "assistant",
    content: "Hello",
    createdAt: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}

function conversation(turns: AssistantChatTurn[]): AssistantConversationView {
  return {
    id: "local_1",
    title: "Chat",
    createdAt: "2026-01-01T00:00:00.000Z",
    turns,
    localOnly: true,
  };
}

function pendingItem(): PendingAction {
  return {
    id: "act_1",
    state: "pending",
    createdAt: "2026-01-01T00:00:00.000Z",
    fingerprint: "fp_1",
    action: {
      version: "1.0",
      action: "file.write",
      target: { project: "demo", path: "src/main.cpp" },
      reason: "Fix memory leak",
      risk: "medium",
      payload: { content: "int main(){}\n" },
      requiresApproval: true,
    },
  };
}

function bundle(url = "https://example.com/docs?token=secret#top"): WebContextBundle {
  return collectWebContext(document, { timestamp: "2026-01-01T00:00:00.000Z", url });
}

function mountPanel(
  patch: Partial<ExtensionState> = {},
  handlers: Partial<PanelHandlers> = {},
): HTMLElement {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const panel = new Panel(document, container, {
    onConnect: () => {},
    onSelectProject: () => {},
    onApprove: () => {},
    onReject: () => {},
    ...handlers,
  });
  panel.setProjects(["demo"]);
  panel.render({ ...createInitialState(), ...patch });
  return container;
}

/** Capabilities no surface may ever offer (spec §15/§20). */
const FORBIDDEN_CONTROL = /execute|approve|apply|auto ?fix|auto ?patch|\brun\b|terminal|shell/i;

function buttonLabels(root: ParentNode): string[] {
  return Array.from(root.querySelectorAll("button")).map(
    (button) => `${button.textContent ?? ""} ${button.dataset.role ?? ""}`,
  );
}

function memoryStorage(seed: Record<string, unknown> = {}) {
  const data = new Map<string, unknown>(Object.entries(seed));
  return {
    data,
    async get(key: string) {
      return data.has(key) ? { [key]: data.get(key) } : {};
    },
    async set(items: Record<string, unknown>) {
      for (const [key, value] of Object.entries(items)) data.set(key, value);
    },
  };
}

/**
 * A Bridge client that records every endpoint the controller touches. Any
 * method that is not stubbed rejects, so an unexpected call fails the test
 * instead of silently loading developer data.
 */
function fakeClient(overrides: Record<string, unknown> = {}) {
  const touched: string[] = [];
  const base: Record<string, unknown> = {
    userSettings: vi.fn(async () => userSettings()),
    providerStatus: vi.fn(async () => ({ providers: [providerEntry()], readOnly: true as const })),
    contextStatus: vi.fn(async () => contextStatus()),
    ...overrides,
  };
  const proxy = new Proxy(base, {
    get(target, property) {
      if (typeof property !== "string") return undefined;
      touched.push(property);
      if (property in target) return target[property];
      return async () => {
        throw new Error(`unexpected Bridge call: ${property}`);
      };
    },
  });
  return { client: proxy as unknown as BridgeClient, touched };
}

function controllerFor(overrides: Record<string, unknown> = {}) {
  const store = new ExtensionStore(memoryStorage());
  const fake = fakeClient(overrides);
  const controller = new Controller({ store, client: fake.client, render: () => {} });
  return { store, controller, touched: fake.touched };
}

describe("phase 32 · user mode / developer mode", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("defaults to User Mode", () => {
    expect(createInitialState().uiMode).toBe("user");
  });

  it("offers a mode toggle that switches between the two read-only modes", () => {
    const onSetMode = vi.fn();
    const user = renderModeToggle(document, "user", { onSetMode });
    expect(user.dataset.mode).toBe("user");
    expect(user.textContent).toContain("Switch to Developer Mode");
    user.querySelector<HTMLButtonElement>("[data-role='toggle-mode']")!.click();
    expect(onSetMode).toHaveBeenCalledWith("developer");

    const developer = renderModeToggle(document, "developer", { onSetMode });
    expect(developer.dataset.mode).toBe("developer");
    developer.querySelector<HTMLButtonElement>("[data-role='toggle-mode']")!.click();
    expect(onSetMode).toHaveBeenLastCalledWith("user");
    for (const label of buttonLabels(developer)) expect(label).not.toMatch(FORBIDDEN_CONTROL);
  });

  it("renders chat, model selector, context, history and settings in User Mode", () => {
    const container = mountPanel({
      bridgeStatus: "connected",
      currentProject: "demo",
      assistantProviders: [providerEntry(), DEEPSEEK],
      assistantSettings: userSettings(),
      assistantContextStatus: contextStatus(),
      sessions: [{ id: "ses_1", status: "ACTIVE" }],
    });

    const surface = container.querySelector<HTMLElement>("[data-role='assistant-surface']")!;
    expect(surface.dataset.mode).toBe("user");
    for (const role of [
      "assistant-chat",
      "model-selector",
      "web-context",
      "ask-ai",
      "chat-history",
      "chat-input",
      "provider-settings",
    ]) {
      expect(container.querySelector(`[data-role='${role}']`)).not.toBeNull();
    }

    expect(container.querySelector("[data-role='developer-surface']")).toBeNull();
    expect(container.querySelector("[data-role='developer-context']")).toBeNull();
    expect(container.textContent).not.toContain("Sessions:");
  });

  it("hides the engineering surfaces in User Mode", () => {
    const container = mountPanel({
      assistantProviders: [providerEntry()],
      assistantContextStatus: contextStatus(),
      projectContext: null,
    });
    const text = container.textContent ?? "";
    for (const label of [
      "Governance",
      "Intelligence",
      "Engineering Graph",
      "Metrics",
      "Project Context",
      "Code Context",
      "Developer Context",
      "Tool Proposal",
      "Waiting Approval",
    ]) {
      expect(text).not.toContain(label);
    }
  });

  it("offers no execute / approve / apply / auto-fix control in User Mode", () => {
    const container = mountPanel({
      pendingActions: [pendingItem()],
      assistantProviders: [providerEntry()],
      assistantConversations: [conversation([turn({ toolCalls: [toolCall()] })])],
      assistantActiveConversation: "local_1",
    });

    for (const label of buttonLabels(container)) expect(label).not.toMatch(FORBIDDEN_CONTROL);
    expect(container.querySelector("[data-role='approve']")).toBeNull();
    expect(container.querySelector("[data-role='reject']")).toBeNull();
    expect(container.querySelector("[data-role='tool-proposal']")).toBeNull();
    // The queue is not hidden away: User Mode points at it without acting on it.
    expect(container.querySelector("[data-role='approval-hint']")?.textContent).toContain(
      "Switch to Developer Mode",
    );
    expect(container.textContent).toContain("Pending Actions:");
  });

  it("adds the read-only developer surfaces in Developer Mode", () => {
    const container = mountPanel({
      uiMode: "developer",
      bridgeStatus: "connected",
      currentProject: "demo",
      assistantProviders: [providerEntry()],
      assistantContextStatus: contextStatus(),
      pendingActions: [pendingItem()],
      sessions: [{ id: "ses_1", status: "ACTIVE" }],
    });

    expect(container.querySelector("[data-role='assistant-chat']")).not.toBeNull();
    expect(container.querySelector("[data-role='developer-surface']")).not.toBeNull();
    const devContext = container.querySelector<HTMLElement>("[data-role='developer-context']")!;
    expect(devContext.textContent).toContain("READ ONLY");
    expect(container.textContent).toContain("Sessions:");
    // Approving stays a human action on the existing approval card.
    expect(container.querySelector("[data-role='approve']")).not.toBeNull();
    expect(container.querySelector("[data-role='approval-hint']")).toBeNull();
  });

  it("toggles between the two modes", () => {
    const onSetMode = vi.fn();
    const userMode = mountPanel({}, { onSetMode });
    userMode.querySelector<HTMLButtonElement>("[data-role='toggle-mode']")!.click();
    expect(onSetMode).toHaveBeenCalledWith("developer");

    document.body.innerHTML = "";
    const developerMode = mountPanel({ uiMode: "developer" }, { onSetMode });
    const toggle = developerMode.querySelector<HTMLElement>("[data-role='mode-toggle']")!;
    expect(toggle.dataset.mode).toBe("developer");
    toggle.querySelector<HTMLButtonElement>("[data-role='toggle-mode']")!.click();
    expect(onSetMode).toHaveBeenLastCalledWith("user");
  });

  it("keeps the mode as a non-sensitive local preference", async () => {
    const storage = memoryStorage();
    const store = new ExtensionStore(storage);
    await store.hydrate();
    await store.setUiMode("developer");
    const snapshot = storage.data.get(STORAGE_KEY) as Record<string, unknown>;
    expect(snapshot.uiMode).toBe("developer");
    expect(await new ExtensionStore(storage).hydrate()).toMatchObject({ uiMode: "developer" });
  });
});

describe("phase 32 · provider settings", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("lists providers, models and the connection status", () => {
    const root = renderModelSelector(document, settingsState(), {});
    const providers = root.querySelector<HTMLSelectElement>("[data-role='provider-select']")!;
    const models = root.querySelector<HTMLSelectElement>("[data-role='model-select']")!;

    expect(Array.from(providers.options).map((option) => option.value)).toEqual([
      "openai",
      "deepseek",
    ]);
    expect(Array.from(models.options).map((option) => option.value)).toEqual([
      "gpt-5",
      "gpt-5-mini",
      "gpt-4.1",
      "gpt-4o",
    ]);
    expect(root.querySelector("[data-role='provider-status-badge']")?.textContent).toBe("Connected");
  });

  it("emits provider and model selection", () => {
    const onSelectProvider = vi.fn();
    const onSelectModel = vi.fn();
    const root = renderModelSelector(document, settingsState(), { onSelectProvider, onSelectModel });
    document.body.appendChild(root);

    const providers = root.querySelector<HTMLSelectElement>("[data-role='provider-select']")!;
    providers.value = "deepseek";
    providers.dispatchEvent(new Event("change"));
    expect(onSelectProvider).toHaveBeenCalledWith("deepseek");

    const models = root.querySelector<HTMLSelectElement>("[data-role='model-select']")!;
    models.value = "gpt-4o";
    models.dispatchEvent(new Event("change"));
    expect(onSelectModel).toHaveBeenCalledWith("gpt-4o");
  });

  it("maps each provider status to its label", () => {
    expect(statusLabel("connected")).toBe("Connected");
    expect(statusLabel("not_configured")).toBe("Not configured");
    expect(statusLabel("failed")).toBe("Failed");
    expect(statusLabel("something-else")).toBe("Not configured");
  });

  it("renders the settings page fields", () => {
    const root = renderProviderSettings(document, settingsState(), {});
    expect(root.textContent).toContain("Provider Settings");
    expect(root.querySelector("[data-role='settings-provider']")).not.toBeNull();
    expect(root.querySelector("[data-role='settings-model']")).not.toBeNull();
    expect(root.querySelector<HTMLInputElement>("[data-role='base-url-input']")!.value).toBe(
      "https://api.openai.com/v1",
    );
    expect(root.querySelector("[data-role='test-connection']")).not.toBeNull();
    expect(root.querySelector("[data-role='save-provider']")).not.toBeNull();
  });

  it("masks the API key field and clears it after Save", () => {
    const onSaveProvider = vi.fn();
    const root = renderProviderSettings(document, settingsState(), { onSaveProvider });
    const key = root.querySelector<HTMLInputElement>("[data-role='api-key-input']")!;

    expect(key.type).toBe("password");
    expect(key.autocomplete).toBe("off");

    key.value = "sk-live-0123456789abcdef";
    root.querySelector<HTMLButtonElement>("[data-role='save-provider']")!.click();

    expect(onSaveProvider).toHaveBeenCalledWith({
      provider: "openai",
      model: "gpt-5",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "sk-live-0123456789abcdef",
    });
    expect(key.value).toBe("");
  });

  it("clears the API key field after Test Connection too", () => {
    const onTestConnection = vi.fn();
    const root = renderProviderSettings(document, settingsState(), { onTestConnection });
    const key = root.querySelector<HTMLInputElement>("[data-role='api-key-input']")!;
    key.value = "sk-live-0123456789abcdef";

    root.querySelector<HTMLButtonElement>("[data-role='test-connection']")!.click();

    expect(onTestConnection).toHaveBeenCalledWith({
      provider: "openai",
      model: "gpt-5",
      apiKey: "sk-live-0123456789abcdef",
    });
    expect(key.value).toBe("");
    expect(root.textContent).not.toContain("sk-live");
  });

  it("shows a provider test result and the key-storage note", () => {
    const root = renderProviderSettings(
      document,
      settingsState({
        test: { provider: "openai", status: "failed", message: "Invalid API key", readOnly: true },
      }),
      {},
    );
    const result = root.querySelector<HTMLElement>("[data-role='provider-test-result']")!;
    expect(result.dataset.status).toBe("failed");
    expect(result.textContent).toBe("Failed — Invalid API key");
    expect(root.querySelector("[data-role='key-storage-note']")?.textContent).toContain(
      "AES-256-GCM",
    );
  });

  it("shows a masked hint for a stored key and never the key", () => {
    const root = renderProviderSettings(document, settingsState(), {});
    const rows = Array.from(root.querySelectorAll<HTMLElement>("[data-role='provider-row']"));
    expect(rows.map((row) => row.dataset.provider)).toEqual(["openai", "deepseek"]);
    expect(
      Array.from(root.querySelectorAll("[data-role='provider-key-hint']")).map(
        (hint) => hint.textContent,
      ),
    ).toEqual(["****cdef", "no key stored"]);
    expect(
      Array.from(root.querySelectorAll("[data-role='provider-status']")).map(
        (badge) => badge.textContent,
      ),
    ).toEqual(["Connected", "Not configured"]);
  });

});

describe("phase 32 · api key containment", () => {
  const KEY = "sk-live-0123456789abcdef";

  it("hands the key to the Bridge without keeping it in state or storage", async () => {
    const providerConfig = vi.fn(async () => ({ requestId: "req_1", status: "pending" }));
    const store = new ExtensionStore(memoryStorage());
    await store.hydrate();
    const fake = fakeClient({ providerConfig });
    const controller = new Controller({ store, client: fake.client, render: () => {} });

    await controller.saveProvider({
      provider: "openai",
      model: "gpt-5",
      baseUrl: "https://api.openai.com/v1",
      apiKey: KEY,
    });

    // The key travels once, in a POST body, to the endpoint that encrypts it.
    expect(providerConfig).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "openai", api_key: KEY, keep_existing_key: false }),
    );
    const state = store.getState();
    expect(JSON.stringify(state)).not.toContain(KEY);
    expect(state.assistantStatus).toBe("Provider update waiting for approval.");
    expect(state.log.map((entry) => JSON.stringify(entry)).join("")).not.toContain(KEY);
  });

  it("keeps the key out of chrome.storage", async () => {
    const storage = memoryStorage();
    const store = new ExtensionStore(storage);
    await store.hydrate();
    const fake = fakeClient({ providerConfig: vi.fn(async () => ({ requestId: "r", status: "pending" })) });
    const controller = new Controller({ store, client: fake.client, render: () => {} });

    await controller.saveProvider({ provider: "openai", model: "gpt-5", baseUrl: "", apiKey: KEY });
    // Also try to smuggle it in directly.
    await store.update({ apiKey: KEY, providerSecret: KEY } as unknown as Partial<ExtensionState>);

    expect(JSON.stringify(storage.data.get(STORAGE_KEY) ?? {})).not.toContain(KEY);
    expect(JSON.stringify(store.getState())).not.toContain(KEY);
  });

  it("treats every credential-shaped state key as forbidden", () => {
    for (const key of ["apiKey", "api_key", "openaiApiKey", "providerSecret", "authorization", "bearerToken", "credential"]) {
      expect(isForbiddenStateKey(key)).toBe(true);
    }
    expect(isForbiddenStateKey("assistantProvider")).toBe(false);
    expect(stripForbiddenKeys({ apiKey: KEY, assistantModel: "gpt-5" })).toEqual({ assistantModel: "gpt-5" });
  });
  it("never persists the transient assistant fields", async () => {
    const storage = memoryStorage();
    const store = new ExtensionStore(storage);
    await store.hydrate();
    await store.setAssistantWebContext(bundle());
    await store.setAssistantStreaming(true);

    const snapshot = storage.data.get(STORAGE_KEY) as Record<string, unknown>;
    for (const key of TRANSIENT_STATE_KEYS) expect(snapshot).not.toHaveProperty(key);
    // The mode, provider and model are non-sensitive and do persist (spec §18).
    expect(snapshot).toHaveProperty("uiMode");
    expect(snapshot).toHaveProperty("assistantProvider");
    expect(snapshot).toHaveProperty("assistantModel");
  });

  it("posts the key in a request body, never in a URL or query parameter", async () => {
    const calls: Array<{ url: string; init: RequestInit }> = [];
    const fetchImpl = vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      return response({ provider: "openai", status: "connected", message: "Connected", readOnly: true });
    });
    const client = new BridgeClient({
      origin: "http://127.0.0.1:8765",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    await client.providerTest({ provider: "openai", model: "gpt-5", api_key: KEY });
    await client.providerConfig({ provider: "openai", api_key: KEY, reason: "test" });

    for (const call of calls) {
      expect(call.url).not.toContain(KEY);
      expect(call.url).not.toMatch(/[?&]/);
      expect(call.init.method).toBe("POST");
    }
    expect(String(calls[0].init.body)).toContain(KEY);
  });

  it("never reads a key back from the Bridge", () => {
    const settings = userSettings();
    for (const forbidden of ["api_key", "apiKey", "encrypted_api_key", "authorization", "secret"]) {
      expect(Object.keys(settings)).not.toContain(forbidden);
      expect(Object.keys(providerEntry())).not.toContain(forbidden);
    }
    // Only a masked tail and a fingerprint ever cross the boundary.
    expect(providerEntry().keyHint).toBe("****cdef");
    expect(code("assistant/types.ts")).not.toMatch(/\bapi_?key\s*[?]?\s*:/i);
  });

  it("does not log or export the key from the settings view", () => {
    const settingsSource = code("assistant/settings-view.ts");
    expect(settingsSource).not.toMatch(/console\.(log|info|warn|error|debug)/);
    expect(settingsSource).not.toMatch(/chrome\.storage/);
    expect(settingsSource).not.toMatch(/localStorage|sessionStorage/);
    // The input is cleared on both submit paths.
    expect(settingsSource.match(/apiKey\.value\s*=\s*""/g)?.length).toBe(2);
  });
});

describe("phase 32 · chat UX", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows an empty transcript before the first message", () => {
    const root = renderAssistantChat(document, chatState(), { onSend: () => {} });
    expect(root.querySelector("[data-role='chat-transcript']")?.textContent).toContain("never executes");
    expect(root.querySelector("[data-role='chat-history']")?.textContent).toContain("No conversations");
    expect(root.querySelector("[data-role='chat-loading']")).toBeNull();
    expect(root.querySelector("[data-role='chat-stop']")).toBeNull();
  });

  it("renders user and assistant messages", () => {
    const root = renderAssistantChat(
      document,
      chatState({
        conversations: [
          conversation([
            turn({ id: "t_u", role: "user", content: "Why does the build fail?" }),
            turn({ id: "t_a", role: "assistant", content: "Because `tsc` cannot find the module." }),
          ]),
        ],
        activeConversation: "local_1",
      }),
      { onSend: () => {} },
    );

    const messages = Array.from(root.querySelectorAll<HTMLElement>("[data-role='chat-message']"));
    expect(messages.map((item) => item.dataset.messageRole)).toEqual(["user", "assistant"]);
    expect(messages[0].textContent).toContain("You");
    expect(messages[0].textContent).toContain("Why does the build fail?");
    expect(messages[1].textContent).toContain("Assistant");
    // The assistant reply goes through the Markdown renderer.
    expect(messages[1].querySelector("code.assistant-inline-code")?.textContent).toBe("tsc");
  });

  it("sends the trimmed composer value and clears the input", () => {
    const onSend = vi.fn();
    const root = renderAssistantChat(document, chatState(), { onSend });
    document.body.appendChild(root);
    const input = root.querySelector<HTMLTextAreaElement>("[data-role='chat-input']")!;
    const send = root.querySelector<HTMLButtonElement>("[data-role='chat-send']")!;

    send.click();
    expect(onSend).not.toHaveBeenCalled();

    input.value = "  explain this diff  ";
    send.click();
    expect(onSend).toHaveBeenCalledWith("explain this diff");
    expect(input.value).toBe("");
  });
  it("renders the supported Markdown blocks and nothing else", () => {
    const root = renderMarkdown(
      document,
      [
        "## Heading",
        "",
        "A paragraph with `inline code`.",
        "",
        "- first",
        "- second",
        "",
        "1. one",
        "2. two",
        "",
        "> quoted advice",
        "",
        "```ts",
        "const a: number = 1;",
        "```",
      ].join("\n"),
    );

    expect(root.querySelector("h2")?.textContent).toBe("Heading");
    expect(root.querySelector("p.assistant-paragraph")?.textContent).toBe("A paragraph with inline code.");
    expect(root.querySelector("p code.assistant-inline-code")?.textContent).toBe("inline code");
    expect(Array.from(root.querySelectorAll("ul li")).map((li) => li.textContent)).toEqual(["first", "second"]);
    expect(Array.from(root.querySelectorAll("ol li")).map((li) => li.textContent)).toEqual(["one", "two"]);
    expect(root.querySelector("blockquote")?.textContent).toBe("quoted advice");
    expect(root.querySelector("[data-role='code-block']")).not.toBeNull();
  });

  it("never turns Markdown into HTML or a script", () => {
    const root = renderMarkdown(document, "<img src=x onerror=alert(1)> <script>alert(2)</script> [x](javascript:alert(3))");
    expect(root.querySelector("img")).toBeNull();
    expect(root.querySelector("script")).toBeNull();
    expect(root.querySelector("a")).toBeNull();
    expect(root.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(code("assistant/markdown.ts")).not.toMatch(/innerHTML|outerHTML|insertAdjacentHTML|createContextualFragment/);
  });

  it("gives a code block a language label and Copy, but no Run control", () => {
    const onCopy = vi.fn();
    const root = renderMarkdown(document, "```python\nprint('hi')\n```", { onCopy });
    document.body.appendChild(root);

    expect(root.querySelector("[data-role='code-language']")?.textContent).toBe("python");
    const copy = root.querySelector<HTMLButtonElement>("[data-role='copy-code']")!;
    copy.click();
    expect(onCopy).toHaveBeenCalledWith("print('hi')");
    expect(copy.textContent).toBe("Copied");
    for (const label of buttonLabels(root)) expect(label).not.toMatch(FORBIDDEN_CONTROL);
    expect(renderMarkdown(document, "```\nplain\n```").querySelector("[data-role='code-language']")?.textContent).toBe("text");
  });
});

describe("phase 32 · streaming", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows the loading indicator and a Stop button while streaming", () => {
    const onStop = vi.fn();
    const root = renderAssistantChat(document, chatState({ streaming: true, status: "Streaming…" }), {
      onSend: () => {},
      onStop,
    });
    document.body.appendChild(root);

    expect(root.querySelector("[data-role='chat-loading']")?.textContent).toBe("Loading…");
    expect(root.querySelector<HTMLButtonElement>("[data-role='chat-send']")!.disabled).toBe(true);
    root.querySelector<HTMLButtonElement>("[data-role='chat-stop']")!.click();
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("marks a turn as streaming and then as stopped", () => {
    const streaming = renderChatTurn(document, turn({ streaming: true }), "user", { onSend: () => {} });
    expect(streaming.querySelector("[data-role='chat-streaming']")?.textContent).toBe("Streaming…");

    const stopped = renderChatTurn(document, turn({ stopped: true }), "user", { onSend: () => {} });
    expect(stopped.querySelector("[data-role='chat-stopped']")?.textContent).toBe("Streaming stopped");
  });

  it("keeps the partial reply when the user stops and reports it", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.hydrate();
    await store.appendAssistantTurn(turn({ id: "t_1", content: "partial", streaming: true }));
    const state = await store.stopAssistantStreaming();

    const active = state.assistantConversations[0].turns[0];
    expect(active).toMatchObject({ content: "partial", streaming: false, stopped: true });
    expect(state.assistantStreaming).toBe(false);
    expect(state.assistantStatus).toBe("Streaming stopped");
  });

  it("parses SSE frames token by token across chunk boundaries", async () => {
    const text =
      frame({ content: "Hel" }) + frame({ content: "lo" }) + frame({ type: "tool_call", toolCall: toolCall() });
    const fetchImpl = vi.fn(async () => sseResponse([text.slice(0, 25), text.slice(25, 70), text.slice(70)]));
    const client = new BridgeClient({
      origin: "http://127.0.0.1:8765",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });

    const seen: AssistantStreamEvent[] = [];
    await client.assistantChatStream(
      { project: "demo", messages: [{ role: "user", content: "hi" }] },
      { onEvent: (event) => seen.push(event) },
    );

    expect(seen.map((event) => event.content)).toEqual(["Hel", "lo", ""]);
    expect(seen[2].toolCall?.name).toBe("file_write");
  });
  it("accumulates streamed tokens into the assistant turn and records tool calls as proposals", async () => {
    const assistantChatStream = vi.fn(async (_body: unknown, options: { onEvent: (e: AssistantStreamEvent) => void }) => {
      options.onEvent({ type: "token", content: "Hel", toolCall: null, provider: "openai", model: "gpt-5" });
      options.onEvent({ type: "token", content: "lo", toolCall: null, provider: "openai", model: "gpt-5" });
      options.onEvent({ type: "tool_call", content: "", toolCall: toolCall(), provider: "openai", model: "gpt-5" });
    });
    const { store, controller } = controllerFor({ assistantChatStream });

    await controller.sendAssistantMessage("hi");

    const turns = store.getState().assistantConversations[0].turns;
    expect(turns.map((item) => item.role)).toEqual(["user", "assistant"]);
    expect(turns[1]).toMatchObject({ content: "Hello", streaming: false });
    expect(turns[1].toolCalls).toEqual([toolCall()]);
    expect(store.getState().assistantStreaming).toBe(false);
    expect(store.getState().assistantStatus).toBe("Tool proposal waiting for approval.");
  });

  it("keeps the partial tokens and never retries after Stop", async () => {
    let controller!: Controller;
    const assistantChatStream = vi.fn(
      async (_body: unknown, options: { signal?: AbortSignal; onEvent: (e: AssistantStreamEvent) => void }) => {
        options.onEvent({ type: "token", content: "par", toolCall: null, provider: "openai", model: "gpt-5" });
        await controller.stopAssistant();
        if (options.signal?.aborted) return;
        options.onEvent({ type: "token", content: "tial", toolCall: null, provider: "openai", model: "gpt-5" });
      },
    );
    const built = controllerFor({ assistantChatStream });
    controller = built.controller;

    await controller.sendAssistantMessage("hi");

    expect(assistantChatStream).toHaveBeenCalledTimes(1);
    const turns = built.store.getState().assistantConversations[0].turns;
    expect(turns[1]).toMatchObject({ content: "par", streaming: false, stopped: true });
    expect(built.store.getState().assistantStatus).toBe("Streaming stopped");
  });

  it("reports a stream failure without retrying it", async () => {
    const assistantChatStream = vi.fn(async () => {
      throw new Error("Bridge unavailable");
    });
    const { store, controller } = controllerFor({ assistantChatStream });

    await controller.sendAssistantMessage("hi");

    expect(assistantChatStream).toHaveBeenCalledTimes(1);
    expect(store.getState().assistantStreaming).toBe(false);
    // Phase 34 · the panel shows the unified safe message for a network-level
    // failure. The thrown text is used to classify it and never displayed.
    expect(store.getState().assistantStatus).toBe("Backend unreachable");
    // Still nothing automatic: no timer in the controller, and no second
    // request after the failure has settled. Retry exists only as a click.
    expect(code("content/controller.ts")).not.toMatch(/setTimeout|setInterval|requestAnimationFrame/i);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(assistantChatStream).toHaveBeenCalledTimes(1);
  });
});

describe("phase 32 · conversation history", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("lists conversations newest first with Open and Remove from view", () => {
    const onSelectConversation = vi.fn();
    const onRemoveConversation = vi.fn();
    const older = { ...conversation([turn()]), id: "local_1", title: "First" };
    const newer = { ...conversation([turn()]), id: "local_2", title: "Second" };
    const root = renderAssistantChat(
      document,
      chatState({ conversations: [older, newer], activeConversation: "local_2" }),
      { onSend: () => {}, onSelectConversation, onRemoveConversation },
    );
    document.body.appendChild(root);

    const entries = Array.from(root.querySelectorAll<HTMLElement>("[data-role='history-entry']"));
    expect(entries.map((entry) => entry.dataset.conversationId)).toEqual(["local_2", "local_1"]);
    expect(entries[0].className).toContain("active");

    const remove = entries[1].querySelector<HTMLButtonElement>("[data-role='remove-conversation']")!;
    expect(remove.textContent).toBe("Remove from view");
    expect(remove.title).toContain("extension only");
    remove.click();
    expect(onRemoveConversation).toHaveBeenCalledWith("local_1");

    entries[1].querySelector<HTMLButtonElement>("[data-role='open-conversation']")!.click();
    expect(onSelectConversation).toHaveBeenCalledWith("local_1");
  });

  it("starts a new local-only conversation and titles it from the first message", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.hydrate();
    const started = await store.newAssistantConversation();
    expect(started.assistantConversations[0].localOnly).toBe(true);

    const state = await store.appendAssistantTurn(
      turn({ id: "t_u", role: "user", content: "Explain this page" }),
    );
    expect(state.assistantConversations[0].title).toBe("Explain this page");
    expect(state.assistantActiveConversation).toBe(state.assistantConversations[0].id);
  });

  it("removes a conversation from the view only and keeps the rest", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.hydrate();
    const first = (await store.newAssistantConversation("One")).assistantActiveConversation!;
    const second = (await store.newAssistantConversation("Two")).assistantActiveConversation!;

    const state = await store.removeAssistantConversation(second);
    expect(state.assistantConversations.map((item) => item.id)).toEqual([first]);
    expect(state.assistantActiveConversation).toBe(first);

    // The display store has no Bridge access at all, so no history operation
    // can reach Phase 31 conversation storage.
    expect(code("state/store.ts")).not.toMatch(/fetch\(|BridgeClient|conversations\//);
  });

  it("keeps every history control free of execution verbs", () => {
    const root = renderAssistantChat(
      document,
      chatState({ conversations: [conversation([turn()])], activeConversation: "local_1" }),
      { onSend: () => {} },
    );
    for (const label of buttonLabels(root)) expect(label).not.toMatch(FORBIDDEN_CONTROL);
  });
});

describe("phase 32 · ask ai and the context bundle", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    document.title = "Docs";
  });

  it("collects nothing until Ask AI is clicked", () => {
    const collect = vi.fn((doc: Document) => collectWebContext(doc, { timestamp: "2026-01-01T00:00:00.000Z" }));
    const onAskAi = vi.fn();
    const button = renderAskAiButton(document, { onAskAi, collect });
    document.body.appendChild(button);

    expect(collect).not.toHaveBeenCalled();
    expect(onAskAi).not.toHaveBeenCalled();

    button.click();

    expect(collect).toHaveBeenCalledTimes(1);
    expect(onAskAi).toHaveBeenCalledTimes(1);
    expect(onAskAi.mock.calls[0][0]).toMatchObject({
      trigger: ASK_AI_TRIGGER,
      consented_at: "2026-01-01T00:00:00.000Z",
    });
  });

  it("registers no background capture hook", () => {
    const module = code("assistant/web-context.ts");
    expect(module).not.toMatch(/DOMContentLoaded|visibilitychange|MutationObserver|setInterval|setTimeout/);
    expect(module).not.toMatch(/addEventListener\(\s*["'](load|scroll|focus|mouseup|selectionchange)["']/);
    // The only listener in the module is the Ask AI click itself.
    expect(module.match(/addEventListener\(/g)).toHaveLength(2);
  });

  it("captures page, selection, readable content and timestamp, minus the query string", () => {
    document.body.innerHTML = "<main>Readable body text</main>";
    const collected = bundle();

    expect(collected.page_title).toBe("Docs");
    expect(collected.page_url).toBe("https://example.com/docs");
    expect(collected.page_url).not.toContain("token");
    expect(collected.readable_content).toBe("Readable body text");
    expect(collected.timestamp).toBe("2026-01-01T00:00:00.000Z");
    expect(bundle("file:///G:/private/notes.txt").page_url).toBe("");
  });

  it("previews the bundle read-only, with a remove control and no execution verbs", () => {
    const onClearContext = vi.fn();
    const root = renderWebContextPreview(document, bundle(), { onClearContext });
    document.body.appendChild(root);

    const labels = Array.from(root.querySelectorAll(".assistant-context-label")).map((n) => n.textContent);
    expect(labels).toEqual(
      expect.arrayContaining(["Page:", "URL:", "Selected Text:", "Readable Content:", "Timestamp:", "Trigger:"]),
    );
    expect(root.querySelectorAll("input, textarea, select")).toHaveLength(0);
    for (const label of buttonLabels(root)) expect(label).not.toMatch(FORBIDDEN_CONTROL);

    root.querySelector<HTMLButtonElement>("[data-role='clear-context']")!.click();
    expect(onClearContext).toHaveBeenCalledTimes(1);
  });

  it("says so when there is no context yet", () => {
    const root = renderWebContextPreview(document, null);
    expect(root.textContent).toContain("Click Ask AI to share this page");
  });

  it("stores the collected bundle without contacting the Bridge", async () => {
    const { store, controller, touched } = controllerFor();

    await controller.askAi(bundle());

    expect(store.getState().assistantWebContext).toMatchObject({ trigger: ASK_AI_TRIGGER });
    expect(store.getState().assistantStatus).toBe("Page context ready. It is sent only with your next message.");
    expect(touched).toEqual([]);
  });

  it("sends the bundle only with the user's message and forgets it afterwards", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    const assistantChatStream = vi.fn(async (body: Record<string, unknown>, options: { onEvent: (e: AssistantStreamEvent) => void }) => {
      bodies.push(body);
      options.onEvent({ type: "token", content: "ok", toolCall: null, provider: "openai", model: "gpt-5" });
    });
    const { store, controller } = controllerFor({ assistantChatStream });

    await controller.askAi(bundle());
    await controller.sendAssistantMessage("what is this page?");

    expect(bodies).toHaveLength(1);
    expect(bodies[0].web_context).toMatchObject({ trigger: ASK_AI_TRIGGER, page_url: "https://example.com/docs" });
    expect(store.getState().assistantWebContext).toBeNull();

    await controller.sendAssistantMessage("and again?");
    expect(bodies[1].web_context).toBeNull();
  });
});

describe("phase 32 · developer context and tool proposals", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("renders the developer context read-only, with no control at all", () => {
    const root = renderDeveloperContext(document, contextStatus());
    document.body.appendChild(root);

    expect(root.dataset.role).toBe("developer-context");
    expect(root.querySelector(".assistant-badge")?.textContent).toBe("READ ONLY");
    const labels = Array.from(root.querySelectorAll(".assistant-context-label")).map((n) => n.textContent);
    expect(labels).toEqual(
      expect.arrayContaining(["Loaded:", "Project:", "Sources:", "Endpoint:", "Modifications:"]),
    );
    expect(root.textContent).toContain("require human approval");
    expect(root.textContent).toContain("explicit Ask AI only");
    expect(root.textContent).toContain("cannot modify source files or run anything");
    expect(root.querySelectorAll("button, input, textarea, select")).toHaveLength(0);
    expect(code("assistant/dev-context-view.ts")).not.toMatch(/addEventListener|createElement\("button"\)/);
  });

  it("says the developer context is not loaded when the Bridge has not answered", () => {
    const root = renderDeveloperContext(document, null);
    expect(root.textContent).toContain("not loaded");
  });

  it("renders a tool call as an inert proposal waiting for approval", () => {
    const card = renderToolProposal(document, toolCall());
    document.body.appendChild(card);

    expect(card.dataset.role).toBe("tool-proposal");
    expect(card.querySelector("[data-role='tool-state']")?.textContent).toBe("Waiting Approval");
    expect(card.querySelector("[data-role='tool-arguments']")?.textContent).toBe('{"path":"src/a.ts"}');
    expect(card.querySelectorAll("button")).toHaveLength(0);
    expect(card.textContent).toContain("A human approves it");
  });

  it("shows tool proposals in Developer Mode only", () => {
    const withCalls = turn({ toolCalls: [toolCall()] });

    const user = renderChatTurn(document, withCalls, "user", { onSend: () => {} });
    expect(user.querySelector("[data-role='tool-proposal']")).toBeNull();

    const developer = renderChatTurn(document, withCalls, "developer", { onSend: () => {} });
    expect(developer.querySelector("[data-role='tool-proposal']")).not.toBeNull();
    expect(buttonLabels(developer)).toEqual([]);
  });

  it("keeps the developer surface out of User Mode entirely", () => {
    const patch = {
      bridgeStatus: "connected" as const,
      currentProject: "demo",
      assistantContextStatus: contextStatus(),
      assistantConversations: [conversation([turn({ toolCalls: [toolCall()] })])],
      assistantActiveConversation: "local_1",
    };

    const user = mountPanel({ ...patch, uiMode: "user" });
    expect(user.querySelector("[data-role='developer-surface']")).toBeNull();
    expect(user.querySelector("[data-role='developer-context']")).toBeNull();
    expect(user.querySelector("[data-role='tool-proposal']")).toBeNull();

    const developer = mountPanel({ ...patch, uiMode: "developer" });
    expect(developer.querySelector("[data-role='developer-surface']")).not.toBeNull();
    expect(developer.querySelector("[data-role='developer-context']")).not.toBeNull();
    expect(developer.querySelector("[data-role='tool-proposal']")).not.toBeNull();
  });

  it("loads no developer engineering data while in User Mode", async () => {
    const { store, controller, touched } = controllerFor();
    await store.update({ currentProject: "demo", uiMode: "user" });

    await controller.refreshContext();

    // Any endpoint the fake does not stub throws, so this also proves nothing
    // else was called; the assertion names the developer endpoints explicitly.
    expect(new Set(touched)).toEqual(new Set(["userSettings", "providerStatus", "contextStatus"]));
    for (const endpoint of ["projectContext", "governanceHealth", "intelligenceInsights", "engineeringGraph"]) {
      expect(touched).not.toContain(endpoint);
    }
    expect(store.getState().projectContext).toBeNull();
    expect(store.getState().assistantSettings).not.toBeNull();
  });
});
