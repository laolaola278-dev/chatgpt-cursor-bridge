import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderExecutionLoopDashboard } from "../src/execution-loop/execution-loop-dashboard";
import type { EngineeringMetrics, ExecutionDagRecord, ExecutionLoopContext, ExecutionLoopQuality8, ExecutionLoopRecord } from "../src/execution-loop/models";

const quality: ExecutionLoopQuality8 = {
  quality: 92,
  executionReady: true,
  confidence: 90,
  riskLevel: "low",
  blockingIssues: [],
  rollbackCapability: true,
  testResult: "passed",
  recommendation: "continue",
  readOnly: true,
};

const loop: ExecutionLoopRecord = {
  id: "eloop_a",
  project: "demo",
  planId: "plan_a",
  workflowId: "wf_a",
  taskIds: ["task_a"],
  proposalId: "proposal_a",
  resultId: "result_a",
  approvalId: "approval_a",
  status: "VERIFYING",
  verification: {
    status: "PASS",
    evidence: { testResult: "passed", qualityScore: 92, riskScore: 18 },
  },
  quality,
  rollback: {},
  memoryProposalId: null,
  createdAt: "2026-02-01T00:00:00Z",
  updatedAt: "2026-02-01T00:00:01Z",
  history: [{ status: "VERIFYING", at: "2026-02-01T00:00:01Z", detail: "checking" }],
  readOnly: true,
};

const dag: ExecutionDagRecord = {
  id: "edag_a",
  project: "demo",
  loopIds: ["eloop_a", "eloop_b"],
  edges: [{ sourceLoop: "eloop_a", targetLoop: "eloop_b", dependencyType: "depends_on" }],
  status: "ACTIVE",
  createdAt: "2026-02-01T00:00:00Z",
  updatedAt: "2026-02-01T00:00:01Z",
  history: [],
  loopStatuses: { eloop_a: "VERIFYING", eloop_b: "PLANNING" },
  readOnly: true,
};

const metrics: EngineeringMetrics = {
  project: "demo",
  totalLoops: 4,
  statusCounts: { VERIFYING: 1, COMPLETED: 2, RECOVERED: 1 },
  completed: 2,
  failed: 0,
  rolledBack: 0,
  recovered: 1,
  cancelled: 0,
  successRate: 100,
  rollbackRate: 0,
  averageQuality: 88,
  averageDurationMs: 1200,
  riskDistribution: { low: 2, medium: 1, high: 1 },
  generatedAt: "2026-02-01T00:00:01Z",
  readOnly: true,
};

const context: ExecutionLoopContext = {
  loop,
  tasks: [{ id: "task_a" }],
  proposal: { id: "proposal_a" },
  result: { id: "result_a" },
  verification: loop.verification,
  quality: {},
  timeline: loop.history,
  dagRelations: {
    incoming: [],
    outgoing: [{ ...dag.edges[0], dagId: dag.id }],
  },
  relatedLoops: [{ ...loop, id: "eloop_b", status: "PLANNING" }],
  readOnly: true,
};

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function dashboard(overrides: Partial<Parameters<typeof renderExecutionLoopDashboard>[3]> = {}, loops: ExecutionLoopRecord[] = [loop]) {
  return renderExecutionLoopDashboard(document, loops, quality, {
    dags: [dag],
    dagReady: { dagId: dag.id, readyLoops: ["eloop_a"], loopStatuses: dag.loopStatuses, readOnly: true },
    metrics,
    context,
    ...overrides,
  });
}

describe("Phase 17 execution orchestration dashboard", () => {
  it("has the existing stable role marker", () => expect(dashboard().dataset.role).toBe("execution-loop-dashboard"));
  it("shows Phase 17 heading", () => expect(dashboard().textContent).toContain("Execution Orchestration · Phase 17"));
  it("shows DAG id", () => expect(dashboard().textContent).toContain("edag_a"));
  it("shows DAG status", () => expect(dashboard().textContent).toContain("ACTIVE"));
  it("shows loop count", () => expect(dashboard().textContent).toContain("2 loop(s)"));
  it("shows edge count", () => expect(dashboard().textContent).toContain("1 dependency edge(s)"));
  it("shows dependency direction", () => expect(dashboard().textContent).toContain("eloop_a → eloop_b"));
  it("shows dependency type", () => expect(dashboard().textContent).toContain("depends_on"));
  it("shows ready loop", () => expect(dashboard().textContent).toContain("ready: eloop_a"));
  it("shows metrics heading", () => expect(dashboard().textContent).toContain("Engineering metrics"));
  it("shows total loop metric", () => expect(dashboard().textContent).toContain("4 loops"));
  it("shows success rate", () => expect(dashboard().textContent).toContain("success 100%"));
  it("shows rollback rate", () => expect(dashboard().textContent).toContain("rollback 0%"));
  it("shows quality metric", () => expect(dashboard().textContent).toContain("quality 88/100"));
  it("shows duration metric", () => expect(dashboard().textContent).toContain("duration 1200ms"));
  it("shows recovered count", () => expect(dashboard().textContent).toContain("recovered 1"));
  it("shows risk distribution", () => expect(dashboard().textContent).toContain("risk low 2 · medium 1 · high 1"));
  it("shows related loop count", () => expect(dashboard().textContent).toContain("1 related"));
  it("shows outgoing relation count", () => expect(dashboard().textContent).toContain("0 incoming · 1 outgoing"));
  it("shows evidence bundle", () => expect(dashboard().textContent).toContain("evidence bundle"));
  it("shows evidence tests", () => expect(dashboard().textContent).toContain("tests passed"));
  it("shows evidence quality", () => expect(dashboard().textContent).toContain("quality 92"));
  it("shows evidence risk", () => expect(dashboard().textContent).toContain("risk 18"));
  it("renders no buttons", () => expect(dashboard().querySelectorAll("button")).toHaveLength(0));
  it("renders no links", () => expect(dashboard().querySelectorAll("a")).toHaveLength(0));
  it("renders no form controls", () => expect(dashboard().querySelectorAll("input,select,textarea")).toHaveLength(0));
  it("keeps read-only badge", () => expect(dashboard().textContent).toContain("APPROVAL CONTROLLED · READ ONLY"));
  it("does not show auto-execution wording", () => expect(dashboard().textContent?.toLowerCase()).not.toContain("auto execute"));
  it("does not show apply action wording", () => expect(dashboard().textContent?.toLowerCase()).not.toContain("apply changes"));
  it("does not mutate DAG", () => { const before = JSON.stringify(dag); dashboard(); expect(JSON.stringify(dag)).toBe(before); });
  it("does not mutate metrics", () => { const before = JSON.stringify(metrics); dashboard(); expect(JSON.stringify(metrics)).toBe(before); });
  it("does not mutate context", () => { const before = JSON.stringify(context); dashboard(); expect(JSON.stringify(context)).toBe(before); });
  it("handles no DAGs", () => expect(dashboard({ dags: [] }).textContent).toContain("No execution DAGs recorded yet"));
  it("handles no metrics", () => expect(dashboard({ metrics: null }).textContent).not.toContain("Engineering metrics ·"));
  it("handles no context", () => expect(dashboard({ context: null }).textContent).not.toContain("cross-loop context"));
  it("shows no ready loops", () => expect(dashboard({ dagReady: { dagId: dag.id, readyLoops: [], loopStatuses: dag.loopStatuses, readOnly: true } }).textContent).toContain("ready: none"));
  it("marks no ready loops as warning", () => expect(dashboard({ dagReady: { dagId: dag.id, readyLoops: [], loopStatuses: dag.loopStatuses, readOnly: true } }).querySelector(".warning")).not.toBeNull());
  it("shows recovered state requiring confirmation", () => expect(dashboard({ context: { ...context, loop: { ...loop, status: "RECOVERED" } } }, [{ ...loop, status: "RECOVERED" }]).textContent).toContain("explicit human confirmation required"));
  it("shows evidence unavailable when absent", () => expect(dashboard({ context: { ...context, verification: {} } }).textContent).toContain("evidence bundle · not available yet"));
  it("shows completed DAG as pass", () => expect(dashboard({ dags: [{ ...dag, status: "COMPLETED" }] }).querySelector(".pass")).not.toBeNull());
  it("supports multiple DAGs", () => expect(dashboard({ dags: [dag, { ...dag, id: "edag_b" }] }).textContent).toContain("2 execution DAG(s)"));
  it("limits edge display", () => { const many = { ...dag, edges: Array.from({ length: 10 }, (_, i) => ({ sourceLoop: `a${i}`, targetLoop: `b${i}`, dependencyType: "depends_on" })) }; const text = dashboard({ dags: [many] }).textContent ?? ""; expect(text).not.toContain("a9 → b9"); });
  it("preserves graph text safely", () => { const weird = { ...dag, id: "<dag>" }; expect(dashboard({ dags: [weird] }).textContent).toContain("<dag>"); });

  const statuses = ["CREATED", "PLANNING", "PROPOSAL_READY", "WAITING_APPROVAL", "EXECUTING", "VERIFYING", "COMPLETED", "FAILED", "ROLLED_BACK", "CANCELLED", "RECOVERED"] as const;
  it.each(statuses)("renders loop status %s", (status) => expect(dashboard({}, [{ ...loop, status }]).textContent).toContain(status));

  const dependencyTypes = ["depends_on", "blocks", "requires_review"];
  it.each(dependencyTypes)("renders dependency type %s", (dependencyType) => expect(dashboard({ dags: [{ ...dag, edges: [{ ...dag.edges[0], dependencyType }] }] }).textContent).toContain(dependencyType));

  const riskValues = ["low", "medium", "high"];
  it.each(riskValues)("renders risk label %s", (risk) => expect(dashboard({ metrics: { ...metrics, riskDistribution: { low: risk === "low" ? 1 : 0, medium: risk === "medium" ? 1 : 0, high: risk === "high" ? 1 : 0 } } }).textContent).toContain(`risk low`));
});

describe("Phase 17 read-only BridgeClient methods", () => {
  it("loads DAG list", async () => { const f = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/execution-dag/list?project=demo"); return response({ dags: [dag], readOnly: true }); }); expect((await new BridgeClient({ fetchImpl: f as typeof fetch }).executionDagList("demo")).dags).toHaveLength(1); });
  it("loads DAG detail", async () => { const f = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/execution-dag/edag_a"); return response(dag); }); expect((await new BridgeClient({ fetchImpl: f as typeof fetch }).executionDag("edag_a")).id).toBe("edag_a"); });
  it("loads DAG readiness", async () => { const f = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/ready"); return response({ dagId: "edag_a", readyLoops: ["eloop_a"], loopStatuses: {}, readOnly: true }); }); expect((await new BridgeClient({ fetchImpl: f as typeof fetch }).executionDagReady("edag_a")).readyLoops).toEqual(["eloop_a"]); });
  it("loads metrics", async () => { const f = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/engineering/metrics?project=demo"); return response(metrics); }); expect((await new BridgeClient({ fetchImpl: f as typeof fetch }).engineeringMetrics("demo")).successRate).toBe(100); });
  it("loads cross-loop context", async () => { const f = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/execution-loop/eloop_a/context"); return response(context); }); expect((await new BridgeClient({ fetchImpl: f as typeof fetch }).executionLoopContext("eloop_a")).relatedLoops).toHaveLength(1); });
  it("uses GET for DAG list", async () => { const methods: string[] = []; const f = vi.fn(async (_i: RequestInfo | URL, init?: RequestInit) => { methods.push(init?.method ?? "GET"); return response({ dags: [], readOnly: true }); }); await new BridgeClient({ fetchImpl: f as typeof fetch }).executionDagList(); expect(methods).toEqual(["GET"]); });
  it("uses GET for metrics", async () => { const methods: string[] = []; const f = vi.fn(async (_i: RequestInfo | URL, init?: RequestInit) => { methods.push(init?.method ?? "GET"); return response(metrics); }); await new BridgeClient({ fetchImpl: f as typeof fetch }).engineeringMetrics(); expect(methods).toEqual(["GET"]); });
  it("preserves DAG read-only marker", async () => { const c = new BridgeClient({ fetchImpl: vi.fn(async () => response({ dags: [], readOnly: true })) as typeof fetch }); expect((await c.executionDagList()).readOnly).toBe(true); });
  it("preserves metrics read-only marker", async () => { const c = new BridgeClient({ fetchImpl: vi.fn(async () => response(metrics)) as typeof fetch }); expect((await c.engineeringMetrics()).readOnly).toBe(true); });
  it("does not expose DAG creation", () => expect("createExecutionDag" in new BridgeClient()).toBe(false));
  it("does not expose DAG advance", () => expect("advanceExecutionDag" in new BridgeClient()).toBe(false));
  it("does not expose recovery mutation", () => expect("recoverExecutionLoop" in new BridgeClient()).toBe(false));
  it("does not expose metrics mutation", () => expect("writeEngineeringMetrics" in new BridgeClient()).toBe(false));
  it("encodes DAG ids", async () => { const f = vi.fn(async (i: RequestInfo | URL) => { expect(String(i)).toContain("edag%20one"); return response(dag); }); await new BridgeClient({ fetchImpl: f as typeof fetch }).executionDag("edag one"); });
  it("encodes context ids", async () => { const f = vi.fn(async (i: RequestInfo | URL) => { expect(String(i)).toContain("eloop%20one"); return response(context); }); await new BridgeClient({ fetchImpl: f as typeof fetch }).executionLoopContext("eloop one"); });
  it("encodes metrics project", async () => { const f = vi.fn(async (i: RequestInfo | URL) => { expect(String(i)).toContain("demo%20app"); return response(metrics); }); await new BridgeClient({ fetchImpl: f as typeof fetch }).engineeringMetrics("demo app"); });
});
