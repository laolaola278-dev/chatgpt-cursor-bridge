/**
 * Phase 32 · Model selector, mode toggle and Provider Settings page.
 *
 * API-key handling (spec §5, the phase's highest-priority rule): the key lives
 * **only** as the transient `value` of the password input below. It is handed to
 * `BridgeClient.providerConfig` / `providerTest` — which POST it to the Bridge for
 * AES-256-GCM encryption — and the input is cleared immediately afterwards. It is
 * never written into `ExtensionState`, never persisted to `chrome.storage`, never
 * put in a URL or query parameter, and never logged.
 */

import type {
  AssistantProviderEntry,
  AssistantUserSettings,
  ProviderConnectionStatus,
  ProviderTestResult,
  UiMode,
} from "./types";

export interface AssistantSettingsHandlers {
  onSelectProvider?: (provider: string) => void;
  onSelectModel?: (model: string) => void;
  /** Receives the transient key; must post it to the Bridge, never store it. */
  onSaveProvider?: (input: { provider: string; model: string; baseUrl: string; apiKey: string }) => void;
  onTestConnection?: (input: { provider: string; model: string; apiKey: string }) => void;
  onForgetKey?: (provider: string) => void;
  onSetMode?: (mode: UiMode) => void;
}

export interface AssistantSettingsViewState {
  uiMode: UiMode;
  provider: string;
  model: string;
  providers: AssistantProviderEntry[];
  settings: AssistantUserSettings | null;
  test: ProviderTestResult | null;
}

const STATUS_LABEL: Record<ProviderConnectionStatus, string> = {
  connected: "Connected",
  not_configured: "Not configured",
  failed: "Failed",
};

export function statusLabel(status: string): string {
  return STATUS_LABEL[status as ProviderConnectionStatus] ?? "Not configured";
}

function findEntry(state: AssistantSettingsViewState): AssistantProviderEntry | null {
  return state.providers.find((entry) => entry.provider === state.provider) ?? state.providers[0] ?? null;
}

function select(doc: Document, role: string, options: string[], current: string): HTMLSelectElement {
  const element = doc.createElement("select");
  element.className = "assistant-select";
  element.dataset.role = role;
  for (const option of options) {
    const item = doc.createElement("option");
    item.value = option;
    item.textContent = option;
    if (option === current) item.selected = true;
    element.appendChild(item);
  }
  return element;
}

function field(doc: Document, label: string, control: HTMLElement): HTMLElement {
  const row = doc.createElement("label");
  row.className = "assistant-field";
  const caption = doc.createElement("span");
  caption.className = "assistant-field-label";
  caption.textContent = label;
  row.append(caption, control);
  return row;
}

/** User Mode surface: pick provider + model, nothing else. */
export function renderModelSelector(
  doc: Document,
  state: AssistantSettingsViewState,
  handlers: AssistantSettingsHandlers,
): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-model-selector";
  root.dataset.role = "model-selector";

  const entry = findEntry(state);
  const providers = state.providers.map((item) => item.provider);
  const providerSelect = select(doc, "provider-select", providers, state.provider);
  providerSelect.addEventListener("change", () => handlers.onSelectProvider?.(providerSelect.value));

  const models = entry?.models ?? [];
  const modelSelect = select(doc, "model-select", models, state.model || entry?.selectedModel || "");
  modelSelect.addEventListener("change", () => handlers.onSelectModel?.(modelSelect.value));

  const status = doc.createElement("span");
  status.className = "assistant-badge";
  status.dataset.role = "provider-status-badge";
  status.textContent = statusLabel(entry?.status ?? "not_configured");

  root.append(field(doc, "Provider", providerSelect), field(doc, "Model", modelSelect), status);
  return root;
}

/** Switches between User Mode and Developer Mode. Both are read-only surfaces. */
export function renderModeToggle(doc: Document, mode: UiMode, handlers: AssistantSettingsHandlers): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-mode-toggle";
  root.dataset.role = "mode-toggle";
  root.dataset.mode = mode;

  const label = doc.createElement("span");
  label.className = "assistant-field-label";
  label.textContent = mode === "developer" ? "Developer Mode" : "User Mode";

  const button = doc.createElement("button");
  button.className = "assistant-mode-button";
  button.dataset.role = "toggle-mode";
  button.type = "button";
  button.textContent = mode === "developer" ? "Switch to User Mode" : "Switch to Developer Mode";
  button.addEventListener("click", () => handlers.onSetMode?.(mode === "developer" ? "user" : "developer"));

  root.append(label, button);
  return root;
}

function renderProviderStatusList(doc: Document, state: AssistantSettingsViewState): HTMLElement {
  const list = doc.createElement("div");
  list.className = "assistant-provider-list";
  list.dataset.role = "provider-status-list";

  for (const entry of state.providers) {
    const row = doc.createElement("div");
    row.className = "assistant-provider-row";
    row.dataset.role = "provider-row";
    row.dataset.provider = entry.provider;
    row.dataset.status = entry.status;

    const name = doc.createElement("span");
    name.className = "assistant-provider-name";
    name.textContent = entry.displayName || entry.provider;

    const status = doc.createElement("span");
    status.className = "assistant-badge";
    status.dataset.role = "provider-status";
    status.textContent = statusLabel(entry.status);

    // Masked tail only — the Bridge never sends the key back.
    const hint = doc.createElement("span");
    hint.className = "assistant-provider-hint";
    hint.dataset.role = "provider-key-hint";
    hint.textContent = entry.hasStoredKey ? entry.keyHint || "stored" : "no key stored";

    row.append(name, status, hint);
    list.appendChild(row);
  }
  return list;
}

/** The Provider Settings page (spec §4). */
export function renderProviderSettings(
  doc: Document,
  state: AssistantSettingsViewState,
  handlers: AssistantSettingsHandlers,
): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-settings";
  root.dataset.role = "provider-settings";

  const head = doc.createElement("div");
  head.className = "assistant-settings-head";
  const title = doc.createElement("span");
  title.textContent = "Provider Settings";
  head.appendChild(title);
  root.appendChild(head);

  const entry = findEntry(state);
  const providerSelect = select(doc, "settings-provider", state.providers.map((item) => item.provider), state.provider);
  providerSelect.addEventListener("change", () => handlers.onSelectProvider?.(providerSelect.value));

  const modelSelect = select(doc, "settings-model", entry?.models ?? [], state.model || entry?.selectedModel || "");
  modelSelect.addEventListener("change", () => handlers.onSelectModel?.(modelSelect.value));

  // Transient by design: read on submit, cleared straight after, never stored.
  const apiKey = doc.createElement("input");
  apiKey.className = "assistant-input";
  apiKey.dataset.role = "api-key-input";
  apiKey.type = "password";
  apiKey.autocomplete = "off";
  apiKey.name = "assistant-provider-secret";
  apiKey.placeholder = entry?.hasStoredKey ? "Stored — type a new key to replace it" : "Paste your API key";

  const baseUrl = doc.createElement("input");
  baseUrl.className = "assistant-input";
  baseUrl.dataset.role = "base-url-input";
  baseUrl.type = "text";
  baseUrl.value = entry?.baseUrl ?? "";
  baseUrl.placeholder = "Default endpoint";

  root.append(
    field(doc, "Provider", providerSelect),
    field(doc, "Model", modelSelect),
    field(doc, "API Key", apiKey),
    field(doc, "Base URL", baseUrl),
  );

  const actions = doc.createElement("div");
  actions.className = "assistant-settings-actions";

  const test = doc.createElement("button");
  test.className = "assistant-settings-test";
  test.dataset.role = "test-connection";
  test.type = "button";
  test.textContent = "Test Connection";
  test.addEventListener("click", () => {
    const key = apiKey.value;
    apiKey.value = "";
    handlers.onTestConnection?.({ provider: providerSelect.value, model: modelSelect.value, apiKey: key });
  });

  const save = doc.createElement("button");
  save.className = "assistant-settings-save";
  save.dataset.role = "save-provider";
  save.type = "button";
  save.textContent = "Save";
  save.addEventListener("click", () => {
    const key = apiKey.value;
    apiKey.value = "";
    handlers.onSaveProvider?.({
      provider: providerSelect.value,
      model: modelSelect.value,
      baseUrl: baseUrl.value.trim(),
      apiKey: key,
    });
  });

  const forget = doc.createElement("button");
  forget.className = "assistant-settings-forget";
  forget.dataset.role = "forget-key";
  forget.type = "button";
  forget.textContent = "Forget stored key";
  forget.addEventListener("click", () => handlers.onForgetKey?.(providerSelect.value));

  actions.append(test, save, forget);
  root.appendChild(actions);

  if (state.test) {
    const result = doc.createElement("div");
    result.className = "assistant-settings-result";
    result.dataset.role = "provider-test-result";
    result.dataset.status = state.test.status;
    result.textContent = `${statusLabel(state.test.status)} — ${state.test.message}`;
    root.appendChild(result);
  }

  root.appendChild(renderProviderStatusList(doc, state));

  const keyStorage = state.settings?.keyStorage;
  const note = doc.createElement("div");
  note.className = "assistant-settings-note";
  note.dataset.role = "key-storage-note";
  note.textContent = keyStorage
    ? `Keys are encrypted by the Bridge (${keyStorage.algorithm}) and stored at ${keyStorage.location}. The extension never keeps a plaintext key.`
    : "Keys are encrypted by the Bridge before storage. The extension never keeps a plaintext key.";
  root.appendChild(note);
  return root;
}
