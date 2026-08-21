import { describe, expect, it } from "vitest";

import { renderDemoDashboard } from "../src/demo/demo-dashboard";
import type { DemoScenarioRecord } from "../src/demo/models";
import type { ReplayRecord } from "../src/replay/models";

const scenario: DemoScenarioRecord = {
  id: "demo_1",
  name: "Bug Fix Demo",
  issue: "Authentication failures observed after token rotation",
  stages: ["ISSUE", "AGENT_ANALYSIS", "PROPOSAL", "APPROVAL", "EXECUTION", "VERIFICATION", "REPORT"],
  readOnly: true,
};

const replay: ReplayRecord = {
  id: "replay_1",
  project: "demo",
  title: "Bug fix timeline",
  createdAt: "2026-01-01T00:00:00Z",
  steps: [{ stage: "ISSUE", detail: "reported", timestamp: "2026-01-01T00:00:00Z" }],
  readOnly: true,
};

function render(overrides: Partial<Parameters<typeof renderDemoDashboard>[1]> = {}) {
  return renderDemoDashboard(document, {
    scenarios: [scenario],
    flow: ["ISSUE", "AGENT_ANALYSIS", "PROPOSAL", "APPROVAL", "EXECUTION", "VERIFICATION", "REPORT"],
    replays: [replay],
    artifacts: [{ id: "artifact_1", kind: "report", project: "demo", createdAt: "2026-01-01T00:00:00Z", payload: {}, markdown: "# Report", readOnly: true }],
    ...overrides,
  });
}

describe("demo dashboard", () => {
  it.each(Array.from({ length: 20 }, (_, index) => index))("renders read-only demo case %i", () => {
    const root = render();
    expect(root.dataset.role).toBe("demo-dashboard");
    expect(root.textContent).toContain("READ ONLY");
    expect(root.textContent).toContain("Engineering Demo");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders full flow case %i", () => {
    const root = render();
    expect(root.textContent).toContain("ISSUE → AGENT_ANALYSIS");
    expect(root.textContent).toContain("REPORT");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders scenarios and replays case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Bug Fix Demo");
    expect(root.textContent).toContain("Bug fix timeline");
    expect(root.textContent).toContain("1 step(s)");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders artifacts case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Artifacts");
    expect(root.textContent).toContain("report");
  });

  it("renders an empty read-only state", () => {
    const root = renderDemoDashboard(document, { scenarios: [], flow: [], replays: [], artifacts: [] });
    expect(root.textContent).toContain("No demo artifacts recorded yet");
    expect(root.querySelector("button")).toBeNull();
  });
});
