import type { ImpactReport, ProjectGraphResponse, ProjectMemoryHistoryResponse, ProjectProfile } from "./models";

function item(doc: Document, value: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `project-intelligence-item ${tone}`.trim();
  node.textContent = value;
  return node;
}

export function renderProjectIntelligenceDashboard(
  doc: Document,
  profile: ProjectProfile | null,
  graph: ProjectGraphResponse | null,
  impact: ImpactReport | null,
  memory: ProjectMemoryHistoryResponse | null,
): HTMLElement {
  const root = doc.createElement("section");
  root.className = "project-intelligence-dashboard";
  root.dataset.role = "project-intelligence-dashboard";

  const heading = doc.createElement("div");
  heading.className = "project-intelligence-heading";
  const title = doc.createElement("strong");
  title.textContent = "Project Intelligence";
  const badge = doc.createElement("span");
  badge.className = "project-intelligence-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  if (!profile) {
    root.appendChild(item(doc, "No indexed project yet. Code indexing remains approval-gated."));
    return root;
  }

  const overview = doc.createElement("div");
  overview.className = "project-intelligence-overview";
  overview.append(
    item(doc, `${profile.moduleCount} modules`),
    item(doc, `Complexity ${profile.complexityScore}/100`),
    item(doc, profile.architectureSummary),
    item(doc, profile.frameworks.join(" · ") || "Framework not detected"),
  );
  root.appendChild(overview);

  const columns = doc.createElement("div");
  columns.className = "project-intelligence-columns";

  const graphBlock = doc.createElement("div");
  graphBlock.className = "project-intelligence-block";
  const graphTitle = doc.createElement("h4");
  graphTitle.textContent = "Architecture graph";
  graphBlock.appendChild(graphTitle);
  graphBlock.appendChild(item(doc, graph ? `${graph.nodes.length} nodes · ${graph.edges.length} relations` : "Graph not built"));
  for (const node of graph?.nodes.slice(0, 5) ?? []) graphBlock.appendChild(item(doc, `${node.type} · ${node.label}`));
  columns.appendChild(graphBlock);

  const impactBlock = doc.createElement("div");
  impactBlock.className = "project-intelligence-block";
  const impactTitle = doc.createElement("h4");
  impactTitle.textContent = "Change impact";
  impactBlock.appendChild(impactTitle);
  impactBlock.appendChild(item(doc, impact ? `${impact.risk.toUpperCase()} · ${impact.affectedModules.length} affected modules` : "No change selected", impact?.risk === "high" ? "warning" : ""));
  for (const path of impact?.affectedModules.slice(0, 5) ?? []) impactBlock.appendChild(item(doc, path));
  columns.appendChild(impactBlock);

  const memoryBlock = doc.createElement("div");
  memoryBlock.className = "project-intelligence-block";
  const memoryTitle = doc.createElement("h4");
  memoryTitle.textContent = "Memory timeline";
  memoryBlock.appendChild(memoryTitle);
  for (const record of memory?.history.slice(0, 5) ?? []) memoryBlock.appendChild(item(doc, `${record.category} · ${record.updatedAt}`));
  if (!memory?.history.length) memoryBlock.appendChild(item(doc, "No project memory records"));
  columns.appendChild(memoryBlock);

  root.appendChild(columns);
  return root;
}
