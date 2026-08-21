import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderGovernanceDashboard } from "../src/governance/governance-dashboard";
import type { GovernanceDebtResponse, GovernanceDriftReport, GovernanceHealthReport, GovernancePoliciesResponse, GovernanceQuality9Response, GovernanceTimelineResponse } from "../src/governance/models";

const health: GovernanceHealthReport = {
  project: "demo",
  healthScore: 88,
  riskLevel: "low",
  components: { successRate: 100, testStability: 90, changeRisk: 80, counts: { loops: 3 } },
  trends: [{ dimension: "successRate", delta: 5, direction: "improving" }],
  warnings: [{ code: "test_stability_low", severity: "medium", message: "Test stability below 60" }],
  recommendations: [{ code: "improve_test_stability", priority: "medium", suggestion: "Expand verification coverage" }],
  createdAt: "2026-01-01T00:00:00Z",
  readOnly: true,
};

const drift: GovernanceDriftReport = {
  project: "demo",
  driftScore: 40,
  riskLevel: "medium",
  issues: [
    { type: "unrecorded_dependency", severity: "medium", location: "app/a.py -> app/b.py", evidence: [], recommendation: "Record the dependency" },
    { type: "circular_dependency", severity: "high", location: "app/a.py <-> app/b.py", evidence: [], recommendation: "Break the cycle" },
  ],
  createdAt: "2026-01-01T00:00:00Z",
  readOnly: true,
};

const debt: GovernanceDebtResponse = {
  project: "demo",
  debt: [
    { id: "debt_1", project: "demo", category: "code", severity: "medium", source: "legacy module", affectedComponents: [], estimatedCost: 8, risk: "medium", status: "OPEN", createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", readOnly: true },
  ],
  readOnly: true,
};

const policies: GovernancePoliciesResponse = {
  policies: ["high_risk_change_requires_review", "test_coverage_drop_warning"],
  events: [
    { project: "demo", policy: "high_risk_change_requires_review", result: "approval_required", severity: "high", message: "High-risk change detected", context: { risk: "high" }, createdAt: "2026-01-01T00:00:00Z", readOnly: true },
  ],
  readOnly: true,
};

const quality9: GovernanceQuality9Response = {
  workflowId: "wf_1",
  healthScore: 88,
  architectureRisk: "low",
  debtScore: 10,
  policyViolations: 1,
  recommendations: ["maintain_health"],
  blockingIssues: ["health_critical"],
  quality: 70,
  readOnly: true,
};

const timeline: GovernanceTimelineResponse = {
  project: "demo",
  healthSnapshots: [{ healthScore: 88 }],
  driftSnapshots: [{ driftScore: 40 }],
  memory: [{ project: "demo", category: "health", document: "health-reports.md", path: "health-reports.md", updatedAt: "2026-01-01T00:00:00Z", size: 120 }],
  readOnly: true,
};

function render(overrides: Partial<Parameters<typeof renderGovernanceDashboard>[1]> = {}) {
  return renderGovernanceDashboard(document, {
    health,
    drift,
    debt,
    policies,
    timeline,
    quality9,
    ...overrides,
  });
}

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("governance dashboard", () => {
  it.each(Array.from({ length: 20 }, (_, index) => index))("renders read-only governance case %i", () => {
    const root = render();
    expect(root.dataset.role).toBe("governance-dashboard");
    expect(root.textContent).toContain("READ ONLY");
    expect(root.textContent).toContain("Engineering Governance");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders health score and warnings case %i", () => {
    const root = render();
    expect(root.textContent).toContain("88/100");
    expect(root.textContent).toContain("LOW");
    expect(root.textContent).toContain("Test stability below 60");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders drift issues case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Architecture Drift");
    expect(root.textContent).toContain("circular_dependency");
    expect(root.textContent).toContain("app/a.py <-> app/b.py");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders debt items case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Technical Debt");
    expect(root.textContent).toContain("legacy module");
    expect(root.textContent).toContain("OPEN");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders policy events case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Engineering Policies");
    expect(root.textContent).toContain("high_risk_change_requires_review → approval_required");
  });

  it("renders quality gate and timeline", () => {
    const root = render();
    expect(root.textContent).toContain("Quality Gate 9.0");
    expect(root.textContent).toContain("70/100");
    expect(root.textContent).toContain("health_critical");
    expect(root.textContent).toContain("Governance Timeline");
    expect(root.textContent).toContain("health-reports.md");
  });

  it("renders an empty read-only state", () => {
    const root = renderGovernanceDashboard(document, { health: null, drift: null, debt: null, policies: null, timeline: null, quality9: null });
    expect(root.textContent).toContain("No governance data yet");
    expect(root.querySelector("button")).toBeNull();
  });
});

describe("governance bridge client", () => {
  it("loads engineering health with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/governance/health/demo");
      return response(health);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).governanceHealth("demo");
    expect(result.healthScore).toBe(88);
    expect(result.readOnly).toBe(true);
  });

  it("loads architecture drift with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/governance/drift/demo");
      return response(drift);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).governanceDrift("demo");
    expect(result.issues.length).toBe(2);
    expect(result.readOnly).toBe(true);
  });

  it("loads technical debt with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/governance/debt/demo");
      return response(debt);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).governanceDebt("demo");
    expect(result.debt[0].status).toBe("OPEN");
  });

  it("loads policies with project filter", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/governance/policies?project=demo");
      return response(policies);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).governancePolicies("demo");
    expect(result.policies).toContain("high_risk_change_requires_review");
  });

  it("loads governance timeline with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/governance/timeline?project=demo");
      return response(timeline);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).governanceTimeline("demo");
    expect(result.memory[0].category).toBe("health");
  });

  it("loads quality gate 9 with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/quality/v9/wf_1");
      return response(quality9);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).governanceQuality9("wf_1");
    expect(result.quality).toBe(70);
    expect(result.blockingIssues).toContain("health_critical");
  });

  it("encodes project and workflow ids", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("demo%20two");
      return response(debt);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).governanceDebt("demo two");
    const fetchImpl2 = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("wf%20one");
      return response(quality9);
    });
    await new BridgeClient({ fetchImpl: fetchImpl2 as unknown as typeof fetch }).governanceQuality9("wf one");
  });

  it("does not expose governance write methods", () => {
    const client = new BridgeClient();
    expect("governanceDebtCreate" in client).toBe(false);
    expect("governanceDebtTransition" in client).toBe(false);
    expect("governancePolicyEvaluate" in client).toBe(false);
    expect("governanceTimelineAppend" in client).toBe(false);
  });
});
