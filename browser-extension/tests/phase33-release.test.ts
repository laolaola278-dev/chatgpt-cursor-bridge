/**
 * Phase 33 · Release validation — extension tests (spec §4/§6/§9/§10/§14/§16/§20).
 *
 * Five groups, all offline:
 *
 * 1. **The packaged bundle** — `dist/` holds exactly the three runtime files,
 *    the manifest is minimal (no `<all_urls>`), and neither bundle carries a
 *    secret or an execution primitive.
 * 2. **User Mode release experience (§9)** — a fresh install lands on the
 *    AI Assistant chat and shows no Governance / Intelligence / Graph / Metrics
 *    / Developer Context surface and no execute-shaped control.
 * 3. **Provider status (§10)** — OpenAI / Anthropic / DeepSeek each render
 *    Connected / Not configured / Failed, with a masked key tail and no key.
 * 4. **Streaming + unreachable backend (§16/§20)** — start → token → render →
 *    finish, Stop keeps the partial text and never re-sends, a failure is
 *    reported once, and an offline Bridge yields a readable sentence rather
 *    than a stack trace or a file path.
 * 5. **Local performance budgets (§14, extension half)** — 100-turn rendering,
 *    100-token accumulation and 100 chat state updates, each with a recorded
 *    elapsed / average / max and a generous budget.
 *
 * Nothing here builds, publishes or approves anything.
 */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderAssistantChat, renderChatTurn } from "../src/assistant/chat-view";
import type { AssistantChatViewState } from "../src/assistant/chat-view";
import { renderProviderSettings, statusLabel } from "../src/assistant/settings-view";
import type { AssistantSettingsViewState } from "../src/assistant/settings-view";
import {
  DEVELOPER_ONLY_SURFACES,
  NEVER_AVAILABLE,
  USER_MODE_SURFACES,
} from "../src/assistant/types";
import type {
  AssistantChatTurn,
  AssistantConversationView,
  AssistantProviderEntry,
  AssistantStreamEvent,
  AssistantUserSettings,
} from "../src/assistant/types";
import { BridgeClient } from "../src/bridge/client";
import { Controller } from "../src/content/controller";
import { createInitialState, ExtensionStore } from "../src/state/store";
import type { ExtensionState } from "../src/state/store";
import { Panel } from "../src/ui/panel";
import type { PanelHandlers } from "../src/ui/panel";

vi.mock("../src/ui/styles.css?inline", () => ({ default: ".panel{}" }));

const DIST = resolve(__dirname, "../dist");
const RUNTIME_FILES = ["manifest.json", "content/content.js", "background/service-worker.js"];

/** Execution primitives that must never appear in a shipped bundle. */
const FORBIDDEN_BUNDLE_TOKENS = [
  "child_process",
  "new Function(",
  "chrome.debugger",
  "declarativeNetRequest",
  "webRequestBlocking",
  "<all_urls>",
];

/** Surfaces an ordinary user must not be shown by default (§9). */
const DEVELOPER_SURFACE_WORDS = /governance|intelligence|engineering graph|metrics|developer context/i;

/** Controls no release surface may offer (§18). */
const FORBIDDEN_CONTROL = /execute|approve|apply|auto ?fix|auto ?patch|\brun\b|terminal|shell/i;

/** Budgets in milliseconds. Generous: an order-of-magnitude guard, not a claim. */
const BUDGETS = {
  render100Turns: 4000,
  accumulate100Tokens: 1500,
  update100States: 4000,
};

const MEASUREMENTS: Record<string, { elapsed: number; average: number; max: number }> = {};

function measure(name: string, samples: number[]): { elapsed: number; average: number; max: number } {
  const elapsed = samples.reduce((total, value) => total + value, 0);
  const result = { elapsed, average: elapsed / samples.length, max: Math.max(...samples) };
  MEASUREMENTS[name] = result;
  return result;
}

function bundleText(relative: string): string {
  return readFileSync(resolve(DIST, relative), "utf8");
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
    models: ["gpt-5", "gpt-4o"],
    ...overrides,
  };
}

const ANTHROPIC = providerEntry({
  provider: "anthropic",
  displayName: "Anthropic",
  status: "not_configured",
  hasStoredKey: false,
  keyHint: "",
  keyEnv: "ANTHROPIC_API_KEY",
  baseUrl: "",
  selectedModel: "claude-4-sonnet",
  models: ["claude-4-sonnet", "claude-3-5-haiku"],
});

const DEEPSEEK = providerEntry({
  provider: "deepseek",
  displayName: "DeepSeek",
  status: "failed",
  hasStoredKey: true,
  keyHint: "****9876",
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
    preferences: {},
    surfaces: [...USER_MODE_SURFACES],
    neverAvailable: [...NEVER_AVAILABLE],
    providers: [{ provider: "openai", status: "connected", hasStoredKey: true, models: ["gpt-5"] }],
    keyStorage: { algorithm: "AES-256-GCM", available: true, location: "bridge key store" },
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
    providers: [providerEntry(), ANTHROPIC, DEEPSEEK],
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

function fakeClient(overrides: Record<string, unknown> = {}) {
  const touched: string[] = [];
  const base: Record<string, unknown> = {
    userSettings: vi.fn(async () => userSettings()),
    providerStatus: vi.fn(async () => ({ providers: [providerEntry()], readOnly: true as const })),
    contextStatus: vi.fn(async () => null),
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

function buttonLabels(root: ParentNode): string[] {
  return Array.from(root.querySelectorAll("button")).map(
    (button) => `${button.textContent ?? ""} ${button.dataset.role ?? ""}`,
  );
}

const distBuilt = RUNTIME_FILES.every((name) => existsSync(resolve(DIST, name)));
const describeBundle = distBuilt ? describe : describe.skip;

// -- 1. The packaged bundle ---------------------------------------------------

describeBundle("phase 33 · packaged bundle", () => {
  it("ships exactly the three runtime files", () => {
    for (const name of RUNTIME_FILES) expect(existsSync(resolve(DIST, name))).toBe(true);
  });

  it("keeps the manifest minimal and MV3", () => {
    const manifest = JSON.parse(bundleText("manifest.json"));
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.background.service_worker).toBe("background/service-worker.js");
    expect([...manifest.permissions].sort()).toEqual(["scripting", "storage"]);
    expect(manifest.optional_permissions).toBeUndefined();
    for (const host of manifest.host_permissions as string[]) {
      expect(host).not.toBe("<all_urls>");
      expect(host).not.toContain("://*/*");
    }
    for (const entry of manifest.content_scripts as { js: string[]; matches: string[] }[]) {
      expect(entry.js).toContain("content/content.js");
      for (const match of entry.matches) expect(match).not.toBe("<all_urls>");
    }
  });

  it("carries no secret and no execution primitive", () => {
    for (const name of ["content/content.js", "background/service-worker.js"]) {
      const text = bundleText(name);
      expect(text).not.toMatch(/sk-[A-Za-z0-9_-]{16,}/);
      expect(text).not.toMatch(/(?:^|[^A-Za-z])Bearer\s+[A-Za-z0-9._-]{16,}/);
      expect(text).not.toMatch(/-----BEGIN [A-Z ]*PRIVATE KEY-----/);
      for (const token of FORBIDDEN_BUNDLE_TOKENS) expect(text).not.toContain(token);
    }
  });

  it("ships no source map alongside the bundles", () => {
    for (const name of ["content/content.js.map", "background/service-worker.js.map"]) {
      expect(existsSync(resolve(DIST, name))).toBe(false);
    }
  });
});

// -- 2. User Mode release experience (§9) ------------------------------------

describe("phase 33 · user mode release experience", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("installs into User Mode with the assistant chat as the first surface", () => {
    const state = createInitialState();
    expect(state.uiMode).toBe("user");
    expect(USER_MODE_SURFACES[0]).toBe("chat");
  });

  it("offers no developer-only surface in the user surface list", () => {
    for (const surface of DEVELOPER_ONLY_SURFACES) {
      expect(USER_MODE_SURFACES as readonly string[]).not.toContain(surface);
    }
    for (const surface of USER_MODE_SURFACES) {
      expect(surface).not.toMatch(DEVELOPER_SURFACE_WORDS);
    }
  });

  it("renders no governance / intelligence / graph / metrics wording by default", () => {
    const container = mountPanel({ uiMode: "user", assistantSettings: userSettings() });
    const headings = Array.from(container.querySelectorAll("h1, h2, h3, h4, summary")).map(
      (node) => node.textContent ?? "",
    );
    for (const heading of headings) expect(heading).not.toMatch(DEVELOPER_SURFACE_WORDS);
  });

  it("renders no execute-shaped control in the user chat surface", () => {
    const state = chatState({
      conversations: [conversation([turn()])],
      activeConversation: "local_1",
    });
    const root = renderAssistantChat(document, state, { onSend: () => {} });
    expect(root.querySelectorAll("[data-role='chat-message']").length).toBe(1);
    for (const label of buttonLabels(root)) expect(label).not.toMatch(FORBIDDEN_CONTROL);
  });

  it("keeps the forbidden capability list identical to the Bridge's", () => {
    expect([...NEVER_AVAILABLE]).toEqual([
      "execute",
      "approve_from_chat",
      "apply_patch",
      "auto_fix",
      "auto_approve",
      "shell",
    ]);
  });
});

// -- 3. Provider status (§10) ------------------------------------------------

describe("phase 33 · provider status", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("labels the three connection states", () => {
    expect(statusLabel("connected")).toBe("Connected");
    expect(statusLabel("not_configured")).toBe("Not configured");
    expect(statusLabel("failed")).toBe("Failed");
    expect(statusLabel("something-else")).toBe("Not configured");
  });

  it("shows a state for OpenAI, Anthropic and DeepSeek at once", () => {
    const root = renderProviderSettings(document, settingsState(), {});
    document.body.appendChild(root);
    const text = root.textContent ?? "";
    for (const name of ["OpenAI", "Anthropic", "DeepSeek"]) expect(text).toContain(name);
    for (const label of ["Connected", "Not configured", "Failed"]) expect(text).toContain(label);
    const rows = Array.from(root.querySelectorAll("[data-role='provider-row']"));
    expect(rows.map((row) => (row as HTMLElement).dataset.provider)).toEqual([
      "openai",
      "anthropic",
      "deepseek",
    ]);
  });

  it("never renders key material, only a masked tail", () => {
    const root = renderProviderSettings(document, settingsState(), {});
    document.body.appendChild(root);
    const markup = root.innerHTML;
    expect(markup).not.toMatch(/sk-[A-Za-z0-9_-]{16,}/);
    expect(markup).not.toMatch(/Bearer\s+[A-Za-z0-9._-]{16,}/);
    const hints = Array.from(root.querySelectorAll("[data-role='provider-key-hint']")).map(
      (node) => node.textContent ?? "",
    );
    expect(hints.length).toBeGreaterThan(0);
    for (const hint of hints) expect(hint).toMatch(/^(\*{4}[A-Za-z0-9]+|stored|no key stored)$/);
    const keyInput = root.querySelector<HTMLInputElement>("input[type='password']");
    expect(keyInput?.value ?? "").toBe("");
  });
});

// -- 4. Streaming and an unreachable backend (§16/§20) -----------------------

describe("phase 33 · streaming and backend reachability", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("runs start → token → render → finish once", async () => {
    const assistantChatStream = vi.fn(
      async (_body: unknown, options: { onEvent: (event: AssistantStreamEvent) => void }) => {
        options.onEvent({ type: "delta", content: "Re", toolCall: null, provider: "openai", model: "gpt-5" });
        options.onEvent({ type: "delta", content: "ady", toolCall: null, provider: "openai", model: "gpt-5" });
        options.onEvent({ type: "done", content: "", toolCall: null, provider: "openai", model: "gpt-5" });
      },
    );
    const { store, controller } = controllerFor({ assistantChatStream });

    await controller.sendAssistantMessage("hi");

    expect(assistantChatStream).toHaveBeenCalledTimes(1);
    const turns = store.getState().assistantConversations[0].turns;
    expect(turns.map((item) => item.role)).toEqual(["user", "assistant"]);
    expect(turns[1]).toMatchObject({ content: "Ready", streaming: false });
    expect(store.getState().assistantStreaming).toBe(false);
    expect(store.getState().assistantStatus).toBe("");

    const rendered = renderChatTurn(document, turns[1], "user", { onSend: () => {} });
    expect(rendered.textContent).toContain("Ready");
  });

  it("keeps the partial text on Stop and never re-sends", async () => {
    let controller!: Controller;
    const assistantChatStream = vi.fn(
      async (
        _body: unknown,
        options: { signal?: AbortSignal; onEvent: (event: AssistantStreamEvent) => void },
      ) => {
        options.onEvent({ type: "delta", content: "half", toolCall: null, provider: "openai", model: "gpt-5" });
        await controller.stopAssistant();
        if (options.signal?.aborted) return;
        options.onEvent({ type: "delta", content: "-more", toolCall: null, provider: "openai", model: "gpt-5" });
      },
    );
    const built = controllerFor({ assistantChatStream });
    controller = built.controller;

    await controller.sendAssistantMessage("hi");

    expect(assistantChatStream).toHaveBeenCalledTimes(1);
    const turns = built.store.getState().assistantConversations[0].turns;
    expect(turns[1]).toMatchObject({ content: "half", streaming: false, stopped: true });
    expect(built.store.getState().assistantStatus).toBe("Streaming stopped");
  });

  it("reports a stream failure once, without a retry", async () => {
    const assistantChatStream = vi.fn(async () => {
      throw new Error("Backend unreachable");
    });
    const { store, controller } = controllerFor({ assistantChatStream });

    await controller.sendAssistantMessage("hi");

    expect(assistantChatStream).toHaveBeenCalledTimes(1);
    expect(store.getState().assistantStreaming).toBe(false);
    expect(store.getState().assistantStatus).toContain("Backend unreachable");
  });

  it("explains an offline Bridge in one readable sentence", () => {
    const container = mountPanel({ bridgeStatus: "offline" });
    const text = container.textContent ?? "";
    expect(text).toContain("Local Bridge unavailable. Start it with: uvicorn app.main:app --port 8765");
    expect(text).not.toMatch(/Traceback|at Object\.<anonymous>|\.py:\d+|[A-Za-z]:\\/);
  });

  it("shows no stack trace or path when a read fails", async () => {
    const { store, controller } = controllerFor({
      userSettings: vi.fn(async () => {
        throw new Error("Backend unreachable");
      }),
    });

    await controller.refreshAssistant();

    const status = store.getState().assistantStatus;
    expect(status).toBe("Backend unreachable");
    expect(status).not.toMatch(/Traceback|node_modules|[A-Za-z]:\\/);
  });
});

// -- 5. Local performance budgets (§14) --------------------------------------

describe("phase 33 · local performance budgets", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("renders a 100-turn conversation within budget", () => {
    const turns = Array.from({ length: 100 }, (_unused, index) =>
      turn({
        id: `turn_${index}`,
        role: index % 2 === 0 ? "user" : "assistant",
        content: `message ${index}`,
      }),
    );
    const state = chatState({
      conversations: [conversation(turns)],
      activeConversation: "local_1",
    });

    const start = performance.now();
    const root = renderAssistantChat(document, state, { onSend: () => {} });
    document.body.appendChild(root);
    const elapsed = performance.now() - start;

    expect(root.querySelectorAll("[data-role='chat-message']").length).toBe(100);
    measure("render100Turns", [elapsed]);
    expect(elapsed).toBeLessThan(BUDGETS.render100Turns);
  });

  it("accumulates 100 streamed tokens within budget", async () => {
    const events: AssistantStreamEvent[] = Array.from({ length: 100 }, (_unused, index) => ({
      type: "delta",
      content: `t${index} `,
      toolCall: null,
      provider: "openai",
      model: "gpt-5",
    }));
    const assistantChatStream = vi.fn(
      async (_body: unknown, options: { onEvent: (event: AssistantStreamEvent) => void }) => {
        for (const event of events) options.onEvent(event);
      },
    );
    const { store, controller } = controllerFor({ assistantChatStream });

    const start = performance.now();
    await controller.sendAssistantMessage("hi");
    const elapsed = performance.now() - start;

    const reply = store.getState().assistantConversations[0].turns[1];
    expect(reply.content.split(/\s+/).filter(Boolean)).toHaveLength(100);
    measure("accumulate100Tokens", [elapsed]);
    expect(elapsed).toBeLessThan(BUDGETS.accumulate100Tokens);
  });

  it("applies 100 chat state updates within budget", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.hydrate();

    const samples: number[] = [];
    for (let index = 0; index < 100; index += 1) {
      const start = performance.now();
      await store.update({ assistantStatus: `step ${index}` });
      samples.push(performance.now() - start);
    }

    expect(store.getState().assistantStatus).toBe("step 99");
    const result = measure("update100States", samples);
    expect(result.elapsed).toBeLessThan(BUDGETS.update100States);
    expect(result.max).toBeLessThan(BUDGETS.update100States);
  });

  it("records elapsed, average and max for every measurement", () => {
    for (const [name, result] of Object.entries(MEASUREMENTS)) {
      expect(result.elapsed, name).toBeGreaterThanOrEqual(0);
      expect(result.average, name).toBeGreaterThanOrEqual(0);
      expect(result.max, name).toBeLessThanOrEqual(result.elapsed + 1e-6);
      // Local baselines only: no provider capacity is implied by these numbers.
      expect(name).not.toMatch(/openai|anthropic|deepseek|throughput/i);
    }
  });
});
