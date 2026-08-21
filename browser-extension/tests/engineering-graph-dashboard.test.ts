import { describe, expect, it } from "vitest";

import { renderEngineeringGraphDashboard } from "../src/engineering-graph/engineering-graph-dashboard";
import type { AgentCapabilityMetric, EngineeringGraphResponse, EvolutionTimelineEntry, FailurePattern } from "../src/engineering-graph/models";

const graph: EngineeringGraphResponse = {
  project: "demo",
  nodes: [
    { id: "workflow:wf_1", type: "workflow", project: "demo", label: "Workflow", metadata: {}, createdAt: "2026-01-01" },
    { id: "execution_loop:loop_1", type: "execution_loop", project: "demo", label: "Loop", metadata: {}, createdAt: "2026-01-01" },
  ],
  edges: [{ source: "workflow:wf_1", target: "execution_loop:loop_1", relation: "depends_on", project: "demo", metadata: {}, createdAt: "2026-01-01" }],
  readOnly: true,
};

const failure: FailurePattern = {
  id: "failure_1",
  project: "demo",
  category: "test_failure",
  signature: "verification_failed",
  occurrences: 2,
  severity: "medium",
  evidence: [],
  createdAt: "2026-01-01",
  readOnly: true,
};

const timeline: EvolutionTimelineEntry = {
  id: "evo_1",
  project: "demo",
  kind: "learning",
  title: "Rollback lesson",
  content: "Keep snapshots",
  sourceId: "loop_1",
  createdAt: "2026-01-01",
  readOnly: true,
};

const capability: AgentCapabilityMetric = {
  agentId: "ag_coder",
  tasksCompleted: 8,
  failedTasks: 2,
  successRate: 80,
  reviewScore: 92,
  averageQuality: 88,
  rollbackRate: 10,
  failurePatterns: [failure],
  readOnly: true,
};

function render() {
  return renderEngineeringGraphDashboard(document, {
    graph,
    failures: [failure],
    timeline: [timeline],
    capabilities: [capability],
  });
}

describe("engineering graph dashboard", () => {
  it.each(Array.from({ length: 20 }, (_, index) => index))("renders graph read-only case %i", () => {
    const root = render();
    expect(root.dataset.role).toBe("engineering-graph-dashboard");
    expect(root.textContent).toContain("READ ONLY");
    expect(root.textContent).toContain("Knowledge Graph");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders failure pattern case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Failure Intelligence");
    expect(root.textContent).toContain("test_failure");
    expect(root.textContent).toContain("verification_failed");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders timeline case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Engineering Timeline");
    expect(root.textContent).toContain("Rollback lesson");
    expect(root.textContent).toContain("learning");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders capability metric case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Agent Capability Metrics");
    expect(root.textContent).toContain("ag_coder");
    expect(root.textContent).toContain("success 80%");
    expect(root.textContent).toContain("review 92/100");
  });

  it("renders an empty read-only state", () => {
    const root = renderEngineeringGraphDashboard(document, { graph: null, failures: [], timeline: [], capabilities: [] });
    expect(root.textContent).toContain("No engineering intelligence recorded yet");
    expect(root.querySelector("button")).toBeNull();
  });
});
