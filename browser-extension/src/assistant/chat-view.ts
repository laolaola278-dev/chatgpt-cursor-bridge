/**
 * Phase 32 · Assistant chat UI, refined in Phase 34.
 *
 * Renders user and assistant messages, the streaming/loading indicator, the
 * conversation history list and the composer. Tool calls returned by the model
 * are shown as **proposals waiting for approval** in Developer Mode only.
 *
 * There is deliberately no Execute / Approve / Apply / Fix / Auto Fix /
 * Auto Approve / Run / Terminal control anywhere in this module: approving a
 * proposal happens through the existing ApprovalStore flow, driven by a human.
 *
 * Phase 34 adds composer ergonomics (Enter sends, Shift+Enter breaks the line,
 * auto-grow up to a cap), a Retry control and conversation management (search,
 * rename, pin/unpin, remove from view). Every one of those is a *click* or a
 * keystroke: this module issues no request by itself, and **Retry never fires
 * automatically** — it only ever re-sends the last user message the user asked
 * for it to re-send.
 */

import type { AssistantChatTurn, AssistantConversationView, AssistantToolCall, UiMode } from "./types";
import { renderMarkdown } from "./markdown";
import { sanitizeStatusText } from "./errors";
import { visibleAssistantConversations } from "../state/store";

export interface AssistantChatHandlers {
  onSend: (text: string) => void;
  onStop?: () => void;
  onNewChat?: () => void;
  onSelectConversation?: (id: string) => void;
  /** Removes a conversation from the extension view only. */
  onRemoveConversation?: (id: string) => void;
  onCopy?: (code: string) => void;
  /** Phase 34 · re-send the last user message. Always a click, never a timer. */
  onRetry?: () => void;
  /** Phase 34 · conversation management. All extension-view-only. */
  onSearchConversations?: (query: string) => void;
  onBeginRename?: (id: string) => void;
  onRename?: (id: string, title: string) => void;
  onCancelRename?: () => void;
  onTogglePin?: (id: string) => void;
}

export interface AssistantChatViewState {
  uiMode: UiMode;
  conversations: AssistantConversationView[];
  activeConversation: string | null;
  streaming: boolean;
  status: string;
  /** Phase 34 · History search text. Display filter only. */
  query?: string;
  /** Phase 34 · id whose inline rename box is open. */
  renaming?: string | null;
  /** Phase 34 · composer text preserved after a failed send. */
  draft?: string;
  /** Phase 34 · true when the last request failed and Retry may be offered. */
  canRetry?: boolean;
}

/** Composer growth cap, in pixels. Beyond this the textarea scrolls. */
export const MAX_COMPOSER_HEIGHT = 160;

/**
 * Grow the composer to fit its content, up to {@link MAX_COMPOSER_HEIGHT}.
 *
 * `scrollHeight` is 0 in a layout-less environment (jsdom); the cap is applied
 * through `max-height` regardless, so the ceiling holds either way.
 */
export function autoGrowComposer(input: HTMLTextAreaElement): void {
  input.style.maxHeight = `${MAX_COMPOSER_HEIGHT}px`;
  input.style.height = "auto";
  const needed = input.scrollHeight;
  if (!needed) return;
  input.style.height = `${Math.min(needed, MAX_COMPOSER_HEIGHT)}px`;
  input.style.overflowY = needed > MAX_COMPOSER_HEIGHT ? "auto" : "hidden";
}

/** One tool call, rendered as an inert proposal. */
export function renderToolProposal(doc: Document, call: AssistantToolCall): HTMLElement {
  const card = doc.createElement("div");
  card.className = "assistant-tool-proposal";
  card.dataset.role = "tool-proposal";

  const head = doc.createElement("div");
  head.className = "assistant-tool-head";
  const name = doc.createElement("span");
  name.className = "assistant-tool-name";
  name.textContent = call.name;
  const state = doc.createElement("span");
  state.className = "assistant-tool-state";
  state.dataset.role = "tool-state";
  state.textContent = "Waiting Approval";
  head.append(name, state);

  const args = doc.createElement("pre");
  args.className = "assistant-tool-arguments";
  args.dataset.role = "tool-arguments";
  args.textContent = call.arguments;

  const note = doc.createElement("div");
  note.className = "assistant-tool-note";
  note.textContent = "Proposal only. A human approves it in the approval list; the assistant cannot run it.";

  card.append(head, args, note);
  return card;
}

export function renderChatTurn(
  doc: Document,
  turn: AssistantChatTurn,
  mode: UiMode,
  handlers: AssistantChatHandlers,
): HTMLElement {
  const row = doc.createElement("div");
  row.className = `assistant-message ${turn.role}`;
  row.dataset.role = "chat-message";
  row.dataset.messageRole = turn.role;

  const who = doc.createElement("div");
  who.className = "assistant-message-role";
  who.textContent = turn.role === "user" ? "You" : "Assistant";
  row.appendChild(who);

  if (turn.role === "assistant") {
    row.appendChild(renderMarkdown(doc, turn.content, { onCopy: handlers.onCopy }));
  } else {
    const body = doc.createElement("div");
    body.className = "assistant-message-body";
    body.textContent = turn.content;
    row.appendChild(body);
  }

  if (turn.streaming) {
    const streaming = doc.createElement("div");
    streaming.className = "assistant-message-state";
    streaming.dataset.role = "chat-streaming";
    streaming.textContent = "Streaming…";
    row.appendChild(streaming);
  }
  if (turn.stopped) {
    const stopped = doc.createElement("div");
    stopped.className = "assistant-message-state";
    stopped.dataset.role = "chat-stopped";
    stopped.textContent = "Streaming stopped";
    row.appendChild(stopped);
  }
  if (turn.failed) {
    // A fixed label. The reason lives in the status line, which is itself part
    // of the closed safe vocabulary — no provider or exception text here.
    const failed = doc.createElement("div");
    failed.className = "assistant-message-state failed";
    failed.dataset.role = "chat-failed";
    failed.textContent = "Request failed";
    row.appendChild(failed);
  }

  // Tool proposals are a Developer Mode surface (spec §15).
  if (mode === "developer" && turn.toolCalls?.length) {
    for (const call of turn.toolCalls) row.appendChild(renderToolProposal(doc, call));
  }
  return row;
}

function historyButton(
  doc: Document,
  role: string,
  label: string,
  className: string,
  title: string,
  handler: () => void,
): HTMLButtonElement {
  const element = doc.createElement("button");
  element.className = className;
  element.dataset.role = role;
  element.type = "button";
  element.textContent = label;
  element.title = title;
  element.addEventListener("click", handler);
  return element;
}

/** The inline rename box. Bounded input, explicit Save, explicit Cancel. */
function renderRenameBox(
  doc: Document,
  conversation: AssistantConversationView,
  handlers: AssistantChatHandlers,
): HTMLElement {
  const box = doc.createElement("div");
  box.className = "assistant-history-rename";
  box.dataset.role = "rename-box";

  const field = doc.createElement("input");
  field.className = "assistant-history-rename-input";
  field.dataset.role = "rename-input";
  field.type = "text";
  field.maxLength = 80;
  field.value = conversation.title;
  field.setAttribute("aria-label", "Conversation name");

  const save = () => handlers.onRename?.(conversation.id, field.value);
  field.addEventListener("keydown", (event) => {
    const key = (event as KeyboardEvent).key;
    if (key === "Enter") {
      event.preventDefault();
      save();
    } else if (key === "Escape") {
      event.preventDefault();
      handlers.onCancelRename?.();
    }
  });

  box.append(
    field,
    historyButton(doc, "rename-save", "Save", "assistant-history-rename-save", "Rename in this view only", save),
    historyButton(doc, "rename-cancel", "Cancel", "assistant-history-rename-cancel", "Keep the current name", () =>
      handlers.onCancelRename?.(),
    ),
  );
  return box;
}

function renderHistory(doc: Document, state: AssistantChatViewState, handlers: AssistantChatHandlers): HTMLElement {
  const history = doc.createElement("div");
  history.className = "assistant-history";
  history.dataset.role = "chat-history";

  const head = doc.createElement("div");
  head.className = "assistant-history-head";
  const label = doc.createElement("span");
  label.textContent = "History";
  const newChat = doc.createElement("button");
  newChat.className = "assistant-new-chat";
  newChat.dataset.role = "new-chat";
  newChat.type = "button";
  newChat.textContent = "New Chat";
  newChat.addEventListener("click", () => handlers.onNewChat?.());
  head.append(label, newChat);
  history.appendChild(head);

  // Search filters the local list as you type. No Bridge call, no LLM request.
  const search = doc.createElement("input");
  search.className = "assistant-history-search";
  search.dataset.role = "chat-search";
  search.type = "search";
  search.placeholder = "Search conversations…";
  search.maxLength = 120;
  search.value = state.query ?? "";
  search.setAttribute("aria-label", "Search conversations in this view");
  search.addEventListener("input", () => handlers.onSearchConversations?.(search.value));
  history.appendChild(search);

  if (state.conversations.length === 0) {
    const empty = doc.createElement("div");
    empty.className = "assistant-history-empty";
    empty.dataset.role = "history-empty";
    empty.textContent = "No conversations in this view yet.";
    history.appendChild(empty);
    return history;
  }

  const visible = visibleAssistantConversations(state.conversations, state.query ?? "");
  if (visible.length === 0) {
    const none = doc.createElement("div");
    none.className = "assistant-history-empty";
    none.dataset.role = "history-empty";
    // Nothing was deleted: a filter that matches nothing only hides rows.
    none.textContent = "No conversation matches this search.";
    history.appendChild(none);
    return history;
  }

  for (const conversation of visible) {
    const row = doc.createElement("div");
    row.className = `assistant-history-entry${conversation.id === state.activeConversation ? " active" : ""}${
      conversation.pinned ? " pinned" : ""
    }`;
    row.dataset.role = "history-entry";
    row.dataset.conversationId = conversation.id;
    if (conversation.pinned) row.dataset.pinned = "true";

    const open = doc.createElement("button");
    open.className = "assistant-history-open";
    open.dataset.role = "open-conversation";
    open.type = "button";
    open.textContent = `${conversation.pinned ? "📌 " : ""}${conversation.title || "Untitled chat"}`;
    open.addEventListener("click", () => handlers.onSelectConversation?.(conversation.id));
    row.appendChild(open);

    row.appendChild(
      historyButton(
        doc,
        "pin-conversation",
        conversation.pinned ? "Unpin" : "Pin",
        "assistant-history-pin",
        "Keeps it at the top of this view only",
        () => handlers.onTogglePin?.(conversation.id),
      ),
    );
    row.appendChild(
      historyButton(doc, "rename-conversation", "Rename", "assistant-history-rename-open", "Rename in this view only", () =>
        handlers.onBeginRename?.(conversation.id),
      ),
    );
    row.appendChild(
      historyButton(
        doc,
        "remove-conversation",
        "Remove from view",
        "assistant-history-remove",
        "Hides it in the extension only; the Bridge keeps its own records",
        () => handlers.onRemoveConversation?.(conversation.id),
      ),
    );

    if (state.renaming === conversation.id) row.appendChild(renderRenameBox(doc, conversation, handlers));
    history.appendChild(row);
  }

  const note = doc.createElement("div");
  note.className = "assistant-history-note";
  note.dataset.role = "history-note";
  note.textContent = "Search, rename, pin and remove change this list only. The Bridge keeps its own records.";
  history.appendChild(note);
  return history;
}

/** The whole chat surface: history, transcript, status and composer. */
export function renderAssistantChat(
  doc: Document,
  state: AssistantChatViewState,
  handlers: AssistantChatHandlers,
): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-chat";
  root.dataset.role = "assistant-chat";

  root.appendChild(renderHistory(doc, state, handlers));

  const transcript = doc.createElement("div");
  transcript.className = "assistant-transcript";
  transcript.dataset.role = "chat-transcript";
  const active = state.conversations.find((item) => item.id === state.activeConversation) ?? null;
  if (!active || active.turns.length === 0) {
    const empty = doc.createElement("div");
    empty.className = "assistant-transcript-empty";
    empty.textContent = "Ask anything. The assistant explains and drafts; it never executes.";
    transcript.appendChild(empty);
  } else {
    for (const turn of active.turns) transcript.appendChild(renderChatTurn(doc, turn, state.uiMode, handlers));
  }
  root.appendChild(transcript);

  if (state.streaming) {
    const loading = doc.createElement("div");
    loading.className = "assistant-loading";
    loading.dataset.role = "chat-loading";
    loading.textContent = "Loading…";
    root.appendChild(loading);
  }
  if (state.status) {
    const status = doc.createElement("div");
    status.className = "assistant-status";
    status.dataset.role = "chat-status";
    // Final gate: only the closed safe vocabulary reaches the screen.
    status.textContent = sanitizeStatusText(state.status);
    root.appendChild(status);
  }

  // Retry is offered only after a failure, and only as a button. Nothing in this
  // module ever re-sends a provider request on its own.
  if (state.canRetry && !state.streaming) {
    const retry = doc.createElement("button");
    retry.className = "assistant-retry";
    retry.dataset.role = "chat-retry";
    retry.type = "button";
    retry.textContent = "Retry";
    retry.title = "Re-sends your last message. Nothing is retried automatically.";
    retry.addEventListener("click", () => handlers.onRetry?.());
    root.appendChild(retry);
  }

  const composer = doc.createElement("div");
  composer.className = "assistant-composer";
  const input = doc.createElement("textarea");
  input.className = "assistant-input";
  input.dataset.role = "chat-input";
  input.rows = 2;
  input.placeholder = "Ask the assistant…";
  input.style.maxHeight = `${MAX_COMPOSER_HEIGHT}px`;
  // A failed send hands the text back instead of dropping it.
  if (state.draft) input.value = state.draft;

  const send = doc.createElement("button");
  send.className = "assistant-send";
  send.dataset.role = "chat-send";
  send.type = "button";
  send.textContent = "Send";
  send.disabled = state.streaming;

  const submit = () => {
    if (state.streaming) return;
    const value = input.value.trim();
    if (!value) return;
    input.value = "";
    autoGrowComposer(input);
    handlers.onSend(value);
  };
  send.addEventListener("click", submit);

  // Enter sends, Shift+Enter (and any modifier, and an active IME composition)
  // inserts a newline instead.
  input.addEventListener("keydown", (event) => {
    const key = (event as KeyboardEvent).key;
    if (key !== "Enter") return;
    const keyboard = event as KeyboardEvent;
    if (keyboard.shiftKey || keyboard.ctrlKey || keyboard.metaKey || keyboard.altKey || keyboard.isComposing) return;
    event.preventDefault();
    submit();
  });
  input.addEventListener("input", () => autoGrowComposer(input));
  autoGrowComposer(input);

  composer.append(input, send);
  if (state.streaming) {
    const stop = doc.createElement("button");
    stop.className = "assistant-stop";
    stop.dataset.role = "chat-stop";
    stop.type = "button";
    stop.textContent = "Stop";
    // Stop ends the stream. It never schedules a retry.
    stop.addEventListener("click", () => handlers.onStop?.());
    composer.appendChild(stop);
  }

  const hint = doc.createElement("div");
  hint.className = "assistant-composer-hint";
  hint.dataset.role = "composer-hint";
  hint.textContent = "Enter sends · Shift+Enter adds a line";
  composer.appendChild(hint);

  root.appendChild(composer);
  return root;
}
