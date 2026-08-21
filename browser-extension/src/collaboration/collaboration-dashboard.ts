import type { AgentRecord } from "../bridge/types";
import type { AgentTeamRecord, CollaborationEventRecord, TaskDependencyRecord } from "./models";

function row(doc: Document, value: string, tone = ""): HTMLElement {
  const node = doc.createElement("div"); node.className = `collaboration-row ${tone}`.trim(); node.textContent = value; return node;
}

export function renderCollaborationDashboard(doc: Document, teams: AgentTeamRecord[], agents: AgentRecord[], dependencies: TaskDependencyRecord[], events: CollaborationEventRecord[]): HTMLElement {
  const root = doc.createElement("section"); root.className = "collaboration-dashboard"; root.dataset.role = "collaboration-dashboard";
  const heading = doc.createElement("div"); heading.className = "collaboration-heading";
  const title = doc.createElement("strong"); title.textContent = "Agent Collaboration";
  const badge = doc.createElement("span"); badge.className = "collaboration-badge"; badge.textContent = "READ ONLY"; heading.append(title, badge); root.appendChild(heading);

  const summary = doc.createElement("div"); summary.className = "collaboration-summary";
  summary.append(row(doc, `${teams.length} team${teams.length === 1 ? "" : "s"}`), row(doc, `${agents.length} agents`), row(doc, `${dependencies.length} dependency${dependencies.length === 1 ? "" : "ies"}`), row(doc, `${events.length} messages`)); root.appendChild(summary);

  const teamBlock = doc.createElement("div"); teamBlock.className = "collaboration-block";
  const teamTitle = doc.createElement("h4"); teamTitle.textContent = "Agent team"; teamBlock.appendChild(teamTitle);
  if (!teams.length) teamBlock.appendChild(row(doc, "No team assigned"));
  for (const team of teams.slice(0, 3)) teamBlock.appendChild(row(doc, `${team.id} · ${team.status} · leader ${team.leader} · ${team.members.length} members`, team.status === "WAITING_APPROVAL" ? "warning" : ""));  root.appendChild(teamBlock);

  const roster = doc.createElement("div"); roster.className = "collaboration-block";
  const rosterTitle = doc.createElement("h4"); rosterTitle.textContent = "Agent roster"; roster.appendChild(rosterTitle);
  if (!agents.length) roster.appendChild(row(doc, "No active agents"));
  for (const agent of agents.slice(0, 8)) roster.appendChild(row(doc, `${agent.role} · ${agent.status} · ${agent.id}`));
  root.appendChild(roster);

  const graph = doc.createElement("div");
 graph.className = "collaboration-block";
  const graphTitle = doc.createElement("h4"); graphTitle.textContent = "Task dependency graph"; graph.appendChild(graphTitle);
  if (!dependencies.length) graph.appendChild(row(doc, "No dependency edges"));
  for (const edge of dependencies.slice(0, 8)) graph.appendChild(row(doc, `${edge.sourceTask}  →  ${edge.targetTask} · ${edge.dependencyType}`));
  root.appendChild(graph);

  const activity = doc.createElement("div"); activity.className = "collaboration-block";
  const activityTitle = doc.createElement("h4"); activityTitle.textContent = "Negotiation activity"; activity.appendChild(activityTitle);
  if (!events.length) activity.appendChild(row(doc, "No collaboration messages"));
  for (const event of events.slice(-5).reverse()) activity.appendChild(row(doc, `${event.type} · ${event.sender} → ${event.receiver} · task ${event.taskId}`));
  root.appendChild(activity);
  return root;
}
