/**
 * Phase 34 · User Trial & Product Refinement — extension tests (spec §1–§8).
 *
 * Six groups, all offline. Every provider call is a mock: no real API key and
 * no external LLM request exists anywhere in this file.
 *
 * 1. **First-run onboarding (§1)** — auto-shown once, Next / Back / Skip /
 *    Setup Later / Finish, skippable with no Bridge and no provider, settled
 *    states are never shown again, and the marker is non-sensitive.
 * 2. **Unified error experience (§2)** — 401 / 429 / 5xx / network / stopped /
 *    `provider_not_configured` each map to one fixed sentence, and no stack
 *    trace, path, key, header or vendor body can reach the panel.
 * 3. **Chat UX (§3)** — Enter vs Shift+Enter, composer growth cap, loading,
 *    Stop, Retry, draft preservation, no duplicated user turn, no auto-retry.
 * 4. **Conversation management (§4)** — search / rename / pin / remove / new,
 *    all local, tolerant of corrupt storage and unknown ids.
 * 5. **Context preview & control (§5)** — the panel shows what would be
 *    injected, the user decides, and nothing is collected or sent on its own.
 * 6. **Security acceptance (§8.6)** — no execute / approve / apply / auto-fix /
 *    shell control in User Mode, no permission bypass, no secret persisted.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  autoGrowComposer,
  MAX_COMPOSER_HEIGHT,
  renderAssistantChat,
  type AssistantChatViewState,
} from "../src/assistant/chat-view";
import { injectedContextText } from "../src/assistant/context-panel";
import {
  classifyError,
  containsForbiddenDetail,
  isSafeMessage,
  safeErrorMessage,
  sanitizeStatusText,
  SAFE_MESSAGES,
} from "../src/assistant/errors";
import {
  isOnboardingDeferred,
  isOnboardingVisible,
  onboardingStepAt,
  renderOnboarding,
  renderOnboardingHint,
} from "../src/assistant/onboarding";
import {
  DEVELOPER_ONLY_SURFACES,
  NEVER_AVAILABLE,
  ONBOARDING_SETTLED_STATES,
  ONBOARDING_STEP_COUNT,
  ONBOARDING_STEPS,
  USER_MODE_SURFACES,
  type AssistantChatTurn,
  type AssistantConversationView,
  type AssistantProviderEntry,
  type AssistantStreamEvent,
  type WebContextBundle,
} from "../src/assistant/types";
import type { BridgeClient } from "../src/bridge/client";
import { BridgeRequestError, BridgeUnavailableError } from "../src/bridge/types";
import { Controller } from "../src/content/controller";
import {
  createInitialState,
  ExtensionStore,
  isForbiddenStateKey,
  STORAGE_KEY,
  TRANSIENT_STATE_KEYS,
  visibleAssistantConversations,
} from "../src/state/store";
import type { ExtensionState } from "../src/state/store";
import { Panel, type PanelHandlers } from "../src/ui/panel";

vi.mock("../src/ui/styles.css?inline", () => ({ default: ".panel{}" }));

/** Controls User Mode must never offer (§8.6). */
const FORBIDDEN_CONTROL = /execute|approve|apply|auto ?fix|auto ?approve|shell|terminal|\brun\b/i;

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
    baseUrl: "",
    selectedModel: "gpt-5",
    lastTestedAt: "2026-01-01T00:00:00Z",
    models: ["gpt-5"],
    ...overrides,
  };
}

/** Every Bridge method not explicitly mocked throws, so a hidden call fails. */
function fakeClient(overrides: Record<string, unknown> = {}) {
  const touched: string[] = [];
  const base: Record<string, unknown> = { ...overrides };
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

async function controllerFor(
  overrides: Record<string, unknown> = {},
  patch: Partial<ExtensionState> = {},
) {
  const store = new ExtensionStore(memoryStorage());
  await store.update({ currentProject: "demo", ...patch });
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

function click(root: ParentNode, role: string): void {
  const node = root.querySelector<HTMLElement>(`[data-role="${role}"]`);
  if (!node) throw new Error(`missing control: ${role}`);
  node.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
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

function conversation(
  overrides: Partial<AssistantConversationView> = {},
): AssistantConversationView {
  return {
    id: "local_1",
    title: "Chat",
    createdAt: "2026-01-01T00:00:00.000Z",
    turns: [],
    localOnly: true,
    ...overrides,
  };
}

function chatState(overrides: Partial<AssistantChatViewState> = {}): AssistantChatViewState {
  return {
    uiMode: "user",
    conversations: [conversation({ turns: [turn()] })],
    activeConversation: "local_1",
    streaming: false,
    status: "",
    ...overrides,
  };
}

function bundle(overrides: Partial<WebContextBundle> = {}): WebContextBundle {
  return {
    trigger: "ask_ai",
    consented_at: "2026-01-01T00:00:00.000Z",
    page_title: "Rate limiting in FastAPI",
    page_url: "https://chatgpt.com/c/demo",
    selected_text: "How do I add a token bucket?",
    readable_content: "A token bucket refills at a fixed rate.",
    timestamp: "2026-01-01T00:00:00.000Z",
    ...overrides,
  };
}

/** A stream mock: emits the given events, then resolves. Never a real call. */
function streamMock(events: Partial<AssistantStreamEvent>[]) {
  return vi.fn(
    async (
      _body: unknown,
      options: { onEvent: (event: AssistantStreamEvent) => void; signal?: AbortSignal },
    ) => {
      for (const event of events) {
        options.onEvent({
          type: "delta",
          content: "",
          toolCall: null,
          provider: "openai",
          model: "gpt-5",
          ...event,
        });
      }
    },
  );
}

// -- 1. First-run onboarding (§1) ---------------------------------------------

describe("phase 34 · first run onboarding", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows the guide automatically on the first launch and lands on chat", () => {
    const state = createInitialState();
    expect(state.onboardingState).toBe("new");
    expect(state.onboardingStep).toBe(0);
    expect(isOnboardingVisible(state.onboardingState)).toBe(true);
    // §7 · the first surface a new user sees is still Chat.
    expect(state.uiMode).toBe("user");
    expect(USER_MODE_SURFACES[0]).toBe("chat");
    const container = mountPanel();
    expect(container.querySelector('[data-role="onboarding"]')).not.toBeNull();
    expect(container.querySelector('[data-role="assistant-chat"]')).not.toBeNull();
  });

  it("walks the four documented steps in order", () => {
    expect(ONBOARDING_STEP_COUNT).toBe(4);
    expect(ONBOARDING_STEPS.map((step) => step.id)).toEqual([
      "start_bridge",
      "configure_provider",
      "test_connection",
      "start_chat",
    ]);
    expect(onboardingStepAt(0).id).toBe("start_bridge");
    // Out-of-range values are clamped rather than crashing the panel.
    expect(onboardingStepAt(99).id).toBe("start_chat");
    expect(onboardingStepAt(-5).id).toBe("start_bridge");
  });

  it("advances with Next and finishes into chat on the last step", async () => {
    const store = new ExtensionStore(memoryStorage());
    for (let step = 1; step < ONBOARDING_STEP_COUNT; step += 1) {
      const state = await store.advanceOnboarding();
      expect(state.onboardingState).toBe("active");
      expect(state.onboardingStep).toBe(step);
    }
    const done = await store.advanceOnboarding();
    expect(done.onboardingState).toBe("done");
    expect(isOnboardingVisible(done.onboardingState)).toBe(false);
    expect(isOnboardingDeferred(done.onboardingState)).toBe(false);
  });

  it("goes Back without leaving the guide and clamps at the first step", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.advanceOnboarding();
    const back = await store.regressOnboarding();
    expect(back.onboardingStep).toBe(0);
    expect(back.onboardingState).toBe("active");
    expect((await store.regressOnboarding()).onboardingStep).toBe(0);
  });

  it("is skippable with no Bridge and no provider", async () => {
    const container = mountPanel({
      bridgeStatus: "offline",
      assistantProviders: [providerEntry({ status: "not_configured", hasStoredKey: false })],
    });
    const guide = container.querySelector('[data-role="onboarding"]');
    expect(guide).not.toBeNull();
    expect(guide?.querySelector('[data-role="onboarding-skip"]')).not.toBeNull();
    const store = new ExtensionStore(memoryStorage());
    const skipped = await store.skipOnboarding();
    expect(skipped.onboardingState).toBe("skipped");
    expect(isOnboardingVisible(skipped.onboardingState)).toBe(false);
  });

  it("keeps Setup Later reachable through a hint and re-openable on request", async () => {
    const store = new ExtensionStore(memoryStorage());
    const later = await store.deferOnboarding();
    expect(later.onboardingState).toBe("later");
    expect(isOnboardingVisible(later.onboardingState)).toBe(false);
    expect(isOnboardingDeferred(later.onboardingState)).toBe(true);
    const container = mountPanel({ onboardingState: "later" });
    expect(container.querySelector('[data-role="onboarding-hint"]')).not.toBeNull();
    expect(container.querySelector('[data-role="onboarding"]')).toBeNull();
    const reopened = await store.reopenOnboarding();
    expect(reopened.onboardingState).toBe("active");
    expect(reopened.onboardingStep).toBe(0);
  });

  it("never re-shows a settled guide on the next launch", async () => {
    for (const settled of ONBOARDING_SETTLED_STATES) {
      const storage = memoryStorage({ [STORAGE_KEY]: { onboardingState: settled } });
      const store = new ExtensionStore(storage);
      const state = await store.hydrate();
      expect(state.onboardingState).toBe(settled);
      expect(isOnboardingVisible(state.onboardingState)).toBe(false);
      expect(mountPanel({ onboardingState: settled }).querySelector('[data-role="onboarding"]')).toBeNull();
      document.body.innerHTML = "";
    }
  });

  it("persists a non-sensitive marker and no key of any kind", async () => {
    const storage = memoryStorage();
    const store = new ExtensionStore(storage);
    await store.completeOnboarding();
    const blob = storage.data.get(STORAGE_KEY) as Record<string, unknown>;
    expect(blob.onboardingState).toBe("done");
    for (const key of Object.keys(blob)) expect(isForbiddenStateKey(key)).toBe(false);
    const serialized = JSON.stringify(blob);
    expect(serialized).not.toMatch(/sk-[A-Za-z0-9_-]{8,}/);
    expect(serialized).not.toMatch(/api[_-]?key/i);
    expect(serialized).not.toMatch(/authorization|bearer/i);
  });

  it("changes no mode and no permission boundary", async () => {
    const store = new ExtensionStore(memoryStorage());
    const before = store.getState();
    const after = await store.completeOnboarding();
    expect(after.uiMode).toBe(before.uiMode);
    expect(NEVER_AVAILABLE).toEqual([
      "execute",
      "approve_from_chat",
      "apply_patch",
      "auto_fix",
      "auto_approve",
      "shell",
    ]);
  });

  it("offers no execute-shaped control and states that it stores no key", () => {
    const guide = renderOnboarding(document, {
      onboardingState: "active",
      onboardingStep: 1,
      bridgeReachable: false,
      providerConfigured: false,
    });
    for (const label of buttonLabels(guide)) expect(label).not.toMatch(FORBIDDEN_CONTROL);
    expect(guide.querySelector('[data-role="onboarding-note"]')?.textContent ?? "").toMatch(
      /stores no API key/i,
    );
    const hint = renderOnboardingHint(document);
    for (const label of buttonLabels(hint)) expect(label).not.toMatch(FORBIDDEN_CONTROL);
  });

  it("wires every guide button to an explicit user callback", () => {
    const calls: string[] = [];
    const guide = renderOnboarding(
      document,
      { onboardingState: "active", onboardingStep: 1, bridgeReachable: true, providerConfigured: true },
      {
        onNext: () => calls.push("next"),
        onBack: () => calls.push("back"),
        onSkip: () => calls.push("skip"),
        onSetupLater: () => calls.push("later"),
      },
    );
    for (const role of ["onboarding-next", "onboarding-back", "onboarding-skip", "onboarding-later"]) {
      click(guide, role);
    }
    expect(calls.sort()).toEqual(["back", "later", "next", "skip"]);
  });
});

// -- 2. Unified error experience (§2) -----------------------------------------

/** The mapping the spec fixes. Left: what happened. Right: what the user reads. */
const ERROR_TABLE: Array<[string, unknown, string]> = [
  ["401", new BridgeRequestError(401, "provider_http_error", "x"), SAFE_MESSAGES.invalidKey],
  ["403", new BridgeRequestError(403, "provider_http_error", "x"), SAFE_MESSAGES.invalidKey],
  ["429", new BridgeRequestError(429, "provider_http_error", "x"), SAFE_MESSAGES.rateLimited],
  ["500", new BridgeRequestError(500, "provider_http_error", "x"), SAFE_MESSAGES.providerUnavailable],
  ["502", new BridgeRequestError(502, "provider_http_error", "x"), SAFE_MESSAGES.providerUnavailable],
  ["503", new BridgeRequestError(503, "provider_http_error", "x"), SAFE_MESSAGES.providerUnavailable],
  ["network", new BridgeUnavailableError("down"), SAFE_MESSAGES.backendUnreachable],
  ["provider unreachable", new BridgeRequestError(502, "provider_unreachable", "x"), SAFE_MESSAGES.backendUnreachable],
  [
    "provider_not_configured (400)",
    new BridgeRequestError(400, "provider_not_configured", "x"),
    SAFE_MESSAGES.notConfigured,
  ],
  [
    "provider_not_configured (422, phase 31 gateway)",
    new BridgeRequestError(422, "provider_not_configured", "x"),
    SAFE_MESSAGES.notConfigured,
  ],
  ["rejected request", new BridgeRequestError(400, "assistant_error", "x"), SAFE_MESSAGES.requestRejected],
];

describe("phase 34 · unified error experience", () => {
  it("maps every documented failure to its fixed sentence", () => {
    for (const [name, error, expected] of ERROR_TABLE) {
      expect(safeErrorMessage(error), name).toBe(expected);
    }
  });

  it("reports a user-stopped stream as Streaming stopped", () => {
    const abort = new DOMException("aborted", "AbortError");
    expect(classifyError(abort).kind).toBe("streaming_stopped");
    expect(safeErrorMessage(abort)).toBe(SAFE_MESSAGES.streamingStopped);
  });

  it("answers with a sentence from the closed vocabulary for anything at all", () => {
    const wild: unknown[] = [
      null,
      undefined,
      "boom",
      new Error("boom"),
      { status: 418 },
      new BridgeRequestError(404, "not_found", "x"),
      Symbol("nope"),
    ];
    for (const error of wild) {
      const message = safeErrorMessage(error);
      expect(isSafeMessage(message)).toBe(true);
    }
  });

  it("leaks no stack trace, path, key, header, DB URL or vendor body", () => {
    const leaky: unknown[] = [
      new Error('Traceback (most recent call last):\n  File "C:\\app\\main.py", line 42, in chat'),
      new Error("at Object.<anonymous> (/srv/bridge/app/service.js:11:3)"),
      new BridgeRequestError(500, "provider_http_error", "openai said sk-live-abcdef0123456789"),
      new BridgeRequestError(500, "provider_http_error", "Authorization: Bearer abcdef0123456789"),
      new BridgeRequestError(500, "provider_http_error", "sqlite:///C:/Users/x/approvals.db"),
      new BridgeRequestError(500, "provider_http_error", "postgres://u:password=hunter2@db/x"),
      { body: { detail: '{"error":{"message":"organization org-123 exceeded"}}' }, status: 500 },
      new Error("<ProviderError object at 0x7f1>"),
    ];
    for (const error of leaky) {
      const message = safeErrorMessage(error);
      expect(isSafeMessage(message)).toBe(true);
      expect(containsForbiddenDetail(message)).toBe(false);
    }
  });

  it("replaces an unsafe status line instead of rendering it", () => {
    // Unsafe text is not merely emptied: it is swapped for a sentence from the
    // closed vocabulary, so the surface never has to decide what to show.
    expect(sanitizeStatusText('File "C:\\app\\main.py", line 42')).toBe(SAFE_MESSAGES.backendUnreachable);
    expect(sanitizeStatusText("Traceback (most recent call last):")).toBe(SAFE_MESSAGES.backendUnreachable);
    expect(sanitizeStatusText(SAFE_MESSAGES.rateLimited)).toBe(SAFE_MESSAGES.rateLimited);
    expect(sanitizeStatusText("")).toBe("");
    const rendered = renderAssistantChat(
      document,
      chatState({ status: "Traceback (most recent call last):" }),
      { onSend: () => {} },
    );
    const status = rendered.querySelector('[data-role="chat-status"]');
    const shown = status?.textContent ?? "";
    expect(containsForbiddenDetail(shown)).toBe(false);
    expect(shown).not.toContain("Traceback");
    expect(isSafeMessage(shown)).toBe(true);
  });

  it("shows a safe sentence when a chat request fails", async () => {
    const { store, controller } = await controllerFor({
      assistantChatStream: vi.fn(async () => {
        throw new BridgeRequestError(429, "provider_http_error", "sk-live-0123456789abcdef");
      }),
    });
    await controller.sendAssistantMessage("hello");
    expect(store.getState().assistantStatus).toBe(SAFE_MESSAGES.rateLimited);
    expect(containsForbiddenDetail(store.getState().assistantStatus)).toBe(false);
  });

  it("shows a safe sentence in Provider Settings (test / save / forget)", async () => {
    const test = await controllerFor({
      providerTest: vi.fn(async () => {
        throw new BridgeUnavailableError("down");
      }),
    });
    await test.controller.testProvider({ provider: "openai", model: "gpt-5", apiKey: "" });
    expect(test.store.getState().assistantStatus).toBe(SAFE_MESSAGES.backendUnreachable);

    const save = await controllerFor({
      providerConfig: vi.fn(async () => {
        throw new BridgeRequestError(500, "provider_http_error", 'File "C:\\app\\main.py", line 42');
      }),
      userSettings: vi.fn(async () => {
        throw new BridgeUnavailableError("down");
      }),
    });
    await save.controller.saveProvider({ provider: "openai", model: "gpt-5", baseUrl: "", apiKey: "sk-test" });
    // Both the failed write and the follow-up refresh stay inside the vocabulary.
    expect(isSafeMessage(save.store.getState().assistantStatus)).toBe(true);
    expect(containsForbiddenDetail(save.store.getState().assistantStatus)).toBe(false);

    const forget = await controllerFor({
      providerForget: vi.fn(async () => {
        throw new BridgeRequestError(401, "provider_http_error", "Authorization: Bearer x");
      }),
      userSettings: vi.fn(async () => {
        throw new BridgeUnavailableError("down");
      }),
    });
    await forget.controller.forgetProviderKey("openai");
    expect(isSafeMessage(forget.store.getState().assistantStatus)).toBe(true);
  });

  it("names an unconfigured provider with the phase 34 sentence", async () => {
    const { store, controller } = await controllerFor({
      assistantChatStream: vi.fn(async () => {
        throw new BridgeRequestError(400, "provider_not_configured", "Assistant stream failed (400)");
      }),
    });
    await controller.sendAssistantMessage("hello");
    expect(store.getState().assistantStatus).toBe("LLM provider is not configured");
  });

  it("ends a mid-stream failure with the safe error frame, not vendor text", async () => {
    const { store, controller } = await controllerFor({
      assistantChatStream: streamMock([
        { type: "delta", content: "partial " },
        { type: "error", content: SAFE_MESSAGES.providerUnavailable },
      ]),
    });
    await controller.sendAssistantMessage("hello");
    const state = store.getState();
    expect(state.assistantStreaming).toBe(false);
    expect(state.assistantStatus).toBe(SAFE_MESSAGES.providerUnavailable);
    const turns = state.assistantConversations[0].turns;
    expect(turns[1].failed).toBe(true);
    expect(turns[1].content).toBe("partial ");
  });

  it("replaces an out-of-vocabulary error frame rather than displaying it", async () => {
    const { store, controller } = await controllerFor({
      assistantChatStream: streamMock([
        { type: "error", content: 'File "C:\\app\\main.py", line 42: sk-live-0123456789' },
      ]),
    });
    await controller.sendAssistantMessage("hello");
    const status = store.getState().assistantStatus;
    expect(status).toBe(SAFE_MESSAGES.providerUnavailable);
    expect(containsForbiddenDetail(status)).toBe(false);
  });
});

// -- 3. Chat UX refinement (§3) -----------------------------------------------

function pressEnter(input: HTMLTextAreaElement, shift = false): void {
  input.dispatchEvent(
    new window.KeyboardEvent("keydown", { key: "Enter", shiftKey: shift, bubbles: true, cancelable: true }),
  );
}

describe("phase 34 · chat ux", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("sends on Enter and inserts a newline on Shift+Enter", () => {
    const sent: string[] = [];
    const root = renderAssistantChat(document, chatState(), { onSend: (text) => sent.push(text) });
    const input = root.querySelector<HTMLTextAreaElement>('[data-role="chat-input"]')!;

    input.value = "first question";
    pressEnter(input);
    expect(sent).toEqual(["first question"]);
    // The composer is emptied by the send, not by the keypress alone.
    expect(input.value).toBe("");

    input.value = "line one";
    pressEnter(input, true);
    // Shift+Enter is left to the textarea: no send, and the text is untouched.
    expect(sent).toEqual(["first question"]);
    expect(input.value).toBe("line one");
  });

  it("does not send an empty composer or an IME composition", () => {
    const sent: string[] = [];
    const root = renderAssistantChat(document, chatState(), { onSend: (text) => sent.push(text) });
    const input = root.querySelector<HTMLTextAreaElement>('[data-role="chat-input"]')!;

    input.value = "   ";
    pressEnter(input);
    input.value = "";
    pressEnter(input);
    input.value = "日本語";
    input.dispatchEvent(
      new window.KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true, cancelable: true }),
    );
    expect(sent).toEqual([]);
  });

  it("grows the composer only up to the documented maximum", () => {
    const root = renderAssistantChat(document, chatState(), { onSend: () => {} });
    const input = root.querySelector<HTMLTextAreaElement>('[data-role="chat-input"]')!;
    expect(input.style.maxHeight).toBe(`${MAX_COMPOSER_HEIGHT}px`);

    // jsdom reports no layout, so scrollHeight is stubbed to drive the clamp.
    Object.defineProperty(input, "scrollHeight", { value: 40, configurable: true });
    autoGrowComposer(input);
    expect(input.style.height).toBe("40px");
    expect(input.style.overflowY).toBe("hidden");

    Object.defineProperty(input, "scrollHeight", { value: MAX_COMPOSER_HEIGHT + 500, configurable: true });
    autoGrowComposer(input);
    expect(input.style.height).toBe(`${MAX_COMPOSER_HEIGHT}px`);
    // Past the cap the composer scrolls instead of pushing the transcript away.
    expect(input.style.overflowY).toBe("auto");
  });

  it("shows a loading state and a Stop button only while streaming", () => {
    const idle = renderAssistantChat(document, chatState(), { onSend: () => {} });
    expect(idle.querySelector('[data-role="chat-loading"]')).toBeNull();
    expect(idle.querySelector('[data-role="chat-stop"]')).toBeNull();

    const busy = renderAssistantChat(document, chatState({ streaming: true }), { onSend: () => {} });
    expect(busy.querySelector('[data-role="chat-loading"]')?.textContent).toBe("Loading…");
    expect(busy.querySelector('[data-role="chat-stop"]')).not.toBeNull();
    expect(busy.querySelector<HTMLButtonElement>('[data-role="chat-send"]')!.disabled).toBe(true);
    // Retry is never offered while a stream is running.
    expect(busy.querySelector('[data-role="chat-retry"]')).toBeNull();
  });

  it("keeps the received answer when the user stops the stream", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.appendAssistantTurn(turn({ id: "t_u", role: "user", content: "hello" }));
    await store.appendAssistantTurn(turn({ id: "t_a", content: "half an ans", streaming: true }));
    await store.setAssistantStreaming(true);

    const stopped = await store.stopAssistantStreaming();
    expect(stopped.assistantStreaming).toBe(false);
    expect(stopped.assistantStatus).toBe(SAFE_MESSAGES.streamingStopped);
    const turns = stopped.assistantConversations[0].turns;
    expect(turns.map((item) => item.content)).toEqual(["hello", "half an ans"]);
    expect(turns[1].streaming).toBe(false);
    expect(turns[1].stopped).toBe(true);
  });

  it("aborts the request on Stop and never resumes it", async () => {
    const seen: { signal: AbortSignal | null } = { signal: null };
    let started: () => void = () => {};
    const streaming = new Promise<void>((resolve) => {
      started = resolve;
    });
    const stream = vi.fn(
      (
        _body: unknown,
        options: { onEvent: (event: AssistantStreamEvent) => void; signal?: AbortSignal },
      ) =>
        new Promise<void>((resolve) => {
          seen.signal = options.signal ?? null;
          options.onEvent({
            type: "delta",
            content: "half",
            toolCall: null,
            provider: "openai",
            model: "gpt-5",
          });
          options.signal?.addEventListener("abort", () => resolve());
          started();
        }),
    );
    const { store, controller } = await controllerFor({ assistantChatStream: stream });
    const inflight = controller.sendAssistantMessage("hello");
    // Wait until the request is actually in flight before pressing Stop.
    await streaming;
    await controller.stopAssistant();
    await inflight;

    expect(seen.signal?.aborted).toBe(true);
    const state = store.getState();
    expect(state.assistantStreaming).toBe(false);
    expect(state.assistantStatus).toBe(SAFE_MESSAGES.streamingStopped);
    // Exactly one provider call: stopping does not re-send.
    expect(stream).toHaveBeenCalledTimes(1);
    expect(state.assistantConversations[0].turns[1].content).toBe("half");
    expect(state.assistantConversations[0].turns[1].stopped).toBe(true);
  });

  it("offers Retry after a failure and re-sends only on the click", async () => {
    const stream = vi
      .fn()
      .mockImplementationOnce(async () => {
        throw new BridgeRequestError(500, "provider_http_error", "boom");
      })
      .mockImplementationOnce(
        async (
          _body: unknown,
          options: { onEvent: (event: AssistantStreamEvent) => void },
        ) => {
          options.onEvent({
            type: "delta",
            content: "second answer",
            toolCall: null,
            provider: "openai",
            model: "gpt-5",
          });
        },
      );
    const { store, controller } = await controllerFor({ assistantChatStream: stream });

    await controller.sendAssistantMessage("explain retries");
    let state = store.getState();
    expect(stream).toHaveBeenCalledTimes(1);
    expect(state.assistantStatus).toBe(SAFE_MESSAGES.providerUnavailable);
    // The question is handed back instead of being dropped.
    expect(state.assistantDraft).toBe("explain retries");
    const failedTurns = state.assistantConversations[0].turns;
    expect(failedTurns).toHaveLength(2);
    expect(failedTurns[1].failed).toBe(true);
    // No timer, no automatic provider retry: still exactly one call.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(stream).toHaveBeenCalledTimes(1);

    await controller.retryAssistant();
    state = store.getState();
    expect(stream).toHaveBeenCalledTimes(2);
    const turns = state.assistantConversations[0].turns;
    // The user message exists exactly once: Retry reuses it, never duplicates it.
    expect(turns.filter((item) => item.role === "user" && item.content === "explain retries")).toHaveLength(1);
    expect(turns[turns.length - 1].content).toBe("second answer");
    expect(state.assistantStreaming).toBe(false);
    expect(state.assistantStatus).toBe("");
  });

  it("renders Retry from the failed tail and wires it to the handler", () => {
    let retried = 0;
    const failed = chatState({
      conversations: [conversation({ turns: [turn({ role: "user", content: "hi" }), turn({ id: "t2", failed: true })] })],
      status: SAFE_MESSAGES.providerUnavailable,
      canRetry: true,
      draft: "hi",
    });
    const root = renderAssistantChat(document, failed, { onSend: () => {}, onRetry: () => (retried += 1) });
    expect(root.querySelector<HTMLTextAreaElement>('[data-role="chat-input"]')!.value).toBe("hi");
    click(root, "chat-retry");
    expect(retried).toBe(1);
  });

  it("returns the streaming state to idle after a failure and after a stop", async () => {
    const failing = await controllerFor({
      assistantChatStream: vi.fn(async () => {
        throw new BridgeUnavailableError("down");
      }),
    });
    await failing.controller.sendAssistantMessage("hello");
    expect(failing.store.getState().assistantStreaming).toBe(false);

    const store = new ExtensionStore(memoryStorage());
    await store.setAssistantStreaming(true);
    expect((await store.stopAssistantStreaming()).assistantStreaming).toBe(false);
    await store.setAssistantStreaming(true);
    expect((await store.failAssistantStreaming(SAFE_MESSAGES.rateLimited)).assistantStreaming).toBe(false);
  });

  it("retries nothing when there is no failed message or a stream is running", async () => {
    const empty = await controllerFor({});
    await empty.controller.retryAssistant();
    // The Bridge proxy throws on any unmocked call, so a hidden send would fail.
    expect(empty.store.getState().assistantConversations).toEqual([]);

    const busy = await controllerFor({}, { assistantStreaming: true });
    await busy.controller.retryAssistant();
    expect(busy.store.getState().assistantStreaming).toBe(true);
  });
});

// -- 4. Conversation management (§4) -------------------------------------------

describe("phase 34 · conversation management", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("starts a new conversation locally and selects it", async () => {
    const store = new ExtensionStore(memoryStorage());
    const first = await store.newAssistantConversation();
    const firstId = first.assistantActiveConversation;
    const second = await store.newAssistantConversation();
    expect(second.assistantConversations).toHaveLength(2);
    expect(second.assistantActiveConversation).not.toBe(firstId);
    // Local-only rows: the Bridge is never asked to create anything.
    expect(second.assistantConversations.every((item) => item.localOnly)).toBe(true);
  });

  it("filters by title and by message text without deleting anything", () => {
    const list: AssistantConversationView[] = [
      conversation({ id: "a", title: "Rate limiting" }),
      conversation({ id: "b", title: "Untitled", turns: [turn({ content: "how do I paginate?" })] }),
      conversation({ id: "c", title: "Deployment" }),
    ];
    expect(visibleAssistantConversations(list, "rate").map((item) => item.id)).toEqual(["a"]);
    expect(visibleAssistantConversations(list, "paginate").map((item) => item.id)).toEqual(["b"]);
    expect(visibleAssistantConversations(list, "RATE").map((item) => item.id)).toEqual(["a"]);
    expect(visibleAssistantConversations(list, "nothing-matches")).toEqual([]);
    // The list itself is untouched by a search.
    expect(list).toHaveLength(3);
    expect(visibleAssistantConversations(list, "").map((item) => item.id)).toEqual(["c", "b", "a"]);
  });

  it("keeps pinned conversations on top and unpins again", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.update({
      assistantConversations: [conversation({ id: "a", title: "A" }), conversation({ id: "b", title: "B" })],
      assistantActiveConversation: "a",
    });
    const pinned = await store.toggleAssistantConversationPinned("a");
    expect(pinned.assistantConversations.find((item) => item.id === "a")?.pinned).toBe(true);
    expect(visibleAssistantConversations(pinned.assistantConversations, "").map((item) => item.id)).toEqual(["a", "b"]);
    const unpinned = await store.toggleAssistantConversationPinned("a");
    expect(unpinned.assistantConversations.find((item) => item.id === "a")?.pinned).toBeFalsy();
    expect(visibleAssistantConversations(unpinned.assistantConversations, "").map((item) => item.id)).toEqual(["b", "a"]);
  });

  it("renames in this view only and keeps the old name for a blank input", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.update({
      assistantConversations: [conversation({ id: "a", title: "Old name" })],
      assistantActiveConversation: "a",
    });
    const renamed = await store.renameAssistantConversation("a", "  Token buckets  ");
    expect(renamed.assistantConversations[0].title).toBe("Token buckets");
    expect(renamed.assistantConversations[0].renamed).toBe(true);
    const blank = await store.renameAssistantConversation("a", "   ");
    expect(blank.assistantConversations[0].title).toBe("Token buckets");
    // A rename never re-titles itself from the next message.
    await store.appendAssistantTurn(turn({ role: "user", content: "another question entirely" }));
    expect(store.getState().assistantConversations[0].title).toBe("Token buckets");
  });

  it("opens and closes the rename box without touching the title", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.update({ assistantConversations: [conversation({ id: "a", title: "Keep me" })] });
    expect((await store.beginRenameConversation("a")).assistantRenaming).toBe("a");
    const cancelled = await store.cancelRenameConversation();
    expect(cancelled.assistantRenaming).toBeNull();
    expect(cancelled.assistantConversations[0].title).toBe("Keep me");
  });

  it("removes a conversation from the view and re-points the active one", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.update({
      assistantConversations: [conversation({ id: "a" }), conversation({ id: "b" })],
      assistantActiveConversation: "a",
      assistantRenaming: "a",
      assistantStatus: SAFE_MESSAGES.rateLimited,
    });
    const state = await store.removeAssistantConversation("a");
    expect(state.assistantConversations.map((item) => item.id)).toEqual(["b"]);
    // No frozen UI: the view moves to a surviving conversation.
    expect(state.assistantActiveConversation).toBe("b");
    expect(state.assistantRenaming).toBeNull();

    const emptied = await store.removeAssistantConversation("b");
    expect(emptied.assistantConversations).toEqual([]);
    expect(emptied.assistantActiveConversation).toBeNull();
    // The transcript renders an empty view rather than throwing.
    const root = renderAssistantChat(
      document,
      chatState({ conversations: [], activeConversation: null }),
      { onSend: () => {} },
    );
    expect(root.querySelector('[data-role="history-empty"]')).not.toBeNull();
  });

  it("ignores an unknown conversation id everywhere", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.update({
      assistantConversations: [conversation({ id: "a", title: "A" })],
      assistantActiveConversation: "a",
    });
    await store.selectAssistantConversation("does_not_exist");
    expect(store.getState().assistantActiveConversation).toBe("a");
    await store.removeAssistantConversation("does_not_exist");
    await store.renameAssistantConversation("does_not_exist", "ghost");
    await store.toggleAssistantConversationPinned("does_not_exist");
    const state = store.getState();
    expect(state.assistantConversations).toHaveLength(1);
    expect(state.assistantConversations[0].title).toBe("A");
  });

  it("boots chat even when the stored blob is corrupt or unreadable", async () => {
    // A truncated JSON string under the state key: not an object, so it is ignored.
    const corrupt = new ExtensionStore(memoryStorage({ [STORAGE_KEY]: '{"assistantConversations":[{"id":' }));
    const state = await corrupt.hydrate();
    expect(state.assistantConversations).toEqual([]);
    expect(state.assistantActiveConversation).toBeNull();
    expect(state.onboardingState).toBe("new");

    const throwing = new ExtensionStore({
      async get() {
        throw new Error("storage unavailable");
      },
      async set() {},
    });
    const recovered = await throwing.hydrate();
    expect(recovered.assistantConversations).toEqual([]);
    // The panel still renders with the recovered state.
    const container = mountPanel(recovered);
    expect(container.querySelector('[data-role="assistant-chat"]')).not.toBeNull();
  });

  it("survives a stored blob whose conversation rows are malformed", async () => {
    const store = new ExtensionStore(
      memoryStorage({
        [STORAGE_KEY]: {
          assistantConversations: [{ id: "a", title: "A", createdAt: "", turns: null, localOnly: true }],
          assistantActiveConversation: "missing",
        },
      }),
    );
    const state = await store.hydrate();
    const container = mountPanel(state);
    // A row with no turns array and an active id that is not in the list must
    // not break the transcript.
    expect(container.querySelector('[data-role="chat-transcript"]')).not.toBeNull();
  });

  it("manages conversations with no Bridge call at all", async () => {
    const { store, controller, touched } = await controllerFor({});
    await controller.newConversation();
    const id = store.getState().assistantActiveConversation!;
    await controller.searchConversations("rate");
    await controller.beginRenameConversation(id);
    await controller.renameConversation(id, "Local only");
    await controller.cancelRenameConversation();
    await controller.toggleConversationPinned(id);
    await controller.selectConversation(id);
    await controller.removeConversation(id);
    // Nothing above may reach the Bridge: no delete, no storage write, no LLM call.
    expect(touched.filter((name) => name !== "then")).toEqual([]);
    expect(store.getState().assistantConversations).toEqual([]);
  });

  it("bounds the search query and the rename length", async () => {
    const store = new ExtensionStore(memoryStorage());
    const long = await store.setAssistantConversationQuery("x".repeat(500));
    expect(long.assistantConversationQuery.length).toBe(120);
    const root = renderAssistantChat(document, chatState({ renaming: "local_1" }), { onSend: () => {} });
    const field = root.querySelector<HTMLInputElement>('[data-role="rename-input"]')!;
    expect(field.maxLength).toBe(80);
  });
});

// -- 5. Context preview & control (§5) -----------------------------------------

function contextPanel(patch: Partial<ExtensionState> = {}): HTMLElement {
  return mountPanel({
    currentProject: "demo",
    assistantProvider: "openai",
    assistantModel: "gpt-5",
    onboardingState: "done",
    ...patch,
  });
}

describe("phase 34 · context preview and control", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows project, agent, read-only status, source, page and selection", () => {
    const container = contextPanel({ assistantWebContext: bundle(), assistantContextInclude: true });
    const panel = container.querySelector('[data-role="context-bundle"]')!;
    expect(panel.getAttribute("data-include")).toBe("true");
    expect(panel.querySelector('[data-role="context-readonly"]')?.textContent).toBe("READ ONLY");
    expect(panel.querySelector('[data-role="context-project"]')?.textContent).toContain("demo");
    expect(panel.querySelector('[data-role="context-agent"]')?.textContent).toContain("openai");
    expect(panel.querySelector('[data-role="context-agent"]')?.textContent).toContain("gpt-5");
    expect(panel.querySelector('[data-role="context-status"]')?.textContent).toContain("Read-only");
    expect(panel.querySelector('[data-role="context-source"]')?.textContent).toContain("Ask AI");
    expect(panel.querySelector('[data-role="context-page-title"]')?.textContent).toContain(
      "Rate limiting in FastAPI",
    );
    const selected = panel.querySelector('[data-role="context-selected-summary"]')?.textContent ?? "";
    expect(selected).toContain("How do I add a token bucket?");
  });

  it("previews exactly the text that would be injected", () => {
    const captured = bundle();
    const container = contextPanel({ assistantWebContext: captured });
    const preview = container.querySelector('[data-role="context-injected-preview"]')!;
    const injected = injectedContextText(captured);
    expect(preview.textContent).toBe(injected);
    // The preview is the payload, not a paraphrase of it.
    expect(injected).toContain(captured.page_title);
    expect(injected).toContain(captured.selected_text);
    expect(injected).toContain(captured.readable_content);
  });

  it("says nothing would be sent before Ask AI is clicked", () => {
    const container = contextPanel();
    const panel = container.querySelector('[data-role="context-bundle"]')!;
    expect(panel.getAttribute("data-include")).toBe("false");
    expect(panel.querySelector('[data-role="context-injected-preview"]')?.textContent).toContain(
      "Nothing would be sent",
    );
    expect(panel.querySelector('[data-role="context-decision"]')?.textContent).toContain(
      "No context is attached",
    );
    // No capture happened, so there is nothing to exclude yet.
    expect(panel.querySelector('[data-role="toggle-context-include"]')).toBeNull();
    expect(injectedContextText(null)).toBe("");
  });

  it("captures only on the Ask AI click and does not send it", async () => {
    const { store, controller, touched } = await controllerFor({});
    const captured = bundle();
    await controller.askAi(captured);
    const state = store.getState();
    expect(state.assistantWebContext).toEqual(captured);
    expect(state.assistantContextInclude).toBe(true);
    expect(state.assistantStatus).toContain("sent only with your next message");
    // Capturing reaches no Bridge method: no upload, no LLM request.
    expect(touched.filter((name) => name !== "then")).toEqual([]);
  });

  it("attaches the bundle only when the user leaves the switch on", async () => {
    const stream = streamMock([{ content: "ok" }]);
    const on = await controllerFor({ assistantChatStream: stream });
    await on.controller.askAi(bundle());
    await on.controller.sendAssistantMessage("with context");
    expect((stream.mock.calls[0][0] as { web_context: unknown }).web_context).toEqual(bundle());

    const off = streamMock([{ content: "ok" }]);
    const excluded = await controllerFor({ assistantChatStream: off });
    await excluded.controller.askAi(bundle());
    await excluded.controller.toggleContextInclude(false);
    await excluded.controller.sendAssistantMessage("without context");
    // Excluded means the payload carries nothing, while the preview stays.
    expect((off.mock.calls[0][0] as { web_context: unknown }).web_context).toBeNull();
    expect(excluded.store.getState().assistantWebContext).not.toBeNull();
  });

  it("removes the captured context on request", async () => {
    const { store, controller } = await controllerFor({});
    await controller.askAi(bundle());
    await controller.clearWebContext();
    expect(store.getState().assistantWebContext).toBeNull();
    const container = contextPanel({ assistantWebContext: bundle() });
    expect(container.querySelector('[data-role="clear-context"]')).not.toBeNull();
  });

  it("drops the bundle after one successful send and keeps it after a failure", async () => {
    const ok = await controllerFor({ assistantChatStream: streamMock([{ content: "ok" }]) });
    await ok.controller.askAi(bundle());
    await ok.controller.sendAssistantMessage("q");
    // Used once, then forgotten — a later message re-uses nothing.
    expect(ok.store.getState().assistantWebContext).toBeNull();

    const bad = await controllerFor({
      assistantChatStream: vi.fn(async () => {
        throw new BridgeUnavailableError("down");
      }),
    });
    await bad.controller.askAi(bundle());
    await bad.controller.sendAssistantMessage("q");
    // Retry reuses the already-approved capture instead of re-reading the page.
    expect(bad.store.getState().assistantWebContext).not.toBeNull();
  });

  it("never persists the captured page or re-collects it on reload", async () => {
    const storage = memoryStorage();
    const store = new ExtensionStore(storage);
    await store.setAssistantWebContext(bundle());
    const persisted = JSON.stringify(storage.data.get(STORAGE_KEY) ?? {});
    expect(TRANSIENT_STATE_KEYS).toContain("assistantWebContext");
    expect(persisted).not.toContain("Rate limiting in FastAPI");
    expect(persisted).not.toContain("token bucket");
    expect((await new ExtensionStore(storage).hydrate()).assistantWebContext).toBeNull();
  });

  it("collects nothing on a refresh or a background tick", async () => {
    const { store, controller, touched } = await controllerFor({
      approvals: vi.fn(async () => []),
      context: vi.fn(async () => null),
      projectContext: vi.fn(async () => null),
      contextStatus: vi.fn(async () => null),
    });
    await controller.refreshContext();
    expect(store.getState().assistantWebContext).toBeNull();
    // Refreshing reads project context only; the page is never touched.
    expect(touched).not.toContain("assistantChatStream");
  });

  it("sends no message and no context until the user submits", async () => {
    const stream = streamMock([{ content: "ok" }]);
    const { controller } = await controllerFor({ assistantChatStream: stream });
    await controller.askAi(bundle());
    await controller.toggleContextInclude(true);
    await controller.toggleContextInclude(false);
    await controller.toggleContextInclude(true);
    // Capture, preview and the include decision are all free of provider calls.
    expect(stream).not.toHaveBeenCalled();
  });
});

// -- 6. Security acceptance (§8.6) --------------------------------------------

describe("phase 34 · security acceptance", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("offers no execute / approve / apply / auto-fix / shell control in User Mode", () => {
    const container = mountPanel({
      onboardingState: "done",
      currentProject: "demo",
      assistantProviders: [providerEntry()],
      assistantWebContext: bundle(),
      assistantConversations: [conversation({ turns: [turn({ role: "user", content: "hi" }), turn()] })],
      assistantActiveConversation: "local_1",
      pendingActions: [
        {
          id: "req_1",
          state: "pending",
          createdAt: "2026-01-01T00:00:00Z",
          fingerprint: "fp_1",
          preview: "WRITE src/app.py",
          action: {
            version: "1.0",
            action: "file.write",
            target: { project: "demo", path: "src/app.py" },
            reason: "phase 34 fixture",
            risk: "medium",
            payload: { content: "x = 1\n" },
            requiresApproval: true,
          },
        },
      ],
    });
    for (const label of buttonLabels(container)) {
      expect(label, label).not.toMatch(FORBIDDEN_CONTROL);
    }
    // A pending approval is a count, never an actionable control here.
    expect(container.querySelector('[data-role="approval-hint"]')).not.toBeNull();
    expect(container.querySelector('[data-role="approve-action"]')).toBeNull();
  });

  it("keeps the forbidden surfaces permanently unavailable", () => {
    expect([...NEVER_AVAILABLE].sort()).toEqual(
      ["apply_patch", "approve_from_chat", "auto_approve", "auto_fix", "execute", "shell"].sort(),
    );
    for (const surface of NEVER_AVAILABLE) {
      expect(USER_MODE_SURFACES).not.toContain(surface);
    }
  });

  it("renders a tool call as an inert proposal, and not at all in User Mode", () => {
    const proposal = turn({
      id: "t_tool",
      content: "Here is a patch proposal.",
      toolCalls: [{ name: "write_file", arguments: '{"path":"src/app.py"}', callId: "call_1" }],
    });
    const conversations = [conversation({ turns: [proposal] })];

    // §6 · tool proposals stay a Developer Mode surface.
    const user = renderAssistantChat(document, chatState({ uiMode: "user", conversations }), {
      onSend: () => {},
    });
    expect(user.querySelector('[data-role="tool-proposal"]')).toBeNull();

    const developer = renderAssistantChat(document, chatState({ uiMode: "developer", conversations }), {
      onSend: () => {},
    });
    const card = developer.querySelector('[data-role="tool-proposal"]');
    expect(card).not.toBeNull();
    // Present but inert: a proposal card carries no way to run it.
    expect(card?.querySelector("button")).toBeNull();
    for (const root of [user, developer]) {
      for (const label of buttonLabels(root)) {
        expect(label, label).not.toMatch(FORBIDDEN_CONTROL);
      }
    }
  });

  it("stores no credential-shaped value, however it is submitted", async () => {
    const storage = memoryStorage();
    const store = new ExtensionStore(storage);
    await store.update({
      apiKey: "sk-live-0123456789abcdef",
      authorization: "Bearer abcdef",
      providerSecret: "shhh",
      access_token: "tok",
    } as unknown as Partial<ExtensionState>);
    const persisted = JSON.stringify(storage.data.get(STORAGE_KEY) ?? {});
    for (const fragment of ["sk-live", "Bearer", "shhh", "access_token", "apiKey"]) {
      expect(persisted, fragment).not.toContain(fragment);
    }
    for (const key of ["apiKey", "api_key", "authorization", "providerSecret", "access_token", "password"]) {
      expect(isForbiddenStateKey(key), key).toBe(true);
    }
  });

  it("carries no key in the onboarding or provider display state", async () => {
    const store = new ExtensionStore(memoryStorage());
    await store.advanceOnboarding();
    await store.update({ assistantProviders: [providerEntry()] });
    const serialized = JSON.stringify(store.getState());
    expect(serialized).not.toContain("sk-");
    // Only a hint and a fingerprint are ever held, never key material.
    expect(store.getState().assistantProviders[0].keyHint).toBe("****cdef");
    for (const settled of ONBOARDING_SETTLED_STATES) {
      expect(String(settled)).not.toMatch(/key|secret|token/i);
    }
  });

  it("proposes without executing: no send path can approve or apply anything", async () => {
    const stream = streamMock([
      {
        content: "I can draft this change.",
        toolCall: { name: "write_file", arguments: '{"path":"src/app.py"}', callId: "call_1" },
      },
    ]);
    const { store, controller, touched } = await controllerFor({ assistantChatStream: stream });
    await controller.sendAssistantMessage("change the file");
    const turns = store.getState().assistantConversations[0].turns;
    expect(turns[1].toolCalls).toHaveLength(1);
    expect(store.getState().assistantStatus).toBe("Tool proposal waiting for approval.");
    // The chat path touches no approval, patch or execution endpoint.
    for (const name of touched) {
      expect(name, name).not.toMatch(/approve|reject|execute|patch|apply|shell/i);
    }
  });
});

// -- 7. UI / state regression (§7) --------------------------------------------

describe("phase 34 · ui and state regression", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("lands a brand-new user on Chat, with no developer surface", () => {
    const container = mountPanel();
    const surface = container.querySelector<HTMLElement>('[data-role="assistant-surface"]')!;
    expect(surface.dataset.mode).toBe("user");
    expect(container.querySelector('[data-role="assistant-chat"]')).not.toBeNull();
    expect(container.querySelector('[data-role="developer-surface"]')).toBeNull();
    // The five User Mode surfaces are all present on that first screen.
    expect(container.querySelector('[data-role="chat-history"]')).not.toBeNull();
    expect(container.querySelector('[data-role="context-bundle"]')).not.toBeNull();
    expect(container.querySelector('[data-role="ask-ai"]')).not.toBeNull();
    expect(USER_MODE_SURFACES).toContain("chat");
  });

  it("keeps the Developer Mode surfaces reachable and free of forbidden controls", () => {
    const container = mountPanel({ uiMode: "developer", onboardingState: "done", currentProject: "demo" });
    const developer = container.querySelector('[data-role="developer-surface"]');
    expect(developer).not.toBeNull();
    // Phase 33's read-only dashboards are untouched, and Chat stays available.
    expect(container.querySelector('[data-role="assistant-chat"]')).not.toBeNull();
    expect([...DEVELOPER_ONLY_SURFACES]).toEqual([
      "project_context",
      "code_context",
      "tool_proposal",
      "engineering_graph",
    ]);
    for (const label of buttonLabels(developer!)) {
      expect(label, label).not.toMatch(/execute|auto ?fix|auto ?approve|shell|terminal|apply/i);
    }
  });

  it("switches mode without disturbing any other state", async () => {
    const { store, controller } = await controllerFor(
      {},
      {
        onboardingState: "later",
        onboardingStep: 2,
        assistantProvider: "openai",
        assistantModel: "gpt-5",
        assistantConversations: [conversation({ id: "a" }), conversation({ id: "b" })],
        assistantActiveConversation: "b",
        assistantWebContext: bundle(),
        assistantContextInclude: false,
      },
    );
    await controller.setUiMode("developer");
    const state = store.getState();
    expect(state.uiMode).toBe("developer");
    expect(state.onboardingState).toBe("later");
    expect(state.onboardingStep).toBe(2);
    expect(state.assistantProvider).toBe("openai");
    expect(state.assistantModel).toBe("gpt-5");
    expect(state.assistantActiveConversation).toBe("b");
    expect(state.assistantStreaming).toBe(false);
    expect(state.assistantWebContext).not.toBeNull();
    expect(state.assistantContextInclude).toBe(false);
    // And back again: the toggle is symmetric and equally inert.
    await controller.setUiMode("user");
    expect(store.getState().uiMode).toBe("user");
    expect(store.getState().assistantActiveConversation).toBe("b");
  });

  it("restores mode, onboarding and selections on reload, but never transient state", async () => {
    const storage = memoryStorage();
    const first = new ExtensionStore(storage);
    await first.update({
      uiMode: "developer",
      onboardingState: "done",
      assistantProvider: "openai",
      assistantModel: "gpt-5",
      assistantConversations: [conversation({ id: "a" })],
      assistantActiveConversation: "a",
      assistantStreaming: true,
      assistantDraft: "half-typed question",
      assistantWebContext: bundle(),
      assistantConversationQuery: "buckets",
    });

    const reloaded = await new ExtensionStore(storage).hydrate();
    expect(reloaded.uiMode).toBe("developer");
    expect(reloaded.onboardingState).toBe("done");
    expect(reloaded.assistantProvider).toBe("openai");
    expect(reloaded.assistantModel).toBe("gpt-5");
    expect(reloaded.assistantActiveConversation).toBe("a");
    // No resurrected stream, no resurrected capture, no resurrected draft.
    expect(reloaded.assistantStreaming).toBe(false);
    expect(reloaded.assistantDraft).toBe("");
    expect(reloaded.assistantWebContext).toBeNull();
    expect(reloaded.assistantConversationQuery).toBe("");
    expect(reloaded.assistantRenaming).toBeNull();
  });

  it("renders the panel in every onboarding state", () => {
    for (const onboardingState of ["new", "active", "done", "skipped", "later"] as const) {
      const container = mountPanel({ onboardingState, currentProject: "demo" });
      expect(container.querySelector('[data-role="assistant-chat"]'), onboardingState).not.toBeNull();
      for (const label of buttonLabels(container)) {
        expect(label, `${onboardingState}: ${label}`).not.toMatch(FORBIDDEN_CONTROL);
      }
    }
  });

  it("issues no request while a failed turn and an error status are on screen", async () => {
    const { store, touched } = await controllerFor({}, {
      assistantStatus: SAFE_MESSAGES.providerUnavailable,
      assistantConversations: [
        conversation({ turns: [turn({ role: "user", content: "hi" }), turn({ failed: true })] }),
      ],
      assistantActiveConversation: "local_1",
    });
    const container = mountPanel(store.getState());
    // Retry is offered, but only a click runs it.
    expect(container.querySelector('[data-role="chat-retry"]')).not.toBeNull();
    await new Promise((resolve) => setTimeout(resolve, 20));
    // Rendering a failure is not an event: nothing retries and nothing is sent.
    expect(touched.filter((name) => name !== "then")).toEqual([]);
    const shown = container.querySelector('[data-role="chat-status"]')?.textContent ?? "";
    expect(isSafeMessage(shown)).toBe(true);
  });
});
