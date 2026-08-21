/**
 * Approval card rendering.
 *
 * Shows the operation, target file, reason, risk level and the diff preview
 * returned by the Bridge. Approve/Reject are the only ways forward.
 */

import { ACTION_LABELS, isMemoryAction, type PendingAction } from "../models/action";
import type { RecoveredApproval } from "../bridge/types";

export interface ApprovalCardHandlers {
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

const STATE_LABELS: Record<string, string> = {
  approving: "Executing via Local Bridge...",
  approved: "Approved and executed",
  rejected: "Rejected by user",
  failed: "Failed",
};

function field(doc: Document, label: string, value: string, mono = false): HTMLElement {
  const row = doc.createElement("div");
  row.className = "field";
  const strong = doc.createElement("b");
  strong.textContent = `${label}: `;
  const span = doc.createElement("span");
  if (mono) span.className = "mono";
  span.textContent = value;
  row.append(strong, span);
  return row;
}

export function renderRecoveredApprovalCard(
  doc: Document,
  item: RecoveredApproval,
  onReconfirm: (id: string) => void,
  onApprove: (id: string) => void = () => {},
): HTMLElement {
  const card = doc.createElement("div");
  card.className = "card recovered-card";
  card.dataset.requestId = item.requestId;
  card.dataset.state = item.status;
  const head = doc.createElement("div");
  head.className = "card-head";
  const title = doc.createElement("span");
  title.className = "card-action";
  title.textContent = `Recovered approval · ${item.action}`;
  const badge = doc.createElement("span");
  badge.className = "risk medium";
  badge.textContent = "RECONFIRM REQUIRED";
  head.append(title, badge);
  card.appendChild(head);
  card.appendChild(field(doc, "Project", item.project, true));
  card.appendChild(field(doc, "Target", item.path, true));
  card.appendChild(field(doc, "Reason", item.reason));
  if (item.preview) {
    const preview = doc.createElement("pre");
    preview.className = "preview";
    preview.textContent = item.preview;
    card.appendChild(preview);
  }
  const button = doc.createElement("button");
  button.className = "btn btn-approve";
  if (item.status === "reconfirmed") {
    button.dataset.role = "approve-recovered";
    button.textContent = "Approve execution";
    button.addEventListener("click", () => onApprove(item.requestId));
  } else {
    button.dataset.role = "reconfirm";
    button.textContent = "Reconfirm approval";
    button.addEventListener("click", () => onReconfirm(item.requestId));
  }
  card.appendChild(button);
  const note = doc.createElement("div");
  note.className = "state approving";
  note.textContent = item.status === "reconfirmed"
    ? "Reconfirmed. Execution still requires this separate explicit approval."
    : "Recovery never approves or executes automatically.";
  card.appendChild(note);
  return card;
}

export function renderApprovalCard(
  doc: Document,
  item: PendingAction,
  handlers: ApprovalCardHandlers,
): HTMLElement {
  const card = doc.createElement("div");
  card.className = "card";
  card.dataset.actionId = item.id;
  card.dataset.state = item.state;

  const head = doc.createElement("div");
  head.className = "card-head";

  const title = doc.createElement("span");
  title.className = "card-action";
  title.textContent = ACTION_LABELS[item.action.action] ?? item.action.action;

  const risk = doc.createElement("span");
  risk.className = `risk ${item.action.risk}`;
  risk.textContent = item.action.risk;

  head.append(title, risk);
  card.appendChild(head);

  card.appendChild(field(doc, "Project", item.action.target.project, true));

  if (isMemoryAction(item.action.action)) {
    card.appendChild(
      field(doc, "Memory", item.action.target.document ?? item.action.target.path, true),
    );
    if (item.action.action === "memory.decision") {
      card.appendChild(field(doc, "ADR Title", item.action.payload.title ?? ""));
    }
  } else {
    card.appendChild(field(doc, "File", item.action.target.path, true));
  }

  card.appendChild(field(doc, "Reason", item.action.reason));

  if (item.preview) {
    const preview = doc.createElement("pre");
    preview.className = "preview";
    preview.textContent = item.preview;
    card.appendChild(preview);
  }

  if (item.state === "pending") {
    const actions = doc.createElement("div");
    actions.className = "actions";

    const approve = doc.createElement("button");
    approve.className = "btn btn-approve";
    approve.textContent = "Approve";
    approve.dataset.role = "approve";
    approve.addEventListener("click", () => handlers.onApprove(item.id));

    const reject = doc.createElement("button");
    reject.className = "btn btn-reject";
    reject.textContent = "Reject";
    reject.dataset.role = "reject";
    reject.addEventListener("click", () => handlers.onReject(item.id));

    actions.append(approve, reject);
    card.appendChild(actions);
  } else {
    const state = doc.createElement("div");
    state.className = `state ${item.state}`;
    state.textContent = item.message ?? STATE_LABELS[item.state] ?? item.state;
    card.appendChild(state);
  }

  return card;
}
