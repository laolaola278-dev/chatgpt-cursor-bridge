import type { QualityReport, RuntimeEvent, RuntimeRecord, TaskRecord } from "./models";

function block(doc: Document, title: string): HTMLElement {
  const node = doc.createElement("section");
  node.className = "runtime-block";
  const heading = doc.createElement("h4");
  heading.textContent = title;
  node.appendChild(heading);
  return node;
}

function item(doc: Document, value: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `runtime-item ${tone}`.trim();
  node.textContent = value;
  return node;
}

export function renderRuntimeDashboard(
  doc: Document,
  runtimes: RuntimeRecord[],
  tasks: TaskRecord[],
  events: RuntimeEvent[],
  quality: QualityReport | null,
): HTMLElement {
  const root = doc.createElement("section");
  root.className = "runtime-dashboard";
  root.dataset.role = "runtime-dashboard";
  const header = doc.createElement("div");
  header.className = "runtime-heading";
  const title = doc.createElement("strong");
  title.textContent = "Autonomous Runtime";
  const badge = doc.createElement("span");
  badge.textContent = "READ ONLY";
  badge.className = "runtime-badge";
  header.append(title, badge);
  root.appendChild(header);

  const summary = doc.createElement("div");
  summary.className = "runtime-summary";
  summary.append(
    item(doc, `${runtimes.length} runtime${runtimes.length === 1 ? "" : "s"}`),
    item(doc, `${tasks.filter((task) => task.status === "PENDING").length} pending tasks`),
    item(doc, `${tasks.filter((task) => task.status === "WAITING_APPROVAL").length} approvals`),
    item(doc, quality ? `Quality ${quality.qualityScore}/100` : "Quality —"),
  );
  root.appendChild(summary);

  const runtimeBlock = block(doc, "Runtime status");
  for (const runtime of runtimes.slice(0, 5)) {
    runtimeBlock.appendChild(item(doc, `${runtime.id} · ${runtime.state} · agent ${runtime.agentId}`, runtime.state === "RECOVERED" ? "warning" : ""));
  }
  if (!runtimes.length) runtimeBlock.appendChild(item(doc, "No runtime records"));
  root.appendChild(runtimeBlock);

  const taskBlock = block(doc, "Task queue");
  for (const task of tasks.slice(0, 6)) taskBlock.appendChild(item(doc, `${task.status} · ${task.id} · priority ${task.priority}`));
  if (!tasks.length) taskBlock.appendChild(item(doc, "No tasks"));
  root.appendChild(taskBlock);

  const eventBlock = block(doc, "Recent events");
  for (const event of events.slice(-5).reverse()) eventBlock.appendChild(item(doc, `${event.type} · ${event.source} · ${new Date(event.timestamp).toLocaleTimeString()}`));
  if (!events.length) eventBlock.appendChild(item(doc, "No events"));
  root.appendChild(eventBlock);

  if (quality) {
    const qualityBlock = block(doc, "Quality gate");
    qualityBlock.appendChild(item(doc, `${quality.qualityScore}/100 · ${quality.risk.toUpperCase()}`, quality.risk === "high" || quality.risk === "critical" ? "warning" : ""));
    for (const issue of quality.blockingIssues) qualityBlock.appendChild(item(doc, issue, "warning"));
    root.appendChild(qualityBlock);
  }
  return root;
}
