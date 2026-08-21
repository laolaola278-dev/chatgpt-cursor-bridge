import type { EngineeringMetrics, ExecutionDagReadyResponse, ExecutionDagRecord, ExecutionLoopContext, ExecutionLoopHistoryEntry, ExecutionLoopQuality8, ExecutionLoopRecord } from "./models";

export interface Phase17DashboardData {
  dags?: ExecutionDagRecord[];
  dagReady?: ExecutionDagReadyResponse | null;
  metrics?: EngineeringMetrics | null;
  context?: ExecutionLoopContext | null;
}

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `loop-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

const STATUS_ORDER: string[] = [
  "CREATED",
  "PLANNING",
  "PROPOSAL_READY",
  "WAITING_APPROVAL",
  "EXECUTING",
  "VERIFYING",
  "COMPLETED",
  "FAILED",
  "ROLLED_BACK",
  "CANCELLED",
];

function toneFor(status: string): string {
  if (status === "COMPLETED" || status === "PROPOSAL_READY") return "pass";
  if (status === "FAILED" || status === "ROLLED_BACK" || status === "CANCELLED") return "warning";
  if (status === "WAITING_APPROVAL") return "pending";
  return "";
}

export function renderExecutionLoopDashboard(
  doc: Document,
  loops: ExecutionLoopRecord[],
  quality: ExecutionLoopQuality8 | null,
  phase17: Phase17DashboardData = {},
): HTMLElement {
  const root = doc.createElement("section");
  root.className = "execution-loop-dashboard";
  root.dataset.role = "execution-loop-dashboard";

  const heading = doc.createElement("div");
  heading.className = "execution-loop-heading";
  const title = doc.createElement("strong");
  title.textContent = "Execution Loop";
  const badge = doc.createElement("span");
  badge.className = "execution-loop-badge";
  badge.textContent = "APPROVAL CONTROLLED · READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  if (!loops.length && !quality && !phase17.dags?.length && !phase17.metrics && !phase17.context) {
    root.appendChild(line(doc, "No execution loop yet"));
    return root;
  }

  const active = loops.filter((loop) => loop.status === "EXECUTING" || loop.status === "VERIFYING" || loop.status === "WAITING_APPROVAL").length;
  const completed = loops.filter((loop) => loop.status === "COMPLETED").length;
  root.appendChild(line(doc, `${loops.length} loop(s) · ${active} active · ${completed} completed`));

  if (loops.length) {
    const block = doc.createElement("div");
    block.className = "execution-loop-block";
    const sub = doc.createElement("h4");
    sub.textContent = "Loop Timeline";
    block.appendChild(sub);
    for (const loop of loops.slice(0, 4)) {
      const card = doc.createElement("div");
      card.className = "execution-loop-card";
      card.appendChild(line(doc, `${loop.id} · ${loop.status}`, toneFor(loop.status)));
      card.appendChild(line(doc, `workflow ${loop.workflowId ?? "standalone"} · plan ${loop.planId} · ${loop.taskIds.length} task(s)`));
      const steps = doc.createElement("div");
      steps.className = "execution-loop-steps";
      const ordered = [...loop.history].sort((a, b) => a.at.localeCompare(b.at));
      const seen = new Set<string>();
      for (const entry of ordered) {
        if (seen.has(entry.status)) continue;
        seen.add(entry.status);
        const step = doc.createElement("span");
        step.className = `execution-loop-step ${toneFor(entry.status)}`;
        step.textContent = entry.status;
        step.title = `${entry.at} · ${entry.detail}`;
        steps.appendChild(step);
      }
      card.appendChild(steps);
      if (loop.proposalId) card.appendChild(line(doc, `proposal ${loop.proposalId}`));
      if (loop.resultId) card.appendChild(line(doc, `result ${loop.resultId}`));
      if (loop.rollback?.count != null) card.appendChild(line(doc, `rollback restored ${String(loop.rollback.count)} file(s)`));
      if (loop.memoryProposalId) card.appendChild(line(doc, `learning memory proposal queued`, "pending"));
      block.appendChild(card);
    }
    root.appendChild(block);
  }

  if (quality) {
    const block = doc.createElement("div");
    block.className = "execution-loop-block";
    const sub = doc.createElement("h4");
    sub.textContent = "Quality Gate 8.0";
    block.appendChild(sub);
    const report = doc.createElement("div");
    report.className = "execution-loop-quality";
    report.appendChild(
      line(
        doc,
        `Quality ${quality.quality}/100 · ${quality.executionReady ? "execution ready" : "execution blocked"}`,
        quality.executionReady ? "pass" : "warning",
      ),
    );
    report.appendChild(line(doc, `confidence ${quality.confidence}/100 · risk ${quality.riskLevel.toUpperCase()}`));
    if (quality.blockingIssues.length) {
      report.appendChild(line(doc, `blocking: ${quality.blockingIssues.join(", ")}`, "warning"));
    } else {
      report.appendChild(line(doc, "no blocking issues"));
    }
    const testLabel = quality.testResult === "not_run" ? "not run" : quality.testResult ?? "not run";
    report.appendChild(line(doc, `rollback ${quality.rollbackCapability ? "ready" : "unavailable"} · tests ${testLabel}`));
    report.appendChild(line(doc, `recommendation: ${quality.recommendation}`));
    block.appendChild(report);
    root.appendChild(block);
  }

  if (phase17.dags?.length || phase17.metrics || phase17.context) {
    const orchestration = doc.createElement("div");
    orchestration.className = "execution-loop-block execution-orchestration-block";
    const title = doc.createElement("h4");
    title.textContent = "Execution Orchestration · Phase 17";
    orchestration.appendChild(title);

    const dags = phase17.dags ?? [];
    if (dags.length) {
      const dag = dags[0];
      orchestration.appendChild(line(doc, `${dags.length} execution DAG(s) · ${dag.id} · ${dag.status}`, dag.status === "COMPLETED" ? "pass" : ""));
      orchestration.appendChild(line(doc, `${dag.loopIds.length} loop(s) · ${dag.edges.length} dependency edge(s)`));
      for (const edge of dag.edges.slice(0, 6)) {
        orchestration.appendChild(line(doc, `${edge.sourceLoop} → ${edge.targetLoop} · ${edge.dependencyType}`));
      }
      if (phase17.dagReady) {
        const ready = phase17.dagReady.readyLoops;
        orchestration.appendChild(line(doc, ready.length ? `ready: ${ready.join(", ")}` : "ready: none; dependencies pending", ready.length ? "pending" : "warning"));
      }
    } else {
      orchestration.appendChild(line(doc, "No execution DAGs recorded yet"));
    }

    if (phase17.metrics) {
      const metrics = phase17.metrics;
      orchestration.appendChild(line(doc, `Engineering metrics · ${metrics.totalLoops} loops · success ${metrics.successRate}% · rollback ${metrics.rollbackRate}%`));
      orchestration.appendChild(line(doc, `quality ${metrics.averageQuality}/100 · duration ${metrics.averageDurationMs}ms · recovered ${metrics.recovered}`));
      orchestration.appendChild(line(doc, `risk low ${metrics.riskDistribution.low ?? 0} · medium ${metrics.riskDistribution.medium ?? 0} · high ${metrics.riskDistribution.high ?? 0}`));
    }

    const context = phase17.context;
    if (context) {
      const incoming = context.dagRelations.incoming.length;
      const outgoing = context.dagRelations.outgoing.length;
      orchestration.appendChild(line(doc, `cross-loop context · ${context.relatedLoops.length} related · ${incoming} incoming · ${outgoing} outgoing`));
      const evidence = context.verification?.evidence;
      if (evidence && typeof evidence === "object") {
        const bundle = evidence as Record<string, unknown>;
        const testResult = typeof bundle.testResult === "string" ? bundle.testResult : "not_run";
        const qualityScore = typeof bundle.qualityScore === "number" ? bundle.qualityScore : "n/a";
        const riskScore = typeof bundle.riskScore === "number" ? bundle.riskScore : "n/a";
        orchestration.appendChild(line(doc, `evidence bundle · tests ${testResult} · quality ${qualityScore} · risk ${riskScore}`));
      } else {
        orchestration.appendChild(line(doc, "evidence bundle · not available yet"));
      }
      if (context.loop.status === "RECOVERED") {
        orchestration.appendChild(line(doc, "runtime recovered · explicit human confirmation required", "warning"));
      }
    }
    root.appendChild(orchestration);
  }

  return root;
}

export function renderExecutionLoopTimeline(doc: Document, loopId: string, timeline: ExecutionLoopHistoryEntry[]): HTMLElement {
  const root = doc.createElement("div");
  root.className = "execution-loop-block";
  root.dataset.role = "execution-loop-timeline";
  const sub = doc.createElement("h4");
  sub.textContent = `Timeline · ${loopId}`;
  root.appendChild(sub);
  if (!timeline.length) {
    root.appendChild(line(doc, "No timeline events yet"));
    return root;
  }
  const ordered = [...timeline].sort((a, b) => a.at.localeCompare(b.at));
  for (const entry of ordered.slice(-8)) {
    const row = doc.createElement("div");
    row.className = "execution-loop-step-row";
    row.appendChild(line(doc, `${entry.at} · ${entry.status}`, toneFor(entry.status)));
    if (entry.detail) row.appendChild(line(doc, entry.detail));
    root.appendChild(row);
  }
  return root;
}

export const LOOP_STATUS_ORDER = STATUS_ORDER;
