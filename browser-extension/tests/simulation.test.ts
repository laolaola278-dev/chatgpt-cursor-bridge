import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderSimulationDashboard } from "../src/simulation/simulation-dashboard";
import type {
  EngineeringPlan,
  SimulationEvaluation,
  SimulationQuality6,
  SimulationRecord,
  SimulationScenario,
} from "../src/simulation/models";

const simulation: SimulationRecord = {
  id: "sim_1",
  project: "demo",
  problem: "UserService has high coupling",
  status: "COMPLETED",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  history: [{ status: "DRAFT", at: "2026-01-01T00:00:00Z" }],
  readOnly: true,
};

const scenario: SimulationScenario = {
  id: "scenario_1",
  simulationId: "sim_1",
  name: "Module Extraction",
  type: "refactor",
  changes: ["create auth service", "move token logic"],
  affectedFiles: ["src/user.ts", "src/auth.ts"],
  dependentModules: ["src/api.ts"],
  affectedTests: ["tests/user.test.ts"],
  workflowStages: ["IMPLEMENTATION", "TESTING", "REVIEW"],
  memoryImpacts: ["ADR required"],
  riskScore: 44,
  impactScore: 62,
  risk: "medium",
  status: "CANDIDATE",
  readOnly: true,
};

const evaluation: SimulationEvaluation = {
  scenario: "scenario_1",
  score: 82,
  risk: "medium",
  advantages: ["lower coupling"],
  disadvantages: ["larger change"],
  factors: { scope: 20, risk: 15, coverage: 18, rollback: 10 },
  readOnly: true,
};

const plan: EngineeringPlan = {
  id: "plan_1",
  simulationId: "sim_1",
  scenarioId: "scenario_1",
  content: "# Engineering Plan\n\n## Problem\nHigh coupling\n\n## Rollback Plan\nRestore the previous boundary.",
  status: "DRAFT",
  createdAt: "2026-01-01T00:00:00Z",
  readOnly: true,
};

const quality: SimulationQuality6 = {
  quality: 88,
  simulationConfidence: 0.84,
  alternativeCoverage: 100,
  riskPredictionAccuracy: 80,
  planCompleteness: 90,
  missingInformation: ["database migration impact"],
  readOnly: true,
};

function render(
  current: SimulationRecord | null = simulation,
  scenarios: SimulationScenario[] = [scenario],
  evaluations: SimulationEvaluation[] = [evaluation],
  plans: EngineeringPlan[] = [plan],
  gate: SimulationQuality6 | null = quality,
): HTMLElement {
  return renderSimulationDashboard(document, current, scenarios, evaluations, plans, gate);
}

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("Phase 14 simulation dashboard", () => {
  it("has a stable role marker", () => {
    expect(render().dataset.role).toBe("simulation-dashboard");
  });

  it("shows the read-only badge", () => {
    expect(render().textContent).toContain("SIMULATION · READ ONLY");
  });

  it("shows the current problem", () => {
    expect(render().textContent).toContain("Problem · UserService has high coupling");
  });

  it("shows simulation status", () => {
    expect(render().textContent).toContain("COMPLETED");
  });

  it("shows candidate count", () => {
    expect(render().textContent).toContain("1 candidate solutions");
  });

  it("shows scenario name", () => {
    expect(render().textContent).toContain("Module Extraction");
  });

  it("shows scenario type", () => {
    expect(render().textContent).toContain("refactor");
  });

  it("shows scenario risk", () => {
    expect(render().textContent).toContain("MEDIUM risk");
  });

  it("shows scenario impact", () => {
    expect(render().textContent).toContain("impact 62/100");
  });

  it("shows affected file count", () => {
    expect(render().textContent).toContain("2 files");
  });

  it("shows dependent module count", () => {
    expect(render().textContent).toContain("1 dependents");
  });

  it("shows evaluation score", () => {
    expect(render().textContent).toContain("Score 82/100");
  });

  it("shows evaluation advantage", () => {
    expect(render().textContent).toContain("lower coupling");
  });

  it("shows a plan preview", () => {
    expect(render().textContent).toContain("# Engineering Plan");
  });

  it("shows quality score", () => {
    expect(render().textContent).toContain("Quality 88/100");
  });

  it("shows confidence as a percentage", () => {
    expect(render().textContent).toContain("confidence 84%");
  });

  it("renders no-simulation state", () => {
    expect(render(null, [], [], [], null).textContent).toContain("No simulation created yet");
  });

  it("renders no-scenario state", () => {
    expect(render(simulation, [], [], [], null).textContent).toContain("No scenarios analyzed yet");
  });

  it("does not render an empty plan block", () => {
    expect(render(simulation, [scenario], [evaluation], [], quality).querySelector(".simulation-plan")).toBeNull();
  });

  it("does not render quality when absent", () => {
    expect(render(simulation, [scenario], [evaluation], [], null).textContent).not.toContain("Quality");
  });

  it("limits candidates to four", () => {
    const many = Array.from({ length: 6 }, (_, i) => ({ ...scenario, id: `s${i}`, name: `Scenario ${i}` }));
    expect(render(simulation, many, [], [], null).querySelectorAll(".simulation-candidate")).toHaveLength(4);
  });

  it("does not add buttons", () => {
    expect(render().querySelectorAll("button")).toHaveLength(0);
  });

  it("does not add links", () => {
    expect(render().querySelectorAll("a")).toHaveLength(0);
  });

  it("does not add form controls", () => {
    expect(render().querySelectorAll("input,select,textarea")).toHaveLength(0);
  });

  it("does not expose apply wording", () => {
    expect(render().textContent?.toLowerCase()).not.toContain("apply scenario");
  });

  it("does not expose execute wording", () => {
    expect(render().textContent?.toLowerCase()).not.toContain("execute plan");
  });

  it("does not mutate the simulation record", () => {
    const before = JSON.stringify(simulation);
    render();
    expect(JSON.stringify(simulation)).toBe(before);
  });

  it("does not mutate scenario records", () => {
    const before = JSON.stringify(scenario);
    render();
    expect(JSON.stringify(scenario)).toBe(before);
  });

  it("does not mutate evaluation records", () => {
    const before = JSON.stringify(evaluation);
    render();
    expect(JSON.stringify(evaluation)).toBe(before);
  });

  it("marks high risk candidates", () => {
    const high = { ...scenario, risk: "high" };
    expect(render(simulation, [high], [], [], null).querySelector(".warning")).not.toBeNull();
  });

  it("keeps low risk candidates visible", () => {
    expect(render(simulation, [{ ...scenario, risk: "low" }], [], [], null).textContent).toContain("LOW risk");
  });

  const statuses = ["DRAFT", "ANALYZING", "COMPLETED", "REVIEWING", "APPROVED", "REJECTED", "ARCHIVED"];
  it.each(statuses)("renders status %s", (status) => {
    expect(render({ ...simulation, status }).textContent).toContain(status);
  });

  const risks = ["low", "medium", "high"];
  it.each(risks)("renders risk %s", (risk) => {
    expect(render(simulation, [{ ...scenario, risk }], [], [], null).textContent).toContain(`${risk.toUpperCase()} risk`);
  });

  const qualities = [0, 25, 50, 75, 100];
  it.each(qualities)("renders quality %s", (value) => {
    expect(render(simulation, [scenario], [evaluation], [], { ...quality, quality: value }).textContent).toContain(`Quality ${value}/100`);
  });
});

describe("Phase 14 Simulation BridgeClient reads", () => {
  it("loads simulation details with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/simulation/sim_1");
      expect(init?.method ?? "GET").toBe("GET");
      return response(simulation);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulation("sim_1");
  });

  it("loads scenarios with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/simulation/sim_1/scenarios");
      return response({ simulationId: "sim_1", scenarios: [scenario], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulationScenarios("sim_1");
  });

  it("loads evaluations with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/simulation/sim_1/evaluation");
      return response({ simulationId: "sim_1", evaluations: [evaluation], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulationEvaluation("sim_1");
  });

  it("loads plans from the read-only detail endpoint", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/simulation/sim_1");
      return response({ ...simulation, plans: [plan] });
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulationPlans("sim_1");
    expect(result.plans).toEqual([plan]);
    expect(result.readOnly).toBe(true);
  });

  it("loads Quality Gate 6 with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/quality/v6/wf_1");
      return response(quality);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulationQuality("wf_1");
  });

  it("loads planning memory history with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/memory/planning/history?project=demo");
      return response({ project: "demo", history: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).planningMemoryHistory("demo");
  });

  it("encodes simulation ids", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("sim%20one");
      return response({ ...simulation, id: "sim one" });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulation("sim one");
  });

  it("encodes workflow ids for quality", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("wf%20one");
      return response(quality);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulationQuality("wf one");
  });

  it("preserves read-only scenario response", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ simulationId: "sim_1", scenarios: [], readOnly: true })) as unknown as typeof fetch });
    expect((await client.simulationScenarios("sim_1")).readOnly).toBe(true);
  });

  it("preserves read-only evaluation response", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ simulationId: "sim_1", evaluations: [], readOnly: true })) as unknown as typeof fetch });
    expect((await client.simulationEvaluation("sim_1")).readOnly).toBe(true);
  });

  it("preserves quality missing information", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response(quality)) as unknown as typeof fetch });
    expect((await client.simulationQuality("wf_1")).missingInformation).toEqual(["database migration impact"]);
  });

  it("does not expose apply scenario", () => {
    const client = new BridgeClient();
    expect("applyScenario" in client).toBe(false);
  });

  it("does not expose execute plan", () => {
    const client = new BridgeClient();
    expect("executePlan" in client).toBe(false);
  });

  it("does not expose simulation approval", () => {
    const client = new BridgeClient();
    expect("approveSimulation" in client).toBe(false);
  });

  it("does not expose scenario mutation", () => {
    const client = new BridgeClient();
    expect("updateScenario" in client).toBe(false);
  });

  it("does not expose plan mutation", () => {
    const client = new BridgeClient();
    expect("writePlan" in client).toBe(false);
  });

  const ids = ["sim_1", "sim_abc", "phase-14", "long-simulation-id", "中文"];
  it.each(ids)("supports simulation id %s", async (id) => {
    const fetchImpl = vi.fn(async () => response({ ...simulation, id }));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulation(id);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  const workflows = ["wf_1", "wf_review", "phase14", "workflow-two", "中文工作流"];
  it.each(workflows)("supports workflow id %s", async (workflowId) => {
    const fetchImpl = vi.fn(async () => response(quality));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).simulationQuality(workflowId);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
