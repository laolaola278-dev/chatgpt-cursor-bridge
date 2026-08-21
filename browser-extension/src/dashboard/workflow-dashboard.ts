import type { AgentRecord, ModelRouteResponse } from "../bridge/types";
import type { ProjectContextResponse } from "../context/types";
import { renderStageTimeline } from "../workflow/timeline";

function text(doc: Document, value: unknown, className = ""): HTMLSpanElement {
  const node = doc.createElement("span");
  if (className) node.className = className;
  node.textContent = String(value ?? "—");
  return node;
}

function stat(doc: Document, title: string, value: unknown, detail: string): HTMLElement {
  const card = doc.createElement("div");
  card.className = "dashboard-stat";
  const label = doc.createElement("span");
  label.className = "dashboard-label";
  label.textContent = title;
  const strong = doc.createElement("strong");
  strong.appendChild(text(doc, value));
  const small = doc.createElement("small");
  small.textContent = detail;
  card.append(label, strong, small);
  return card;
}

function list(doc: Document, values: string[], empty: string): HTMLElement {
  const wrapper = doc.createElement("div");
  wrapper.className = "dashboard-list";
  if (!values.length) {
    wrapper.textContent = empty;
    return wrapper;
  }
  for (const value of values) {
    const item = doc.createElement("div");
    item.className = "dashboard-list-item";
    item.textContent = value;
    wrapper.appendChild(item);
  }
  return wrapper;
}

export function renderWorkflowDashboard(
  doc: Document,
  context: ProjectContextResponse | null,
  runtime: { agents: AgentRecord[]; modelSelection: ModelRouteResponse | null } = { agents: [], modelSelection: null },
): HTMLElement {
  const dashboard = doc.createElement("section");
  dashboard.className = "workflow-dashboard";
  dashboard.dataset.role = "workflow-dashboard";

  const heading = doc.createElement("div");
  heading.className = "dashboard-heading";
  const title = doc.createElement("div");
  title.className = "dashboard-title";
  title.textContent = "Workflow Dashboard";
  const badge = doc.createElement("span");
  badge.className = "dashboard-badge";
  badge.textContent = context ? "LIVE CONTEXT" : "NO PROJECT";
  heading.append(title, badge);
  dashboard.appendChild(heading);

  if (!context) {
    const empty = doc.createElement("div");
    empty.className = "dashboard-empty";
    empty.textContent = "Select a project and connect to load workflow context.";
    dashboard.appendChild(empty);
    return dashboard;
  }

  const workflow = context.currentWorkflow;
  const stats = doc.createElement("div");
  stats.className = "dashboard-stats";
  stats.append(
    stat(doc, "Project", context.project, "active workspace"),
    stat(doc, "Workflow", workflow?.name ?? "None", workflow?.status ?? "No workflow"),
    stat(
      doc,
      "Current stage",
      context.currentStage?.stageType ?? workflow?.currentStage ?? "—",
      context.currentStage?.status ?? workflow?.status ?? "Pending",
    ),
    stat(doc, "Pending approvals", context.pendingApprovals.length, "explicit decisions required"),
    stat(doc, "Test result", context.lastTestResult?.status ?? "—", context.lastTestResult ? "latest TESTING report" : "no result yet"),
    stat(doc, "Git", context.gitStatus.clean === true ? "Clean" : context.gitStatus.status ?? "Changes", "read-only status"),
  );
  dashboard.appendChild(stats);

  const agentSection = doc.createElement("div");
  agentSection.className = "dashboard-agents";
  const agentTitle = doc.createElement("h4");
  agentTitle.textContent = "Multi-agent runtime";
  agentSection.appendChild(agentTitle);
  const agentSummary = doc.createElement("div");
  agentSummary.className = "agent-summary";
  const model = runtime.modelSelection?.model;
  agentSummary.textContent = model
    ? `Router: ${model.displayName} · ${runtime.modelSelection?.classification.taskType}`
    : "Router ready · no task selection";
  agentSection.appendChild(agentSummary);
  const agentValues = runtime.agents.slice(0, 6).map((agent) => `${agent.role} · ${agent.status} · ${agent.modelId}`);
  agentSection.appendChild(list(doc, agentValues, "No agents assigned"));
  dashboard.appendChild(agentSection);

  if (workflow) {
    const timelineTitle = doc.createElement("h4");
    timelineTitle.textContent = "Stage timeline";
    dashboard.append(timelineTitle, renderStageTimeline(doc, workflow));
  }

  const lower = doc.createElement("div");
  lower.className = "dashboard-lower";
  const tasks = doc.createElement("div");
  tasks.className = "dashboard-column";
  const tasksTitle = doc.createElement("h4");
  tasksTitle.textContent = "Open tasks";
  tasks.append(tasksTitle, list(doc, context.openTasks, "No open tasks"));
  const changes = doc.createElement("div");
  changes.className = "dashboard-column";
  const changesTitle = doc.createElement("h4");
  changesTitle.textContent = "Recent changes";
  changes.append(changesTitle, list(doc, context.recentChanges.slice(-5).map((entry) => `${entry.action ?? "event"} · ${entry.result ?? ""}`), "No recent changes"));

  const sessions = doc.createElement("div");
  sessions.className = "dashboard-column";
  const sessionsTitle = doc.createElement("h4");
  sessionsTitle.textContent = "Agent sessions";
  const sessionValues = (context.activeSessions ?? []).slice(0, 5).map((session) => {
    const id = String(session.id ?? "session").slice(-12);
    return `${id} · ${String(session.status ?? "UNKNOWN")}`;
  });
  sessions.append(sessionsTitle, list(doc, sessionValues, "No sessions"));

  lower.append(tasks, changes, sessions);
  dashboard.appendChild(lower);
  return dashboard;
}
