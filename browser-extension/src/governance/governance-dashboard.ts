import type {
  GovernanceDebtResponse,
  GovernanceDriftReport,
  GovernanceHealthReport,
  GovernancePoliciesResponse,
  GovernanceQuality9Response,
  GovernanceTimelineResponse,
} from "./models";

export interface GovernanceDashboardData {
  health: GovernanceHealthReport | null;
  drift: GovernanceDriftReport | null;
  debt: GovernanceDebtResponse | null;
  policies: GovernancePoliciesResponse | null;
  timeline: GovernanceTimelineResponse | null;
  quality9: GovernanceQuality9Response | null;
}

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `governance-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

function block(doc: Document, title: string): HTMLElement {
  const wrapper = doc.createElement("div");
  wrapper.className = "governance-block";
  const heading = doc.createElement("h4");
  heading.textContent = title;
  wrapper.appendChild(heading);
  return wrapper;
}

function score(doc: Document, className: string, value: string): HTMLElement {
  const node = doc.createElement("div");
  node.className = className;
  node.textContent = value;
  return node;
}

/** Read-only governance overview: health, drift, debt, policy, quality gate. */
export function renderGovernanceDashboard(doc: Document, data: GovernanceDashboardData): HTMLElement {
  const root = doc.createElement("section");
  root.className = "governance-dashboard";
  root.dataset.role = "governance-dashboard";
  const heading = doc.createElement("div");
  heading.className = "governance-heading";
  const title = doc.createElement("strong");
  title.textContent = "Engineering Governance";
  const badge = doc.createElement("span");
  badge.className = "governance-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  const { health, drift, debt, policies, quality9, timeline } = data;
  if (!health && !drift && !debt && !policies && !quality9) {
    root.appendChild(line(doc, "No governance data yet. Connect to a Local Bridge with Phase 21."));
    return root;
  }

  // Health score + risk + warnings + recommendations.
  if (health) {
    const healthBlock = block(doc, "Engineering Health");
    const stats = doc.createElement("div");
    stats.className = "governance-stats";
    const scoreNode = score(doc, "governance-score", `${health.healthScore}/100`);
    const riskNode = score(doc, "governance-score", health.riskLevel.toUpperCase());
    stats.append(scoreNode, riskNode);
    healthBlock.appendChild(stats);
    for (const trend of health.trends.slice(0, 4)) {
      const arrow = trend.direction === "improving" ? "▲" : trend.direction === "declining" ? "▼" : "■";
      healthBlock.appendChild(line(doc, `${arrow} ${trend.dimension} ${trend.delta > 0 ? "+" : ""}${trend.delta}`));
    }
    for (const warning of health.warnings.slice(0, 4)) {
      healthBlock.appendChild(line(doc, `⚠ ${warning.message}`, "warning"));
    }
    for (const rec of health.recommendations.slice(0, 3)) {
      healthBlock.appendChild(line(doc, `→ ${rec.suggestion}`));
    }
    root.appendChild(healthBlock);
  }

  // Architecture drift.
  if (drift) {
    const driftBlock = block(doc, "Architecture Drift");
    driftBlock.appendChild(line(doc, `Drift ${drift.driftScore}/100 · ${drift.riskLevel.toUpperCase()} risk`, drift.driftScore >= 50 ? "warning" : ""));
    for (const issue of drift.issues.slice(0, 4)) {
      driftBlock.appendChild(line(doc, `${issue.type} · ${issue.severity} · ${issue.location}`, issue.severity === "high" ? "warning" : ""));
    }
    if (!drift.issues.length) driftBlock.appendChild(line(doc, "No drift issues detected"));
    root.appendChild(driftBlock);
  }

  // Technical debt.
  if (debt) {
    const debtBlock = block(doc, "Technical Debt");
    for (const item of debt.debt.slice(0, 4)) {
      debtBlock.appendChild(line(doc, `${item.category} · ${item.severity} · ${item.status} · est ${item.estimatedCost}h · ${item.source}`));
    }
    if (!debt.debt.length) debtBlock.appendChild(line(doc, "No open debt items"));
    root.appendChild(debtBlock);
  }

  // Engineering policies + recorded events.
  if (policies) {
    const policyBlock = block(doc, "Engineering Policies");
    policyBlock.appendChild(line(doc, policies.policies.join(" · ") || "No policies registered"));
    for (const event of policies.events.slice(0, 3)) {
      const tone = event.result === "approval_required" ? "warning" : event.result === "warning" ? "pending" : "pass";
      policyBlock.appendChild(line(doc, `${event.policy} → ${event.result}`, tone));
    }
    root.appendChild(policyBlock);
  }

  // Quality Gate 9.0.
  if (quality9) {
    const qualityBlock = block(doc, "Quality Gate 9.0");
    qualityBlock.appendChild(line(doc, `Quality ${quality9.quality}/100 · health ${quality9.healthScore} · debt ${quality9.debtScore} · ${quality9.policyViolations} policy violation(s)`));
    for (const issue of quality9.blockingIssues.slice(0, 3)) qualityBlock.appendChild(line(doc, `blocked: ${issue}`, "warning"));
    if (!quality9.blockingIssues.length) qualityBlock.appendChild(line(doc, "No blocking issues", "pass"));
    root.appendChild(qualityBlock);
  }

  // Governance timeline memory.
  if (timeline) {
    const memoryBlock = block(doc, "Governance Timeline");
    for (const record of timeline.memory.slice(0, 4)) {
      memoryBlock.appendChild(line(doc, `${record.category} · ${record.document}`));
    }
    if (!timeline.memory.length) memoryBlock.appendChild(line(doc, "No governance memory yet"));
    root.appendChild(memoryBlock);
  }

  return root;
}
