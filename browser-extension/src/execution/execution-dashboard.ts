import type { ExecutionProposalRecord, ExecutionQuality7, ExecutionResultRecord, ExecutionTaskRecord } from "./models";

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `execution-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

export function renderExecutionDashboard(
  doc: Document,
  tasks: ExecutionTaskRecord[],
  proposals: ExecutionProposalRecord[],
  results: ExecutionResultRecord[],
  quality: ExecutionQuality7 | null,
): HTMLElement {
  const root = doc.createElement("section");
  root.className = "execution-dashboard";
  root.dataset.role = "execution-dashboard";

  const heading = doc.createElement("div");
  heading.className = "execution-heading";
  const title = doc.createElement("strong");
  title.textContent = "Execution Control Center";
  const badge = doc.createElement("span");
  badge.className = "execution-badge";
  badge.textContent = "CONTROLLED · READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  if (!tasks.length && !proposals.length && !results.length && !quality) {
    root.appendChild(line(doc, "No controlled execution yet"));
    return root;
  }

  const waiting = proposals.filter((item) => item.status === "PROPOSED").length;
  const pendingTasks = tasks.filter((item) => item.status === "APPROVAL_REQUIRED").length;
  root.appendChild(line(doc, `${tasks.length} implementation tasks · ${pendingTasks} waiting approval · ${waiting} proposals pending`));

  const overview = doc.createElement("div");
  overview.className = "execution-overview";
  const items: Array<[string, string]> = [
    ["Tasks", String(tasks.length)],
    ["Proposal queue", String(waiting)],
    ["Executed", String(results.length)],
    ["Verified", String(results.filter((item) => item.verification.status === "PASS").length)],
  ];
  for (const [label, value] of items) {
    const cell = doc.createElement("div");
    cell.className = "execution-item";
    cell.appendChild(line(doc, label));
    cell.appendChild(line(doc, value, "execution-count"));
    overview.appendChild(cell);
  }
  root.appendChild(overview);

  if (tasks.length) {
    const block = doc.createElement("div");
    block.className = "execution-block";
    const sub = doc.createElement("h4");
    sub.textContent = "Implementation Tasks";
    block.appendChild(sub);
    for (const task of tasks.slice(0, 8)) {
      const row = doc.createElement("div");
      row.className = "execution-task";
      row.appendChild(line(doc, `${task.title} · ${task.status}`, task.risk === "high" ? "warning" : ""));
      row.appendChild(line(doc, `${task.risk.toUpperCase()} risk ${task.riskScore}/100 · ${task.files.length} file(s)`));
      if (task.verification?.status) row.appendChild(line(doc, `Verification ${task.verification.status}`, task.verification.status === "PASS" ? "pass" : "warning"));
      block.appendChild(row);
    }
    root.appendChild(block);
  }

  if (proposals.length) {
    const block = doc.createElement("div");
    block.className = "execution-block";
    const sub = doc.createElement("h4");
    sub.textContent = "Proposal Queue";
    block.appendChild(sub);
    for (const proposal of proposals.slice(0, 6)) {
      const row = doc.createElement("div");
      row.className = "execution-proposal";
      row.appendChild(line(doc, `${proposal.id} · ${proposal.status}`, proposal.status === "PROPOSED" ? "pending" : ""));
      row.appendChild(line(doc, `${proposal.operations.length} operation(s) · risk ${proposal.riskScore}/100`));
      block.appendChild(row);
    }
    root.appendChild(block);
  }

  if (results.length) {
    const block = doc.createElement("div");
    block.className = "execution-block";
    const sub = doc.createElement("h4");
    sub.textContent = "Execution History";
    block.appendChild(sub);
    for (const result of results.slice(0, 6)) {
      const row = doc.createElement("div");
      row.className = "execution-result";
      row.appendChild(line(doc, `${result.id} · ${result.verification.status} in ${result.durationMs}ms`, result.verification.status === "PASS" ? "pass" : "warning"));
      row.appendChild(line(doc, `${result.filesChanged.length} file(s) · ${result.verification.checks.join(" · ")}`));
      block.appendChild(row);
    }
    root.appendChild(block);
  }

  if (quality) {
    root.appendChild(
      line(
        doc,
        `Quality ${quality.quality}/100 · execution ${quality.executionReady ? "ready" : "blocked"}`,
        quality.executionReady ? "pass" : "warning",
      ),
    );
  }
  return root;
}
