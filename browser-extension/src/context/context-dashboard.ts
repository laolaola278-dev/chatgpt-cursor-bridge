import type { DevContextResponse } from "./types";

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `developer-context-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

function summaryRow(doc: Document, label: string, value: string, tone = ""): HTMLElement {
  const row = doc.createElement("div");
  row.className = "developer-context-summary-row";
  const key = doc.createElement("span");
  key.className = "developer-context-summary-key";
  key.textContent = label;
  const val = doc.createElement("span");
  val.className = "developer-context-summary-value";
  val.textContent = value;
  row.append(key, val);
  if (tone) row.dataset.tone = tone;
  return row;
}

/**
 * Read-only Developer Context dashboard (Phase 29).
 *
 * Displays the assembled context bundle (project / file / symbol / dependency /
 * git / test) plus a context preview list. Context items can be selected for
 * the next chat message and removed again, but nothing here can execute,
 * apply, fix, approve, or mutate the project.
 */
export function renderContextDashboard(
  doc: Document,
  devContext: DevContextResponse | null,
  selection: string[],
  onToggle: (id: string) => void,
): HTMLElement {
  const root = doc.createElement("section");
  root.className = "developer-context-dashboard";
  root.dataset.role = "developer-context-dashboard";

  const heading = doc.createElement("div");
  heading.className = "developer-context-heading";
  const title = doc.createElement("strong");
  title.textContent = "Developer Context";
  const badge = doc.createElement("span");
  badge.className = "developer-context-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  if (!devContext) {
    root.appendChild(line(doc, "No developer context loaded. Select a project and refresh."));
    return root;
  }

  const meta = doc.createElement("div");
  meta.className = "developer-context-meta";
  meta.append(
    summaryRow(doc, "Project", devContext.project),
    summaryRow(doc, "Agent", devContext.agent),
    summaryRow(doc, "Size", `${(devContext.size / 1024).toFixed(1)} KB`),
    summaryRow(doc, "Truncated", devContext.truncated ? "yes" : "no", devContext.truncated ? "warn" : ""),
    summaryRow(doc, "Security filtering", devContext.securityFiltering ? "active" : "off", "ok"),
  );
  root.appendChild(meta);

  // -- Context preview -------------------------------------------------
  const preview = doc.createElement("div");
  preview.className = "developer-context-preview";
  const previewTitle = doc.createElement("h4");
  previewTitle.textContent = "Context Preview (user sends)";
  preview.appendChild(previewTitle);
  const note = doc.createElement("div");
  note.className = "developer-context-note";
  note.textContent = "Nothing is sent automatically. Select items below to attach them to your next message; remove any item before sending. Tool proposals still require human approval.";
  preview.appendChild(note);

  const project = devContext.projectContext;
  const sections: Array<{ id: string; label: string; detail: string }> = [
    {
      id: "project",
      label: "Project context",
      detail: project ? `${project.fileCount} files · ${Object.keys(project.languages).join(", ") || "no languages"} · ${project.packageManagers.join(", ") || "no package managers"}` : "unavailable",
    },
    {
      id: "files",
      label: "Files",
      detail: devContext.files ? `${devContext.files.length} file(s)` : "unavailable",
    },
    {
      id: "symbols",
      label: "Symbols",
      detail: devContext.symbols ? `${devContext.symbols.total} symbol(s)` : "unavailable",
    },
    {
      id: "dependencies",
      label: "Dependencies",
      detail: devContext.dependencies ? `${devContext.dependencies.total} dependency(ies)` : "unavailable",
    },
    {
      id: "git",
      label: "Git",
      detail: devContext.git ? `branch ${devContext.git.branch} · ${devContext.git.clean ? "clean" : `${devContext.git.changedFiles.length} changed`} · ${devContext.git.commits.length} commit(s)` : "unavailable",
    },
    {
      id: "tests",
      label: "Tests / build",
      detail: devContext.tests
        ? `test ${devContext.tests.testStatus?.status ?? "unknown"} · build ${devContext.tests.buildStatus?.status ?? "unknown"}`
        : "unavailable",
    },
  ];

  for (const section of sections) {
    const row = doc.createElement("div");
    row.className = "developer-context-preview-row";
    const toggle = doc.createElement("input");
    toggle.type = "checkbox";
    toggle.dataset.role = "context-select";
    toggle.dataset.contextId = section.id;
    toggle.checked = selection.includes(section.id);
    toggle.addEventListener("change", () => onToggle(section.id));
    const label = doc.createElement("span");
    label.className = "developer-context-preview-label";
    label.textContent = section.label;
    const detail = doc.createElement("span");
    detail.className = "developer-context-preview-detail";
    detail.textContent = section.detail;
    row.append(toggle, label, detail);
    preview.appendChild(row);
  }

  const selected = doc.createElement("div");
  selected.className = "developer-context-selected";
  selected.textContent = selection.length
    ? `${selection.length} context item(s) ready to attach: ${selection.join(", ")}`
    : "No context items selected";
  preview.appendChild(selected);
  root.appendChild(preview);

  // -- Detail blocks ----------------------------------------------------
  const blocks = doc.createElement("div");
  blocks.className = "developer-context-blocks";

  if (project) {
    const block = doc.createElement("div");
    block.className = "developer-context-block";
    const blockTitle = doc.createElement("h4");
    blockTitle.textContent = "Project";
    block.appendChild(blockTitle);
    block.append(
      line(doc, `Workspace: ${project.workspaceRoot}`),
      line(doc, `Languages: ${Object.entries(project.languages).map(([lang, count]) => `${lang} (${count})`).join(", ") || "none"}`),
      line(doc, `Files: ${project.fileCount}`),
      line(doc, `Package managers: ${project.packageManagers.join(", ") || "none"}`),
      line(doc, `Test: ${project.testStatus?.status ?? "unknown"} · Build: ${project.buildStatus?.status ?? "unknown"}`),
    );
    blocks.appendChild(block);
  }

  if (devContext.git) {
    const block = doc.createElement("div");
    block.className = "developer-context-block";
    const blockTitle = doc.createElement("h4");
    blockTitle.textContent = "Git (read-only)";
    block.appendChild(blockTitle);
    block.append(
      line(doc, `Branch: ${devContext.git.branch}`),
      line(doc, `State: ${devContext.git.clean ? "clean" : "dirty"}`),
      line(doc, `Changed: ${devContext.git.changedFiles.slice(0, 5).join(", ") || "none"}${devContext.git.changedFiles.length > 5 ? " …" : ""}`),
      line(doc, `Diff: ${devContext.git.diffTruncated ? `${devContext.git.diff.length} chars (truncated)` : `${devContext.git.diff.length} chars`}`),
    );
    blocks.appendChild(block);
  }

  if (devContext.symbols && devContext.symbols.symbols.length) {
    const block = doc.createElement("div");
    block.className = "developer-context-block";
    const blockTitle = doc.createElement("h4");
    blockTitle.textContent = "Symbols";
    block.appendChild(blockTitle);
    for (const symbol of devContext.symbols.symbols.slice(0, 6)) {
      block.append(line(doc, `${symbol.type} ${symbol.name}${symbol.exported ? " (exported)" : ""} — ${symbol.file}:${symbol.line}`));
    }
    if (devContext.symbols.symbols.length > 6) block.append(line(doc, `… ${devContext.symbols.symbols.length - 6} more`));
    blocks.appendChild(block);
  }

  if (devContext.dependencies && devContext.dependencies.dependencies.length) {
    const block = doc.createElement("div");
    block.className = "developer-context-block";
    const blockTitle = doc.createElement("h4");
    blockTitle.textContent = "Dependencies";
    block.appendChild(blockTitle);
    for (const dep of devContext.dependencies.dependencies.slice(0, 6)) {
      block.append(line(doc, `${dep.name}@${dep.version} (${dep.type}) — ${dep.sourceFile}`));
    }
    if (devContext.dependencies.dependencies.length > 6) block.append(line(doc, `… ${devContext.dependencies.dependencies.length - 6} more`));
    blocks.appendChild(block);
  }

  if (devContext.tests) {
    const block = doc.createElement("div");
    block.className = "developer-context-block";
    const blockTitle = doc.createElement("h4");
    blockTitle.textContent = "Tests / build (read-only)";
    block.appendChild(blockTitle);
    block.append(
      line(doc, `Last test result: ${devContext.tests.testStatus?.status ?? "not recorded"}`),
      line(doc, `Build status: ${devContext.tests.buildStatus?.status ?? "not recorded"}`),
    );
    blocks.appendChild(block);
  }

  root.appendChild(blocks);

  const footer = doc.createElement("div");
  footer.className = "developer-context-footer";
  footer.textContent = "Read-only context. No execution, apply, fix, auto-approve, or source modification.";
  root.appendChild(footer);
  return root;
}
