/**
 * Phase 32 · AI Assistant types (extension side).
 *
 * These mirror the Bridge payloads of `/user/settings`, `/provider/status`,
 * `/provider/test`, `/context/status` and `/assistant/chat`.
 *
 * There is deliberately **no** api-key field anywhere in this module: the key
 * only ever exists as the transient value of a Settings input element and is
 * posted straight to the Bridge, which encrypts it (AES-256-GCM). It is never
 * part of `ExtensionState` and therefore never reaches `chrome.storage`.
 */

/** User Mode is the default; Developer Mode only adds read-only surfaces. */
export type UiMode = "user" | "developer";

/** Surfaces User Mode may render (spec §2). */
export const USER_MODE_SURFACES = [
  "chat",
  "model_selector",
  "context",
  "history",
  "settings",
] as const;

/** Extra surfaces Developer Mode may render — read-only, still no execution. */
export const DEVELOPER_ONLY_SURFACES = [
  "project_context",
  "code_context",
  "tool_proposal",
  "engineering_graph",
] as const;

/** Capabilities no mode may ever expose (mirrors service.NEVER_AVAILABLE). */
export const NEVER_AVAILABLE = [
  "execute",
  "approve_from_chat",
  "apply_patch",
  "auto_fix",
  "auto_approve",
  "shell",
] as const;

export type ProviderConnectionStatus = "connected" | "not_configured" | "failed";

export interface AssistantProviderEntry {
  provider: string;
  displayName: string;
  status: ProviderConnectionStatus;
  requiresApiKey: boolean;
  keyEnv: string;
  hasStoredKey: boolean;
  /** Masked tail only, e.g. `****cdef`. Never the key itself. */
  keyHint: string;
  keyFingerprint: string;
  baseUrl: string;
  selectedModel: string;
  lastTestedAt: string;
  models: string[];
}

export interface AssistantUserSettings {
  mode: UiMode;
  provider: string;
  model: string;
  baseUrl: string;
  preferences: Record<string, string>;
  surfaces: string[];
  neverAvailable: string[];
  providers: Array<Pick<AssistantProviderEntry, "provider" | "status" | "hasStoredKey" | "models">>;
  keyStorage: { algorithm: string; available: boolean; location: string };
  readOnly: true;
}

export interface ProviderTestResult {
  provider: string;
  status: ProviderConnectionStatus;
  /** Fixed vocabulary only: Connected / Not configured / Invalid API key / … */
  message: string;
  readOnly: true;
}

export interface AssistantContextStatus {
  scope: UiMode;
  web: {
    requiresExplicitTrigger: true;
    trigger: "ask_ai";
    automaticCapture: false;
    automaticUpload: false;
    fields: string[];
  };
  developerContext: {
    loaded: boolean;
    readOnly: true;
    project?: string;
    sources?: string[];
    endpoint?: string;
    modificationRequiresApproval?: boolean;
  };
  readOnly: true;
}

/** A page snapshot that exists only because the user clicked **Ask AI**. */
export interface WebContextBundle {
  trigger: "ask_ai";
  consented_at: string;
  page_title: string;
  page_url: string;
  selected_text: string;
  readable_content: string;
  timestamp: string;
}

export interface AssistantToolCall {
  name: string;
  arguments: string;
  callId: string;
}

export interface AssistantChatResult {
  reply: string;
  toolCalls: AssistantToolCall[];
  provider: string;
  model: string;
  finishReason: string;
  usage: Record<string, number>;
  simulated: boolean;
  contextIncluded: boolean;
  context: Record<string, unknown> | null;
  /** Always false: the assistant proposes, a human approves. */
  toolCallsExecuted: false;
  requiresApproval: boolean;
  readOnly: true;
}

export type AssistantChatRole = "user" | "assistant";

/** One SSE frame from `/assistant/chat/stream` (mirrors StreamEvent.as_dict). */
export interface AssistantStreamEvent {
  type: string;
  content: string;
  toolCall: AssistantToolCall | null;
  provider: string;
  model: string;
}

export interface AssistantChatTurn {
  id: string;
  role: AssistantChatRole;
  content: string;
  createdAt: string;
  /** True while tokens are still arriving for this turn. */
  streaming?: boolean;
  /** True when the user pressed Stop; no automatic retry ever follows. */
  stopped?: boolean;
  /**
   * Phase 34: the request behind this turn failed. Set together with a safe
   * message so Retry can be offered — the retry itself is always a click.
   */
  failed?: boolean;
  toolCalls?: AssistantToolCall[];
}

/**
 * Conversation kept for the extension's own display only. New Chat / History /
 * Remove from view touch this list exclusively — Phase 31 backend conversation
 * storage is never modified by those buttons.
 */
export interface AssistantConversationView {
  id: string;
  title: string;
  createdAt: string;
  turns: AssistantChatTurn[];
  localOnly: true;
  /**
   * Phase 34 · extension-local display flags. Pinning and renaming reorder and
   * relabel this list only; the Bridge is never told about either.
   */
  pinned?: boolean;
  /** True once the user renamed it, so an auto title never overwrites it. */
  renamed?: boolean;
}

/**
 * Phase 34 · first-run onboarding.
 *
 * The state is a non-sensitive local display marker. It gates *which UI is
 * shown* and nothing else: no permission, no provider configuration and no
 * approval semantics depend on it.
 *
 * - `new`     — never seen; the guide is shown automatically on first launch
 * - `active`  — the user is stepping through it
 * - `later`   — "Setup Later"; Chat is usable, a hint stays available
 * - `skipped` — "Skip"; not shown again
 * - `done`    — all four steps completed
 */
export type OnboardingState = "new" | "active" | "later" | "skipped" | "done";

export const ONBOARDING_STATES = ["new", "active", "later", "skipped", "done"] as const;

/** Onboarding is over for these states; the guide is not rendered again. */
export const ONBOARDING_SETTLED_STATES = ["skipped", "done"] as const;

export type OnboardingStepId = "start_bridge" | "configure_provider" | "test_connection" | "start_chat";

export interface OnboardingStep {
  id: OnboardingStepId;
  title: string;
  detail: string;
}

/** The four steps from the Phase 34 spec, in order. */
export const ONBOARDING_STEPS: readonly OnboardingStep[] = Object.freeze([
  Object.freeze({
    id: "start_bridge" as OnboardingStepId,
    title: "Start Local Bridge",
    detail: "Run: uvicorn app.main:app --port 8765 — the extension talks to 127.0.0.1 only.",
  }),
  Object.freeze({
    id: "configure_provider" as OnboardingStepId,
    title: "Configure Provider",
    detail: "Open Settings and pick a provider. The API key goes to the Bridge and is encrypted there.",
  }),
  Object.freeze({
    id: "test_connection" as OnboardingStepId,
    title: "Test Connection",
    detail: "Use Test connection in Settings. The result is a fixed status word, never a provider response.",
  }),
  Object.freeze({
    id: "start_chat" as OnboardingStepId,
    title: "Start Chat",
    detail: "Ask a question. The assistant explains and drafts; every change stays a proposal.",
  }),
]);

export const ONBOARDING_STEP_COUNT = ONBOARDING_STEPS.length;
