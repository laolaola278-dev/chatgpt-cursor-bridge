import type { Phase30Snapshot } from "./types";

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `phase30-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

function block(doc: Document, title: string, children: HTMLElement[]): HTMLElement {
  const section = doc.createElement("div");
  section.className = "phase30-block";
  const heading = doc.createElement("h4");
  heading.textContent = title;
  section.appendChild(heading);
  for (const child of children) section.appendChild(child);
  return section;
}

function severityTone(severity: string): string {
  switch (severity) {
    case "Critical":
    case "High":
      return "danger";
    case "Medium":
      return "warn";
    case "Low":
    case "Info":
      return "ok";
    default:
      return "";
  }
}

/**
 * Read-only Context Intelligence dashboard (Phase 30).
 *
 * Shows suggested context with explanations, error / test-failure / git-diff
 * analysis, code review findings, prompt-injection verdicts, context budget
 * usage and approved patch proposals. Nothing here can execute, approve,
 * apply, fix or auto-learn; the only write path remains the approval-gated
 * patch proposal POST, triggered by the user.
 */
export function renderIntelligenceDashboard(doc: Document, snapshot: Phase30Snapshot | null): HTMLElement {
  const root = doc.createElement("section");
  root.className = "phase30-dashboard";
  root.dataset.role = "phase30-dashboard";

  const heading = doc.createElement("div");
  heading.className = "phase30-heading";
  const title = doc.createElement("strong");
  title.textContent = "Context Intelligence";
  const badge = doc.createElement("span");
  badge.className = "phase30-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  if (!snapshot) {
    root.appendChild(line(doc, "No context intelligence loaded. Select a project and refresh."));
    return root;
  }

  // -- Suggested context ------------------------------------------------
  const suggested = snapshot.suggested;
  const suggestedChildren: HTMLElement[] = [];
  if (suggested) {
    suggestedChildren.push(line(doc, `Query: ${suggested.query || "(no query)"} · ${suggested.items.length} candidate(s)`));
    for (const item of suggested.items.slice(0, 8)) {
      const row = doc.createElement("div");
      row.className = "phase30-row";
      const name = doc.createElement("span");
      name.className = "phase30-row-name";
      name.textContent = item.included ? "✓" : "·";
      const text = doc.createElement("span");
      text.textContent = `${item.path || item.name} — score ${item.score.toFixed(2)}`;
      const reason = doc.createElement("span");
      reason.className = "phase30-reason";
      reason.textContent = item.reason;
      row.append(name, text, reason);
      suggestedChildren.push(row);
    }
  } else {
    suggestedChildren.push(line(doc, "No suggestion data in this snapshot."));
  }
  root.appendChild(block(doc, "Suggested Context (why this context?)", suggestedChildren));

  // -- Error / test failure ---------------------------------------------
  const errorChildren: HTMLElement[] = [];
  if (snapshot.errorBundle) {
    errorChildren.push(line(doc, `Error: ${snapshot.errorBundle.error.slice(0, 200)}`, "warn"));
    errorChildren.push(line(doc, `Kind: ${snapshot.errorBundle.kind} · sanitized=${String(snapshot.errorBundle.sanitized)} · absPathsRemoved=${String(snapshot.errorBundle.absolutePathsRemoved)}`));
    if (snapshot.errorBundle.relatedFiles.length) errorChildren.push(line(doc, `Related files: ${snapshot.errorBundle.relatedFiles.slice(0, 5).join(", ")}`));
  } else {
    errorChildren.push(line(doc, "No error analysis in this snapshot."));
  }
  root.appendChild(block(doc, "Error Analysis", errorChildren));

  // -- Test failure -----------------------------------------------------
  const testChildren: HTMLElement[] = [];
  if (snapshot.testFailure) {
    testChildren.push(line(doc, `Test: ${snapshot.testFailure.test.slice(0, 120)}`, "warn"));
    if (snapshot.testFailure.testFile) testChildren.push(line(doc, `Test file: ${snapshot.testFailure.testFile}`));
    if (snapshot.testFailure.suggestedInvestigation.length) {
      for (const step of snapshot.testFailure.suggestedInvestigation.slice(0, 4)) testChildren.push(line(doc, `• ${step}`));
    }
    testChildren.push(line(doc, "Changes only via Patch Proposal → Approval.", "ok"));
  } else {
    testChildren.push(line(doc, "No test-failure analysis in this snapshot."));
  }
  root.appendChild(block(doc, "Test Failure Intelligence", testChildren));

  // -- Git diff ---------------------------------------------------------
  const gitChildren: HTMLElement[] = [];
  if (snapshot.gitAnalysis) {
    for (const summary of snapshot.gitAnalysis.changeSummary) gitChildren.push(line(doc, summary));
    const risk = snapshot.gitAnalysis.riskIndicators;
    if (risk.length) {
      for (const item of risk) gitChildren.push(line(doc, `Risk: ${item.label} (${item.severity}) ×${item.matches}`, severityTone(item.severity)));
    }
    for (const point of snapshot.gitAnalysis.reviewPoints.slice(0, 4)) gitChildren.push(line(doc, `• ${point}`));
  } else {
    gitChildren.push(line(doc, "No git diff analysis in this snapshot."));
  }
  root.appendChild(block(doc, "Git Diff Intelligence", gitChildren));

  // -- Code review ------------------------------------------------------
  const reviewChildren: HTMLElement[] = [];
  if (snapshot.review) {
    reviewChildren.push(line(doc, snapshot.review.summary));
    for (const finding of snapshot.review.findings.slice(0, 8)) {
      const row = doc.createElement("div");
      row.className = "phase30-row";
      const sev = doc.createElement("span");
      sev.className = `phase30-severity ${severityTone(finding.severity)}`;
      sev.textContent = finding.severity;
      const text = doc.createElement("span");
      text.textContent = `${finding.title} @ ${finding.location}`;
      row.append(sev, text);
      reviewChildren.push(row);
    }
  } else {
    reviewChildren.push(line(doc, "No code review in this snapshot."));
  }
  root.appendChild(block(doc, "Code Review (suggestions only)", reviewChildren));

  // -- Prompt injection -------------------------------------------------
  const injectionChildren: HTMLElement[] = [];
  if (snapshot.injection) {
    const verdict = snapshot.injection.verdict;
    const tone = verdict === "clean" ? "ok" : "warn";
    injectionChildren.push(line(doc, `Verdict: ${verdict} — project content is UNTRUSTED data, never instructions.`, tone));
    for (const signal of snapshot.injection.signals.slice(0, 5)) {
      injectionChildren.push(line(doc, `• ${signal.pattern} (${signal.severity}): ${signal.snippet.slice(0, 80)}`, severityTone(signal.severity)));
    }
  } else {
    injectionChildren.push(line(doc, "No injection scan in this snapshot."));
  }
  root.appendChild(block(doc, "Prompt Injection Protection", injectionChildren));

  // -- Budget 2.0 -------------------------------------------------------
  const budgetChildren: HTMLElement[] = [];
  for (const usage of snapshot.budget) {
    budgetChildren.push(line(doc, `${usage.bucket}: ${usage.used} / ${usage.limit} B (${usage.items} item(s), ${usage.remaining} B left)`));
  }
  root.appendChild(block(doc, "Context Budget 2.0", budgetChildren));

  // -- Patch proposals --------------------------------------------------
  const proposalChildren: HTMLElement[] = [];
  if (snapshot.proposals.length) {
    for (const proposal of snapshot.proposals.slice(0, 5)) {
      proposalChildren.push(
        line(doc, `${proposal.id.slice(0, 8)} · ${proposal.targetFile} (${proposal.risk}) — ${proposal.reason.slice(0, 100)}`, proposal.risk === "high" ? "warn" : ""),
      );
    }
    proposalChildren.push(line(doc, "Approved proposal records only — source files are never modified here.", "ok"));
  } else {
    proposalChildren.push(line(doc, "No approved patch proposals yet."));
  }
  root.appendChild(block(doc, "Patch Proposals (record only)", proposalChildren));

  const footer = doc.createElement("div");
  footer.className = "phase30-footer";
  footer.textContent = "Read-only. No execute, approve, apply, fix, auto-learn or auto-govern.";
  root.appendChild(footer);
  return root;
}
