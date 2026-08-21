/**
 * Phase 32 · Web Context Assistant (explicit **Ask AI** consent only).
 *
 * The mandatory chain (spec §12) is:
 *
 *   user clicks Ask AI → collect page context → show the collected context →
 *   user sends a question → context bundle → LLM Gateway
 *
 * Consequences encoded here:
 *
 * * `collectWebContext` is only ever called from the Ask AI click handler. This
 *   module registers **no** load, DOMContentLoaded, visibilitychange, timer or
 *   MutationObserver hook, so there is no background capture path.
 * * Collecting does not send. The bundle is handed to the panel for display; it
 *   only reaches the Bridge when the user submits a message.
 * * A non-http(s) page (file://, chrome://) never contributes its URL.
 */

import type { WebContextBundle } from "./types";

export const ASK_AI_TRIGGER = "ask_ai";
export const MAX_SELECTED_TEXT = 8000;
export const MAX_READABLE_CONTENT = 20000;

const READABLE_SELECTORS = ["main", "article", "[role='main']"];

function nowIso(): string {
  return new Date().toISOString();
}

function isShareableUrl(raw: string): boolean {
  return /^https?:\/\//i.test(raw.trim());
}

/** Strip the query string: it frequently carries tokens. */
function safeUrl(raw: string): string {
  const candidate = (raw ?? "").trim();
  if (!isShareableUrl(candidate)) return "";
  const cut = candidate.split(/[?#]/, 1)[0];
  return cut.slice(0, 2000);
}

function selectionText(doc: Document): string {
  const view = doc.defaultView;
  const selection = view?.getSelection?.();
  return (selection?.toString() ?? "").trim().slice(0, MAX_SELECTED_TEXT);
}

/** Visible prose of the page, best-effort and length-capped. */
export function readableContent(doc: Document): string {
  let host: Element | null = null;
  for (const selector of READABLE_SELECTORS) {
    host = doc.querySelector(selector);
    if (host) break;
  }
  const source = host ?? doc.body ?? null;
  if (!source) return "";
  const text = (source.textContent ?? "").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
  return text.slice(0, MAX_READABLE_CONTENT);
}

export interface CollectOptions {
  /** Injected for tests; defaults to the real clock. */
  timestamp?: string;
  /** Injected for tests; defaults to `doc.defaultView.location.href`. */
  url?: string;
}

/**
 * Build one bundle from the current page.
 *
 * Call this **only** in response to an explicit Ask AI click: the returned
 * bundle carries `trigger: "ask_ai"` plus the consent timestamp the Bridge
 * requires, and the Bridge rejects a bundle without them.
 */
export function collectWebContext(doc: Document, options: CollectOptions = {}): WebContextBundle {
  const timestamp = options.timestamp ?? nowIso();
  const href = options.url ?? doc.defaultView?.location?.href ?? "";
  return {
    trigger: ASK_AI_TRIGGER,
    consented_at: timestamp,
    page_title: (doc.title ?? "").slice(0, 300),
    page_url: safeUrl(href),
    selected_text: selectionText(doc),
    readable_content: readableContent(doc),
    timestamp,
  };
}

export interface AskAiHandlers {
  /** Receives the freshly collected bundle. Must not send it anywhere. */
  onAskAi: (bundle: WebContextBundle) => void;
  collect?: (doc: Document) => WebContextBundle;
}

/** The floating Ask AI trigger. Nothing is collected until it is clicked. */
export function renderAskAiButton(doc: Document, handlers: AskAiHandlers): HTMLButtonElement {
  const button = doc.createElement("button");
  button.className = "assistant-ask-ai";
  button.dataset.role = "ask-ai";
  button.type = "button";
  button.textContent = "Ask AI";
  button.title = "Share this page with the assistant (collected only now, sent only when you send a message)";
  button.addEventListener("click", () => {
    const collect = handlers.collect ?? ((target: Document) => collectWebContext(target));
    handlers.onAskAi(collect(doc));
  });
  return button;
}

export interface WebContextPreviewHandlers {
  onClearContext?: () => void;
}

/** Read-only preview of what would be sent (spec §12: Context UI). */
export function renderWebContextPreview(
  doc: Document,
  bundle: WebContextBundle | null,
  handlers: WebContextPreviewHandlers = {},
): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-context";
  root.dataset.role = "web-context";

  const head = doc.createElement("div");
  head.className = "assistant-context-head";
  const title = doc.createElement("span");
  title.textContent = "Page Context";
  const badge = doc.createElement("span");
  badge.className = "assistant-badge";
  badge.textContent = "READ ONLY";
  head.append(title, badge);
  root.appendChild(head);

  if (!bundle) {
    const empty = doc.createElement("div");
    empty.className = "assistant-context-line";
    empty.textContent = "No page context. Click Ask AI to share this page.";
    root.append(empty);
    return root;
  }

  const line = (label: string, value: string) => {
    const row = doc.createElement("div");
    row.className = "assistant-context-line";
    const key = doc.createElement("span");
    key.className = "assistant-context-label";
    key.textContent = label;
    const val = doc.createElement("span");
    val.className = "assistant-context-value";
    val.textContent = value;
    row.append(key, val);
    root.appendChild(row);
  };

  line("Page:", bundle.page_title || "(untitled)");
  line("URL:", bundle.page_url || "(local page — not shared)");
  line("Selected Text:", bundle.selected_text || "(none)");
  line("Readable Content:", bundle.readable_content ? `${bundle.readable_content.length} characters` : "(none)");
  line("Timestamp:", bundle.timestamp);
  line("Trigger:", bundle.trigger);

  const note = doc.createElement("div");
  note.className = "assistant-context-note";
  note.textContent = "Collected when you clicked Ask AI. It is sent only with your next message.";
  root.appendChild(note);

  const clear = doc.createElement("button");
  clear.className = "assistant-context-clear";
  clear.dataset.role = "clear-context";
  clear.type = "button";
  clear.textContent = "Remove context";
  clear.addEventListener("click", () => handlers.onClearContext?.());
  root.appendChild(clear);
  return root;
}
