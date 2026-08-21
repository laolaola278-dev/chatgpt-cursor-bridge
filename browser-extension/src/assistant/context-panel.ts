/**
 * Phase 34 · Context Bundle panel.
 *
 * Task 5 asks for one place that answers "what exactly would be sent, and do I
 * want to send it?". This module wraps the Phase 32 `renderWebContextPreview`
 * (left untouched, so its consent semantics and its tests keep holding) and adds
 * around it:
 *
 * * Project, Agent and the read-only status of the bundle
 * * where the context came from (Ask AI, plus the read-only developer sources)
 * * the current page title and a summary of the selected text
 * * a preview of the **actual injected content** — the same string the Bridge
 *   would receive, truncated for display only
 * * an explicit include / exclude control, and Remove context
 *
 * The mandatory chain is unchanged:
 *
 *   Ask AI click → capture → preview → the user sends a question → LLM Gateway
 *
 * Nothing here captures, uploads, injects or asks anything: the module renders
 * state and reports clicks. It registers no load, timer, observer or
 * visibility hook, so there is no background collection path, and no code path
 * sends the bundle — only the user's next message does.
 */

import type { AssistantContextStatus, UiMode, WebContextBundle } from "./types";
import { renderWebContextPreview, type WebContextPreviewHandlers } from "./web-context";

/** How much of the injected content the preview shows. Display cap only. */
export const CONTEXT_PREVIEW_LIMIT = 1200;

export interface ContextPanelState {
  bundle: WebContextBundle | null;
  /** Whether the bundle travels with the next message. Default: it does. */
  include: boolean;
  project: string | null;
  provider: string;
  model: string;
  uiMode: UiMode;
  contextStatus: AssistantContextStatus | null;
}

export interface ContextPanelHandlers extends WebContextPreviewHandlers {
  /** Flip include/exclude. Excluding keeps the preview and sends nothing. */
  onToggleContextInclude?: (include: boolean) => void;
}

/**
 * The exact text that would be injected with the next message.
 *
 * Built from the consented bundle only. Used for display *and* as the honest
 * answer to "what does the model see" — there is no second, hidden payload.
 */
export function injectedContextText(bundle: WebContextBundle | null): string {
  if (!bundle) return "";
  const parts: string[] = [];
  if (bundle.page_title) parts.push(`Page: ${bundle.page_title}`);
  if (bundle.page_url) parts.push(`URL: ${bundle.page_url}`);
  if (bundle.selected_text) parts.push(`Selected text:\n${bundle.selected_text}`);
  if (bundle.readable_content) parts.push(`Readable content:\n${bundle.readable_content}`);
  return parts.join("\n\n");
}

/** One-line summary of a possibly long selection. */
export function selectedTextSummary(bundle: WebContextBundle | null): string {
  const selected = bundle?.selected_text ?? "";
  if (!selected) return "(nothing selected)";
  const head = selected.replace(/\s+/g, " ").trim().slice(0, 120);
  return `${selected.length} characters — “${head}${selected.length > head.length ? "…" : ""}”`;
}

function row(doc: Document, label: string, value: string, role: string): HTMLElement {
  const line = doc.createElement("div");
  line.className = "assistant-context-line";
  line.dataset.role = role;
  const key = doc.createElement("span");
  key.className = "assistant-context-label";
  key.textContent = label;
  const val = doc.createElement("span");
  val.className = "assistant-context-value";
  val.textContent = value;
  line.append(key, val);
  return line;
}

/** Where this context came from. Ask AI is always named explicitly. */
function contextSource(state: ContextPanelState): string {
  const sources: string[] = [];
  if (state.bundle) sources.push("Ask AI (this page, on your click)");
  const developer = state.contextStatus?.developerContext;
  if (state.uiMode === "developer" && developer?.loaded) {
    const names = developer.sources?.length ? developer.sources.join(", ") : "project files";
    sources.push(`Developer Context (read-only: ${names})`);
  }
  return sources.length ? sources.join(" · ") : "No context captured";
}

export function renderContextBundlePanel(
  doc: Document,
  state: ContextPanelState,
  handlers: ContextPanelHandlers = {},
): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-context-panel";
  root.dataset.role = "context-bundle";
  root.dataset.include = state.include && state.bundle ? "true" : "false";

  const head = doc.createElement("div");
  head.className = "assistant-context-panel-head";
  const title = doc.createElement("span");
  title.className = "assistant-context-panel-title";
  title.textContent = "Context Bundle";
  const badge = doc.createElement("span");
  badge.className = "assistant-badge";
  badge.dataset.role = "context-readonly";
  badge.textContent = "READ ONLY";
  head.append(title, badge);
  root.appendChild(head);

  root.appendChild(row(doc, "Project:", state.project || "(no project selected)", "context-project"));
  root.appendChild(
    row(
      doc,
      "Agent:",
      state.provider ? `${state.provider}${state.model ? ` · ${state.model}` : ""}` : "(local simulator)",
      "context-agent",
    ),
  );
  root.appendChild(
    row(doc, "Status:", "Read-only context. The assistant proposes; a human approves every change.", "context-status"),
  );
  root.appendChild(row(doc, "Context source:", contextSource(state), "context-source"));
  root.appendChild(row(doc, "Current page:", state.bundle?.page_title || "(no page captured)", "context-page-title"));
  root.appendChild(row(doc, "Selected text:", selectedTextSummary(state.bundle), "context-selected-summary"));

  // What the model would actually receive. Empty until Ask AI is clicked.
  const injected = injectedContextText(state.bundle);
  const preview = doc.createElement("pre");
  preview.className = "assistant-context-injected";
  preview.dataset.role = "context-injected-preview";
  preview.dataset.length = String(injected.length);
  preview.textContent = injected
    ? injected.slice(0, CONTEXT_PREVIEW_LIMIT) + (injected.length > CONTEXT_PREVIEW_LIMIT ? "\n…" : "")
    : "Nothing would be sent. Click Ask AI to capture this page.";
  root.appendChild(preview);

  const decision = doc.createElement("div");
  decision.className = "assistant-context-decision";
  decision.dataset.role = "context-decision";
  decision.textContent = state.bundle
    ? state.include
      ? "This context goes with your next message."
      : "This context stays here and is not sent."
    : "No context is attached to your next message.";
  root.appendChild(decision);

  if (state.bundle) {
    // A button, not a checkbox: the Phase 32 preview must stay input-free, and
    // one explicit click is the whole decision.
    const toggle = doc.createElement("button");
    toggle.className = "assistant-context-include";
    toggle.dataset.role = "toggle-context-include";
    toggle.dataset.include = state.include ? "true" : "false";
    toggle.type = "button";
    toggle.textContent = state.include ? "Do not send this context" : "Send this context";
    toggle.title = "Decides whether the captured page travels with your next message";
    toggle.addEventListener("click", () => handlers.onToggleContextInclude?.(!state.include));
    root.appendChild(toggle);
  }

  // The Phase 32 preview keeps its own fields, its own Remove control and its
  // own guarantees; this panel only surrounds it.
  root.appendChild(renderWebContextPreview(doc, state.bundle, handlers));
  return root;
}
