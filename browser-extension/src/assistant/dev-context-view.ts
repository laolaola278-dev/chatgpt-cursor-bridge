/**
 * Phase 32 · Developer Context view — read-only (spec §14).
 *
 * Shows what the existing Code Assistant / Context system already exposes
 * (project, sources, endpoint) as plain status rows. There is no Execute /
 * Approve / Apply / Fix / Auto Fix / Auto Approve control: a modification can
 * only ever travel Patch Proposal → ApprovalStore → human approval.
 */

import type { AssistantContextStatus } from "./types";

function line(doc: Document, label: string, value: string): HTMLElement {
  const row = doc.createElement("div");
  row.className = "assistant-context-line";
  const key = doc.createElement("span");
  key.className = "assistant-context-label";
  key.textContent = label;
  const val = doc.createElement("span");
  val.className = "assistant-context-value";
  val.textContent = value;
  row.append(key, val);
  return row;
}

export function renderDeveloperContext(doc: Document, status: AssistantContextStatus | null): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-dev-context";
  root.dataset.role = "developer-context";

  const head = doc.createElement("div");
  head.className = "assistant-context-head";
  const title = doc.createElement("span");
  title.textContent = "Developer Context";
  const badge = doc.createElement("span");
  badge.className = "assistant-badge";
  badge.textContent = "READ ONLY";
  head.append(title, badge);
  root.appendChild(head);

  if (!status) {
    root.appendChild(line(doc, "Status:", "not loaded"));
    return root;
  }

  const developer = status.developerContext;
  root.appendChild(line(doc, "Loaded:", developer.loaded ? "yes" : "no"));
  root.appendChild(line(doc, "Project:", developer.project || "(none selected)"));
  root.appendChild(line(doc, "Sources:", developer.sources?.length ? developer.sources.join(", ") : "(none)"));
  root.appendChild(line(doc, "Endpoint:", developer.endpoint || "(none)"));
  root.appendChild(
    line(doc, "Modifications:", developer.modificationRequiresApproval === false ? "unknown" : "require human approval"),
  );
  root.appendChild(line(doc, "Web capture:", status.web.automaticCapture ? "automatic" : "explicit Ask AI only"));
  root.appendChild(line(doc, "Web upload:", status.web.automaticUpload ? "automatic" : "only with your message"));

  const note = doc.createElement("div");
  note.className = "assistant-context-note";
  note.textContent =
    "The assistant reads and explains this context and may draft a proposal. It cannot modify source files or run anything.";
  root.appendChild(note);
  return root;
}
