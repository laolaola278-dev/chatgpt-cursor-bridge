import { describe, expect, it } from "vitest";

import type { ProjectContextResponse } from "../src/context/types";
import { renderWorkflowDashboard } from "../src/dashboard/workflow-dashboard";
import { renderStageTimeline } from "../src/workflow/timeline";

const context: ProjectContextResponse = {
  project: "demo",
  currentWorkflow: {
    id: "wf_abcdef0123456789",
    project: "demo",
    name: "Ship context",
    description: "Context",
    currentStage: "IMPLEMENTATION",
    status: "IMPLEMENTING",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    stages: [
      {
        id: "stg_abcdef0123456789",
        workflowId: "wf_abcdef0123456789",
        stageType: "REQUIREMENT",
        status: "APPROVED",
        reportTitle: "Requirements",
        report: "## Goal\n\nShip context",
        approvalRequestId: "req_abcdef0123456789",
        actionIds: ["req_1", "req_2"],
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      },
      {
        id: "stg_1234567890abcdef",
        workflowId: "wf_abcdef0123456789",
        stageType: "IMPLEMENTATION",
        status: "IN_PROGRESS",
        actionIds: [],
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      },
    ],
  },
  currentStage: null,
  recentDecisions: [],
  openTasks: ["Restore context on reconnect"],
  lastTestResult: { status: "passed", stageId: "stg_test", report: "passed", updatedAt: "2026-01-01T00:00:00Z" },
  gitStatus: { clean: false, modified: ["src/context.ts"] },
  pendingApprovals: [{ requestId: "req_pending" }],
  recentChanges: [{ action: "workflow_stage_start", result: "success" }],
  snapshot: { path: "/workspace/context/demo/current.json", updatedAt: "2026-01-01T00:00:00Z" },
};

describe("Phase 7 workflow dashboard", () => {
  it("renders project context, status cards, timeline and tasks", () => {
    const dashboard = renderWorkflowDashboard(document, context);
    expect(dashboard.dataset.role).toBe("workflow-dashboard");
    expect(dashboard.textContent).toContain("Ship context");
    expect(dashboard.textContent).toContain("IMPLEMENTATION");
    expect(dashboard.textContent).toContain("Restore context on reconnect");
    expect(dashboard.querySelectorAll(".dashboard-stat")).toHaveLength(6);
    expect(dashboard.querySelector("[data-role='stage-timeline']")).not.toBeNull();
  });

  it("exposes stage reports and approval/action metadata", () => {
    const timeline = renderStageTimeline(document, context.currentWorkflow!);
    expect(timeline.querySelector(".stage-report summary")?.textContent).toBe("View report");
    expect(timeline.textContent).toContain("2 actions");
    expect(timeline.textContent).toContain("Approval Approved");
    expect(timeline.querySelector("[data-stage='REQUIREMENT']")?.className).toContain("done");
  });

  it("renders agent status and selected model without adding controls", () => {
    const dashboard = renderWorkflowDashboard(document, context, {
      agents: [{
        id: "ag_coder123456789",
        project: "demo",
        sessionId: "ses_1234567890",
        role: "CODER",
        modelId: "local/coder-v1",
        memoryScope: "demo/src",
        permissions: ["change_propose"],
        status: "ACTIVE",
        updatedAt: "2026-01-01T00:00:00Z",
      }],
      modelSelection: {
        classification: { taskType: "review", confidence: 0.9, signals: ["review"] },
        model: {
          id: "local/reviewer-v1",
          provider: "local",
          displayName: "Local Reviewer",
          capabilities: ["review"],
          contextWindow: 32000,
          enabled: true,
        },
      },
    });
    expect(dashboard.textContent).toContain("Multi-agent runtime");
    expect(dashboard.textContent).toContain("CODER · ACTIVE · local/coder-v1");
    expect(dashboard.textContent).toContain("Local Reviewer");
    expect(dashboard.querySelectorAll("button")).toHaveLength(0);
  });

  it("renders a safe empty state without a project", () => {
    const dashboard = renderWorkflowDashboard(document, null);
    expect(dashboard.textContent).toContain("Select a project");
    expect(dashboard.querySelector("[data-role='stage-timeline']")).toBeNull();
  });
});
