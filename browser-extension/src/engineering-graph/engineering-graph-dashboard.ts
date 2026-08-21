import type { AgentCapabilityMetric, EngineeringGraphResponse, EvolutionTimelineEntry, FailurePattern } from "./models";

export interface EngineeringGraphDashboardData {
  graph: EngineeringGraphResponse | null;
  failures: FailurePattern[];
  timeline: EvolutionTimelineEntry[];
  capabilities: AgentCapabilityMetric[];
}

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `engineering-graph-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

export function renderEngineeringGraphDashboard(doc: Document, data: EngineeringGraphDashboardData): HTMLElement {
  const root = doc.createElement("section");
  root.className = "engineering-graph-dashboard";
  root.dataset.role = "engineering-graph-dashboard";
  const heading = doc.createElement("div");
  heading.className = "engineering-graph-heading";
  const title = doc.createElement("strong");
  title.textContent = "Engineering Intelligence Graph";
  const badge = doc.createElement("span");
  badge.className = "engineering-graph-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  const graph = data.graph;
  if (!graph && !data.failures.length && !data.timeline.length && !data.capabilities.length) {
    root.appendChild(line(doc, "No engineering intelligence recorded yet"));
    return root;
  }
  root.appendChild(line(doc, `${graph?.nodes.length ?? 0} graph nodes · ${graph?.edges.length ?? 0} relations · ${data.failures.length} failure patterns`));

  const blocks = doc.createElement("div");
  blocks.className = "engineering-graph-blocks";
  const graphBlock = doc.createElement("div");
  graphBlock.className = "engineering-graph-block";
  const graphTitle = doc.createElement("h4");
  graphTitle.textContent = "Knowledge Graph";
  graphBlock.appendChild(graphTitle);
  for (const node of (graph?.nodes ?? []).slice(0, 8)) graphBlock.appendChild(line(doc, `${node.type} · ${node.label}`));
  for (const edge of (graph?.edges ?? []).slice(0, 8)) graphBlock.appendChild(line(doc, `${edge.source} → ${edge.target} · ${edge.relation}`));
  if (!graph?.nodes.length) graphBlock.appendChild(line(doc, "Graph index pending approval", "warning"));
  blocks.appendChild(graphBlock);

  const failureBlock = doc.createElement("div");
  failureBlock.className = "engineering-graph-block";
  const failureTitle = doc.createElement("h4");
  failureTitle.textContent = "Failure Intelligence";
  failureBlock.appendChild(failureTitle);
  for (const pattern of data.failures.slice(0, 6)) failureBlock.appendChild(line(doc, `${pattern.category} · ${pattern.signature} · ${pattern.occurrences} occurrence(s)`, pattern.severity === "high" ? "warning" : ""));
  if (!data.failures.length) failureBlock.appendChild(line(doc, "No failure pattern detected"));
  blocks.appendChild(failureBlock);

  const metricBlock = doc.createElement("div");
  metricBlock.className = "engineering-graph-block";
  const metricTitle = doc.createElement("h4");
  metricTitle.textContent = "Agent Capability Metrics";
  metricBlock.appendChild(metricTitle);
  for (const metric of data.capabilities.slice(0, 6)) metricBlock.appendChild(line(doc, `${metric.agentId} · success ${metric.successRate}% · review ${metric.reviewScore}/100 · rollback ${metric.rollbackRate}%`));
  if (!data.capabilities.length) metricBlock.appendChild(line(doc, "No agent metrics recorded yet"));
  blocks.appendChild(metricBlock);

  const timelineBlock = doc.createElement("div");
  timelineBlock.className = "engineering-graph-block";
  const timelineTitle = doc.createElement("h4");
  timelineTitle.textContent = "Engineering Timeline";
  timelineBlock.appendChild(timelineTitle);
  for (const entry of data.timeline.slice(0, 6)) timelineBlock.appendChild(line(doc, `${entry.kind} · ${entry.title}`));
  if (!data.timeline.length) timelineBlock.appendChild(line(doc, "No evolution events recorded yet"));
  blocks.appendChild(timelineBlock);
  root.appendChild(blocks);
  return root;
}
