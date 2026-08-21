import { describe, expect, it } from "vitest";
import { renderRuntimeDashboard } from "../src/runtime/runtime-dashboard";
import type { RuntimeEvent, RuntimeRecord, TaskRecord } from "../src/runtime/models";

const runtime: RuntimeRecord = { id: "rt_1", agentId: "ag_1", sessionId: "ses_1", workflowId: "wf_1", stageId: "stg_1", state: "RECOVERED", createdAt: "2026-01-01", updatedAt: "2026-01-01", history: [] };
const task: TaskRecord = { id: "task_1", workflowId: "wf_1", stageId: "stg_1", agentId: "ag_1", priority: 4, status: "PENDING", context: {}, createdAt: "2026-01-01", updatedAt: "2026-01-01" };
const event: RuntimeEvent = { eventId: "evt_1", timestamp: "2026-01-01T00:00:00Z", type: "runtime.created", source: "test", payload: {}, auditId: "aud_1", checksum: "valid" };

function render(overrides: Partial<{ runtimes: RuntimeRecord[]; tasks: TaskRecord[]; events: RuntimeEvent[]; quality: { workflowId: string; qualityScore: number; risk: string; blockingIssues: string[]; checks: Record<string, unknown> } | null }> = {}) {
  return renderRuntimeDashboard(document, overrides.runtimes ?? [runtime], overrides.tasks ?? [task], overrides.events ?? [event], overrides.quality === undefined ? { workflowId: "wf_1", qualityScore: 82, risk: "low", blockingIssues: [], checks: {} } : overrides.quality);
}

describe("Phase 10 runtime dashboard", () => {
  it("renders runtime, task and event status", () => {
    const root = render();
    expect(root.dataset.role).toBe("runtime-dashboard");
    expect(root.textContent).toContain("RECOVERED");
    expect(root.textContent).toContain("PENDING");
    expect(root.textContent).toContain("runtime.created");
    expect(root.textContent).toContain("82/100");
  });

  it("renders empty state and no buttons", () => {
    const root = render({ runtimes: [], tasks: [], events: [], quality: null });
    expect(root.textContent).toContain("No runtime records");
    expect(root.querySelectorAll("button")).toHaveLength(0);
  });

  it("marks recovered runtimes as requiring attention", () => {
    const root = render({ tasks: [], events: [], quality: null });
    expect(root.querySelector(".warning")?.textContent).toContain("RECOVERED");
  });

  it("shows the read-only badge", () => {
    expect(render().textContent).toContain("READ ONLY");
  });

  it("shows pending task count", () => {
    expect(render().textContent).toContain("1 pending tasks");
  });

  it("shows event source", () => {
    expect(render().textContent).toContain("test");
  });

  it("shows quality risk details", () => {
    const root = render({ quality: { workflowId: "wf_1", qualityScore: 41, risk: "high", blockingIssues: ["test_result_failed"], checks: {} } });
    expect(root.textContent).toContain("HIGH");
    expect(root.textContent).toContain("test_result_failed");
  });

  it("does not expose mutation controls for quality findings", () => {
    const root = render({ quality: { workflowId: "wf_1", qualityScore: 41, risk: "critical", blockingIssues: ["approval required"], checks: {} } });
    expect(root.querySelectorAll("button, input, select, textarea")).toHaveLength(0);
  });

  it("renders completed runtime state", () => {
    const completed = { ...runtime, state: "COMPLETED" as const };
    expect(render({ runtimes: [completed], tasks: [], events: [], quality: null }).textContent).toContain("COMPLETED");
  });

  it("renders waiting approval task state", () => {
    const waiting = { ...task, status: "WAITING_APPROVAL" as const };
    expect(render({ runtimes: [], tasks: [waiting], events: [], quality: null }).textContent).toContain("WAITING_APPROVAL");
  });

  it("renders multiple recent events", () => {
    const second = { ...event, eventId: "evt_2", type: "task.created" };
    const root = render({ events: [event, second], quality: null });
    expect(root.textContent).toContain("task.created");
    expect(root.textContent).toContain("runtime.created");
  });

  it("renders task priority in the queue", () => {
    expect(render().textContent).toContain("priority 4");
  });

  it("omits quality details when no report is available", () => {
    const root = render({ quality: null });
    expect(root.textContent).not.toContain("Quality gate");
  });
});
