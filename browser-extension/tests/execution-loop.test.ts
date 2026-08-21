import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderExecutionLoopDashboard, renderExecutionLoopTimeline } from "../src/execution-loop/execution-loop-dashboard";
import type {
  ExecutionLoopHistoryEntry,
  ExecutionLoopQuality8,
  ExecutionLoopRecord,
} from "../src/execution-loop/models";

const quality: ExecutionLoopQuality8 = {
  quality: 88,
  executionReady: true,
  confidence: 84,
  riskLevel: "medium",
  blockingIssues: [],
  rollbackCapability: true,
  testResult: "passed",
  recommendation: "loop_ready",
  readOnly: true,
};

const history: ExecutionLoopHistoryEntry[] = [
  { status: "CREATED", at: "2026-02-01T00:00:00Z", detail: "loop created" },
  { status: "PLANNING", at: "2026-02-01T00:00:01Z", detail: "3 task(s) planned" },
  { status: "PROPOSAL_READY", at: "2026-02-01T00:00:02Z", detail: "proposal generated" },
  { status: "WAITING_APPROVAL", at: "2026-02-01T00:00:03Z", detail: "awaiting human approval" },
  { status: "EXECUTING", at: "2026-02-01T00:00:04Z", detail: "controlled execution approved" },
  { status: "VERIFYING", at: "2026-02-01T00:00:05Z", detail: "execution result recorded" },
  { status: "COMPLETED", at: "2026-02-01T00:00:06Z", detail: "verification PASS" },
];

const loop: ExecutionLoopRecord = {
  id: "eloop_1",
  project: "demo",
  planId: "plan_1",
  workflowId: "wf_1",
  taskIds: ["et_1", "et_2", "et_3"],
  proposalId: "ep_1",
  resultId: "er_1",
  approvalId: "req_1",
  status: "COMPLETED",
  verification: { status: "PASS", checks: ["approval_verified", "snapshot_verified"] },
  quality,
  rollback: {},
  memoryProposalId: null,
  createdAt: "2026-02-01T00:00:00Z",
  updatedAt: "2026-02-01T00:00:06Z",
  history,
  readOnly: true,
};

function render(loops: ExecutionLoopRecord[] = [loop], gate: ExecutionLoopQuality8 | null = quality): HTMLElement {
  return renderExecutionLoopDashboard(document, loops, gate);
}

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("Phase 16 execution loop dashboard", () => {
  it("has a stable role marker", () => {
    expect(render().dataset.role).toBe("execution-loop-dashboard");
  });

  it("shows the approval controlled badge", () => {
    expect(render().textContent).toContain("APPROVAL CONTROLLED · READ ONLY");
  });

  it("renders the empty state", () => {
    expect(render([], null).textContent).toContain("No execution loop yet");
  });

  it("shows loop count", () => {
    expect(render().textContent).toContain("1 loop(s)");
  });

  it("shows active loop count", () => {
    expect(render().textContent).toContain("0 active");
  });

  it("shows completed loop count", () => {
    expect(render().textContent).toContain("1 completed");
  });

  it("counts waiting approval loops as active", () => {
    const waiting = { ...loop, status: "WAITING_APPROVAL" as const };
    expect(render([waiting]).textContent).toContain("1 active");
  });

  it("counts executing loops as active", () => {
    const running = { ...loop, status: "EXECUTING" as const };
    expect(render([running]).textContent).toContain("1 active");
  });

  it("counts verifying loops as active", () => {
    const verifying = { ...loop, status: "VERIFYING" as const };
    expect(render([verifying]).textContent).toContain("1 active");
  });

  it("shows loop id", () => {
    expect(render().textContent).toContain("eloop_1");
  });

  it("shows loop status", () => {
    expect(render().textContent).toContain("COMPLETED");
  });

  it("shows plan reference", () => {
    expect(render().textContent).toContain("plan plan_1");
  });

  it("shows task count", () => {
    expect(render().textContent).toContain("3 task(s)");
  });

  it("shows proposal reference", () => {
    expect(render().textContent).toContain("proposal ep_1");
  });

  it("shows result reference", () => {
    expect(render().textContent).toContain("result er_1");
  });

  it("shows learning memory proposal status", () => {
    const withMemory = { ...loop, memoryProposalId: "req_9" };
    expect(render([withMemory]).textContent).toContain("learning memory proposal queued");
  });

  it("shows rollback restored count", () => {
    const rolled = { ...loop, status: "ROLLED_BACK" as const, rollback: { count: 4, restoredFiles: ["a.py", "b.py"] } };
    expect(render([rolled]).textContent).toContain("rollback restored 4 file(s)");
  });

  it("renders timeline steps", () => {
    expect(render().querySelectorAll(".execution-loop-step").length).toBeGreaterThanOrEqual(3);
  });

  it("renders each distinct history status", () => {
    const steps = Array.from(render().querySelectorAll(".execution-loop-step")).map((node) => node.textContent);
    for (const status of ["CREATED", "PLANNING", "WAITING_APPROVAL", "COMPLETED"]) {
      expect(steps).toContain(status);
    }
  });

  it("shows quality gate 8 heading", () => {
    expect(render().textContent).toContain("Quality Gate 8.0");
  });

  it("shows quality score", () => {
    expect(render().textContent).toContain("Quality 88/100");
  });

  it("shows execution readiness", () => {
    expect(render().textContent).toContain("execution ready");
  });

  it("shows blocked execution when not ready", () => {
    expect(render([], { ...quality, executionReady: false, quality: 30 }).textContent).toContain("execution blocked");
  });

  it("shows confidence", () => {
    expect(render().textContent).toContain("confidence 84/100");
  });

  it("shows risk level", () => {
    expect(render().textContent).toContain("risk MEDIUM");
  });

  it("shows no blocking issues", () => {
    expect(render().textContent).toContain("no blocking issues");
  });

  it("shows blocking issues when present", () => {
    const blocked = { ...quality, blockingIssues: ["no_approval", "risk_high"] };
    expect(render([], blocked).textContent).toContain("blocking: no_approval, risk_high");
  });

  it("shows rollback capability", () => {
    expect(render().textContent).toContain("rollback ready");
  });

  it("shows rollback unavailable", () => {
    expect(render([], { ...quality, rollbackCapability: false }).textContent).toContain("rollback unavailable");
  });

  it("shows test result", () => {
    expect(render().textContent).toContain("tests passed");
  });

  it("shows tests not run", () => {
    expect(render([], { ...quality, testResult: "not_run" }).textContent).toContain("tests not run");
  });

  it("shows recommendation", () => {
    expect(render().textContent).toContain("recommendation: loop_ready");
  });

  it("limits loops to four", () => {
    const many = Array.from({ length: 6 }, (_, i) => ({ ...loop, id: `eloop_${i}` }));
    expect(render(many).querySelectorAll(".execution-loop-card")).toHaveLength(4);
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

  it("does not expose execute wording", () => {
    expect(render().textContent?.toLowerCase()).not.toContain("execute now");
  });

  it("does not expose auto fix wording", () => {
    expect(render().textContent?.toLowerCase()).not.toContain("auto fix");
  });

  it("does not expose apply wording", () => {
    expect(render().textContent?.toLowerCase()).not.toContain("apply changes");
  });

  it("does not mutate loop records", () => {
    const before = JSON.stringify(loop);
    render();
    expect(JSON.stringify(loop)).toBe(before);
  });

  it("does not mutate history records", () => {
    const before = JSON.stringify(history);
    render();
    expect(JSON.stringify(history)).toBe(before);
  });

  it("marks failed loops as warning", () => {
    expect(render([{ ...loop, status: "FAILED" }]).querySelector(".warning")).not.toBeNull();
  });

  it("marks rolled back loops as warning", () => {
    expect(render([{ ...loop, status: "ROLLED_BACK" }]).querySelector(".warning")).not.toBeNull();
  });

  it("marks completed loops as pass", () => {
    expect(render().querySelector(".pass")).not.toBeNull();
  });

  it("marks waiting approval as pending", () => {
    expect(render([{ ...loop, status: "WAITING_APPROVAL" }]).querySelector(".pending")).not.toBeNull();
  });

  it("renders timeline role marker", () => {
    expect(renderExecutionLoopTimeline(document, "eloop_1", history).dataset.role).toBe("execution-loop-timeline");
  });

  it("timeline shows loop id", () => {
    expect(renderExecutionLoopTimeline(document, "eloop_1", history).textContent).toContain("eloop_1");
  });

  it("timeline renders empty state", () => {
    expect(renderExecutionLoopTimeline(document, "eloop_1", []).textContent).toContain("No timeline events yet");
  });

  it("timeline shows latest events", () => {
    expect(renderExecutionLoopTimeline(document, "eloop_1", history).textContent).toContain("VERIFYING");
  });

  it("timeline shows event timestamps", () => {
    expect(renderExecutionLoopTimeline(document, "eloop_1", history).textContent).toContain("2026-02-01T00:00:06Z");
  });

  it("timeline shows event detail", () => {
    expect(renderExecutionLoopTimeline(document, "eloop_1", history).textContent).toContain("verification PASS");
  });

  it("timeline limits to eight entries", () => {
    const many = Array.from({ length: 12 }, (_, i) => ({ status: `S_${i}`, at: `2026-01-01T00:00:0${i % 10}Z`, detail: "" }));
    expect(renderExecutionLoopTimeline(document, "eloop_1", many).querySelectorAll(".execution-loop-step-row").length).toBeLessThanOrEqual(8);
  });

  const statuses = ["CREATED", "PLANNING", "PROPOSAL_READY", "WAITING_APPROVAL", "EXECUTING", "VERIFYING", "COMPLETED", "FAILED", "ROLLED_BACK", "CANCELLED"];
  it.each(statuses)("renders loop status %s", (status) => {
    expect(render([{ ...loop, status: status as ExecutionLoopRecord["status"] }]).textContent).toContain(status);
  });

  const risks = ["low", "medium", "high"];
  it.each(risks)("renders risk level %s", (risk) => {
    expect(render([], { ...quality, riskLevel: risk }).textContent).toContain(`risk ${risk.toUpperCase()}`);
  });

  const scores = [0, 25, 50, 88, 100];
  it.each(scores)("renders quality score %s", (value) => {
    expect(render([], { ...quality, quality: value }).textContent).toContain(`Quality ${value}/100`);
  });

  it("renders failed verification loops", () => {
    const failed = { ...loop, status: "FAILED" as const, verification: { status: "FAIL" } };
    expect(render([failed]).textContent).toContain("FAILED");
  });

  it("shows workflow id when present", () => {
    expect(render().textContent).toContain("wf_1");
  });
});

describe("Phase 16 execution loop BridgeClient reads", () => {
  it("loads execution loops with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/execution-loop/list");
      return response({ loops: [loop], readOnly: true });
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoopList("demo");
    expect(result.loops).toEqual([loop]);
    expect(result.readOnly).toBe(true);
  });

  it("loads a single execution loop with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/execution-loop/eloop_1");
      return response(loop);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoop("eloop_1");
    expect(result.status).toBe("COMPLETED");
  });

  it("loads loop timeline with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/execution-loop/eloop_1/timeline");
      return response({ loopId: "eloop_1", timeline: history, readOnly: true });
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoopTimeline("eloop_1");
    expect(result.timeline.length).toBeGreaterThan(0);
  });

  it("loads Quality Gate 8 with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/quality/v8/wf_1");
      return response({ workflowId: "wf_1", ...quality });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoopQuality8("wf_1");
  });

  it("preserves read-only loop list", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ loops: [], readOnly: true })) as unknown as typeof fetch });
    expect((await client.executionLoopList()).readOnly).toBe(true);
  });

  it("preserves loop quality blocking issues", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ workflowId: "wf_1", ...quality, blockingIssues: ["no_snapshot"] })) as unknown as typeof fetch });
    expect((await client.executionLoopQuality8("wf_1")).blockingIssues).toEqual(["no_snapshot"]);
  });

  it("encodes loop ids", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("eloop%20one");
      return response(loop);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoop("eloop one");
  });

  it("encodes project filters", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("project=demo%20two");
      return response({ loops: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoopList("demo two");
  });

  it("does not expose loop create", () => {
    const client = new BridgeClient();
    expect("createExecutionLoop" in client).toBe(false);
  });

  it("does not expose loop prepare", () => {
    const client = new BridgeClient();
    expect("prepareLoop" in client).toBe(false);
  });

  it("does not expose loop verify", () => {
    const client = new BridgeClient();
    expect("verifyLoop" in client).toBe(false);
  });

  it("does not expose loop rollback", () => {
    const client = new BridgeClient();
    expect("rollbackLoop" in client).toBe(false);
  });

  it("does not expose loop execute", () => {
    const client = new BridgeClient();
    expect("executeLoop" in client).toBe(false);
  });

  it("does not expose loop memory writes", () => {
    const client = new BridgeClient();
    expect("writeLoopMemory" in client).toBe(false);
  });

  const ids = ["eloop_1", "eloop_abc", "phase16", "execution-loop-one", "中文循环"];
  it.each(ids)("supports loop id %s", async (id) => {
    const fetchImpl = vi.fn(async () => response(loop));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoop(id);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  const workflows = ["wf_1", "wf_verify", "phase16", "workflow-two", "中文工作流"];
  it.each(workflows)("supports workflow id %s", async (workflowId) => {
    const fetchImpl = vi.fn(async () => response({ workflowId, ...quality }));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoopQuality8(workflowId);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  const projects = ["demo", "demo-two", "my_project", "中文项目"];
  it.each(projects)("supports project filter %s", async (project) => {
    const fetchImpl = vi.fn(async () => response({ loops: [], readOnly: true }));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionLoopList(project);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
