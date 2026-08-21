import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderExecutionDashboard } from "../src/execution/execution-dashboard";
import type {
  ExecutionProposalRecord,
  ExecutionQuality7,
  ExecutionResultRecord,
  ExecutionTaskRecord,
} from "../src/execution/models";

const task: ExecutionTaskRecord = {
  id: "et_1",
  workflowId: "wf_1",
  planId: "plan_1",
  project: "demo",
  title: "extract auth service",
  type: "implementation",
  files: ["src/user.py", "src/auth.py"],
  dependencies: ["move token logic"],
  risk: "medium",
  riskScore: 40,
  status: "APPROVAL_REQUIRED",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  verification: {},
  readOnly: true,
};

const proposal: ExecutionProposalRecord = {
  id: "ep_1",
  taskId: "et_1",
  project: "demo",
  workflowId: "wf_1",
  operations: [
    { type: "file.patch", path: "src/user.py", reason: "extract auth" },
    { type: "file.patch", path: "src/auth.py", reason: "extract auth" },
  ],
  estimatedChanges: 15,
  riskScore: 65,
  status: "PROPOSED",
  approvalId: null,
  createdAt: "2026-01-01T00:00:00Z",
  readOnly: true,
};

const result: ExecutionResultRecord = {
  id: "er_1",
  proposalId: "ep_1",
  taskId: "et_1",
  project: "demo",
  filesChanged: ["src/user.py", "src/auth.py"],
  diffSummary: { changed: 1, files: ["src/user.py", "src/auth.py"], diffBytes: 120 },
  durationMs: 42,
  errors: [],
  verification: {
    status: "PASS",
    checks: ["approval_verified", "snapshot_captured", "git_diff_present", "no_dependency_break"],
    project: "demo",
    files: ["src/user.py", "src/auth.py"],
    snapshotCaptured: true,
    approvalVerified: true,
    qualityScore: 91,
    readOnly: true,
    autoFix: false,
  },
  createdAt: "2026-01-01T00:00:00Z",
  readOnly: true,
};

const quality: ExecutionQuality7 = {
  quality: 92,
  executionReady: true,
  blockingIssues: [],
  implementationConfidence: 95,
  executionRisk: 20,
  risk: "low",
  rollbackReadiness: 90,
  verificationConfidence: 90,
  readOnly: true,
};

function render(
  tasks: ExecutionTaskRecord[] = [task],
  proposals: ExecutionProposalRecord[] = [proposal],
  results: ExecutionResultRecord[] = [result],
  gate: ExecutionQuality7 | null = quality,
): HTMLElement {
  return renderExecutionDashboard(document, tasks, proposals, results, gate);
}

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("Phase 15 execution dashboard", () => {
  it("has a stable role marker", () => {
    expect(render().dataset.role).toBe("execution-dashboard");
  });

  it("shows the read-only badge", () => {
    expect(render().textContent).toContain("CONTROLLED · READ ONLY");
  });

  it("renders the empty state", () => {
    expect(render([], [], [], null).textContent).toContain("No controlled execution yet");
  });

  it("shows implementation task count", () => {
    expect(render().textContent).toContain("1 implementation tasks");
  });

  it("shows tasks waiting approval", () => {
    expect(render().textContent).toContain("1 waiting approval");
  });

  it("shows proposal queue count", () => {
    expect(render().textContent).toContain("1 proposals pending");
  });

  it("shows task title", () => {
    expect(render().textContent).toContain("extract auth service");
  });

  it("shows task status", () => {
    expect(render().textContent).toContain("APPROVAL_REQUIRED");
  });

  it("shows task risk", () => {
    expect(render().textContent).toContain("MEDIUM risk 40/100");
  });

  it("shows task file count", () => {
    expect(render().textContent).toContain("2 file(s)");
  });

  it("shows executed count", () => {
    expect(render().textContent).toContain("1");
  });

  it("shows verified count", () => {
    expect(render().textContent).toContain("1");
  });

  it("shows proposal id", () => {
    expect(render().textContent).toContain("ep_1");
  });

  it("shows proposal operation count", () => {
    expect(render().textContent).toContain("2 operation(s)");
  });

  it("shows proposal risk", () => {
    expect(render().textContent).toContain("risk 65/100");
  });

  it("shows execution result id", () => {
    expect(render().textContent).toContain("er_1");
  });

  it("shows verification status", () => {
    expect(render().textContent).toContain("PASS in 42ms");
  });

  it("shows verification checks", () => {
    expect(render().textContent).toContain("approval_verified");
  });

  it("shows quality score", () => {
    expect(render().textContent).toContain("Quality 92/100");
  });

  it("shows execution readiness", () => {
    expect(render().textContent).toContain("execution ready");
  });

  it("shows blocked execution when not ready", () => {
    expect(render([], [], [], { ...quality, executionReady: false, quality: 40 }).textContent).toContain("execution blocked");
  });

  it("marks high risk tasks", () => {
    expect(render([{ ...task, risk: "high" }], [], [], null).querySelector(".warning")).not.toBeNull();
  });

  it("marks failed verification", () => {
    const failed = { ...result, verification: { ...result.verification, status: "FAIL" } };
    expect(render([], [], [failed], null).querySelector(".warning")).not.toBeNull();
  });

  it("limits tasks to eight", () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ ...task, id: `et_${i}`, title: `task ${i}` }));
    expect(render(many, [], [], null).querySelectorAll(".execution-task")).toHaveLength(8);
  });

  it("limits proposals to six", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ ...proposal, id: `ep_${i}` }));
    expect(render([], many, [], null).querySelectorAll(".execution-proposal")).toHaveLength(6);
  });

  it("limits results to six", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ ...result, id: `er_${i}` }));
    expect(render([], [], many, null).querySelectorAll(".execution-result")).toHaveLength(6);
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

  it("does not expose apply wording", () => {
    expect(render().textContent?.toLowerCase()).not.toContain("apply changes");
  });

  it("does not mutate task records", () => {
    const before = JSON.stringify(task);
    render();
    expect(JSON.stringify(task)).toBe(before);
  });

  it("does not mutate proposal records", () => {
    const before = JSON.stringify(proposal);
    render();
    expect(JSON.stringify(proposal)).toBe(before);
  });

  it("does not mutate result records", () => {
    const before = JSON.stringify(result);
    render();
    expect(JSON.stringify(result)).toBe(before);
  });

  const statuses = ["PROPOSED", "APPROVAL_REQUIRED", "APPROVED", "EXECUTING", "VERIFYING", "COMPLETED", "FAILED", "ROLLED_BACK"];
  it.each(statuses)("renders task status %s", (status) => {
    expect(render([{ ...task, status }], [], [], null).textContent).toContain(status);
  });

  const risks = ["low", "medium", "high"];
  it.each(risks)("renders task risk %s", (risk) => {
    expect(render([{ ...task, risk }], [], [], null).textContent).toContain(`${risk.toUpperCase()} risk`);
  });

  const qualities = [0, 30, 70, 92, 100];
  it.each(qualities)("renders quality %s", (value) => {
    expect(render([], [], [], { ...quality, quality: value }).textContent).toContain(`Quality ${value}/100`);
  });

  const proposalStatuses = ["PROPOSED", "APPROVED", "REJECTED", "EXECUTED", "FAILED", "ROLLED_BACK"];
  it.each(proposalStatuses)("renders proposal status %s", (status) => {
    expect(render([], [{ ...proposal, status }], [], null).textContent).toContain(status);
  });
});

describe("Phase 15 Execution BridgeClient reads", () => {
  it("loads execution tasks with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/execution/tasks");
      expect(init?.method ?? "GET").toBe("GET");
      return response({ tasks: [task], readOnly: true });
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionTasks("demo");
    expect(result.tasks).toEqual([task]);
    expect(result.readOnly).toBe(true);
  });

  it("loads execution proposals with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/execution/proposals");
      return response({ proposals: [proposal], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionProposals("demo");
  });

  it("loads execution results with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/execution/results");
      return response({ results: [result], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionResults("demo");
  });

  it("loads verification with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/execution/et_1/verify");
      return response({ executionId: "et_1", status: "PASS", checks: [], readOnly: true });
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionVerify("et_1");
    expect(result.status).toBe("PASS");
  });

  it("loads Quality Gate 7 with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/quality/v7/wf_1");
      return response(quality);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionQuality7("wf_1");
  });

  it("loads execution memory history with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/memory/execution/history?project=demo");
      return response({ project: "demo", history: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionMemoryHistory("demo");
  });

  it("encodes execution ids", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("et%20one");
      return response({ executionId: "et one", status: "PASS", checks: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionVerify("et one");
  });

  it("encodes project filters", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("project=demo%20two");
      return response({ tasks: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionTasks("demo two");
  });

  it("preserves read-only task response", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ tasks: [], readOnly: true })) as unknown as typeof fetch });
    expect((await client.executionTasks()).readOnly).toBe(true);
  });

  it("preserves read-only results response", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ results: [], readOnly: true })) as unknown as typeof fetch });
    expect((await client.executionResults()).readOnly).toBe(true);
  });

  it("preserves quality blocking issues", async () => {
    const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ ...quality, blockingIssues: ["db migration"] })) as unknown as typeof fetch });
    expect((await client.executionQuality7("wf_1")).blockingIssues).toEqual(["db migration"]);
  });

  it("does not expose execute proposal", () => {
    const client = new BridgeClient();
    expect("executeProposal" in client).toBe(false);
  });

  it("does not expose execution create", () => {
    const client = new BridgeClient();
    expect("createExecution" in client).toBe(false);
  });

  it("does not expose execution approval", () => {
    const client = new BridgeClient();
    expect("approveExecution" in client).toBe(false);
  });

  it("does not expose proposal generation", () => {
    const client = new BridgeClient();
    expect("generateProposal" in client).toBe(false);
  });

  it("does not expose execution memory writes", () => {
    const client = new BridgeClient();
    expect("writeExecutionMemory" in client).toBe(false);
  });

  const ids = ["et_1", "et_abc", "phase15", "execution-task-one", "中文任务"];
  it.each(ids)("supports execution id %s", async (id) => {
    const fetchImpl = vi.fn(async () => response({ executionId: id, status: "PASS", checks: [], readOnly: true }));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionVerify(id);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  const workflows = ["wf_1", "wf_review", "phase15", "workflow-two", "中文工作流"];
  it.each(workflows)("supports workflow id %s", async (workflowId) => {
    const fetchImpl = vi.fn(async () => response(quality));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionQuality7(workflowId);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  const projects = ["demo", "demo-two", "my_project", "中文项目"];
  it.each(projects)("supports project filter %s", async (project) => {
    const fetchImpl = vi.fn(async () => response({ tasks: [], readOnly: true }));
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).executionTasks(project);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
