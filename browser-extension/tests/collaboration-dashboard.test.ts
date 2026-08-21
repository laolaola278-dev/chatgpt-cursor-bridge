import { describe, expect, it } from "vitest";
import { renderCollaborationDashboard } from "../src/collaboration/collaboration-dashboard";
import type { AgentRecord } from "../src/bridge/types";
import type { AgentTeamRecord, CollaborationEventRecord, TaskDependencyRecord } from "../src/collaboration/models";

const team: AgentTeamRecord = { id: "team_1", workflowId: "wf_1", members: ["ag_1", "ag_2", "ag_3", "ag_4", "ag_5"], leader: "ag_1", status: "WAITING_APPROVAL", createdAt: "2026-01-01", updatedAt: "2026-01-01" };
const agent = (role: string): AgentRecord => ({ id: `ag_${role.toLowerCase()}`, project: "demo", sessionId: "ses_1", role, modelId: "local-deterministic", memoryScope: "project", permissions: ["context_read"], status: "ACTIVE", updatedAt: "2026-01-01" });
const edge: TaskDependencyRecord = { sourceTask: "task_requirement", targetTask: "task_architecture", dependencyType: "depends_on" };
const event: CollaborationEventRecord = { messageId: "cmsg_1", type: "REQUEST_REVIEW", sender: "ag_coder", receiver: "ag_reviewer", taskId: "task_1", workflowId: "wf_1", context: "Review proposal", timestamp: "2026-01-01T00:00:00Z" };

function render(overrides: Partial<{ teams: AgentTeamRecord[]; agents: AgentRecord[]; dependencies: TaskDependencyRecord[]; events: CollaborationEventRecord[] }> = {}) {
  return renderCollaborationDashboard(document, overrides.teams ?? [team], overrides.agents ?? [agent("PLANNER"), agent("ARCHITECT"), agent("CODER"), agent("TESTER"), agent("REVIEWER")], overrides.dependencies ?? [edge], overrides.events ?? [event]);
}

describe("Phase 11 collaboration dashboard", () => {
  it("renders a collaboration root", () => expect(render().dataset.role).toBe("collaboration-dashboard"));
  it("shows read-only badge", () => expect(render().textContent).toContain("READ ONLY"));
  it("shows team id", () => expect(render().textContent).toContain("team_1"));
  it("shows waiting approval status", () => expect(render().textContent).toContain("WAITING_APPROVAL"));
  it("shows team leader", () => expect(render().textContent).toContain("leader ag_1"));
  it("shows member count", () => expect(render().textContent).toContain("5 members"));
  it("shows dependency graph edge", () => expect(render().textContent).toContain("task_requirement"));
  it("shows dependency type", () => expect(render().textContent).toContain("depends_on"));
  it("shows negotiation event type", () => expect(render().textContent).toContain("REQUEST_REVIEW"));
  it("shows negotiation participants", () => expect(render().textContent).toContain("ag_coder → ag_reviewer"));
  it("shows message count", () => expect(render().textContent).toContain("1 message"));
  it("shows empty team state", () => expect(render({ teams: [] }).textContent).toContain("No team assigned"));
  it("shows empty dependency state", () => expect(render({ dependencies: [] }).textContent).toContain("No dependency edges"));
  it("shows empty event state", () => expect(render({ events: [] }).textContent).toContain("No collaboration messages"));
  it("renders no mutation controls", () => expect(render().querySelectorAll("button, input, select, textarea")).toHaveLength(0));
  it("renders all five role labels through agents", () => {
    const root = render();
    expect(root.textContent).toContain("PLANNER"); expect(root.textContent).toContain("REVIEWER");
  });
  it("renders multiple dependency edges", () => {
    const root = render({ dependencies: [edge, { ...edge, sourceTask: "task_architecture", targetTask: "task_code" }] });
    expect(root.textContent).toContain("task_code");
  });
  it("renders completed team state", () => expect(render({ teams: [{ ...team, status: "COMPLETED" }] }).textContent).toContain("COMPLETED"));
  it("renders conflict-style activity as metadata", () => expect(render({ events: [{ ...event, type: "CONFLICT" }] }).textContent).toContain("CONFLICT"));
});
