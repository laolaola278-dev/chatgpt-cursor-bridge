import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderIntelligenceDashboard } from "../src/intelligence/intelligence-dashboard";
import type { EngineeringDecision, EngineeringInsight, EngineeringProposal, IntelligenceQuality5 } from "../src/intelligence/models";

const insight: EngineeringInsight = { id: "ins_1", project: "demo", type: "architecture_risk", severity: "high", title: "High coupling", location: "src/user.ts", evidence: ["5 dependents"], suggestion: "Extract boundary", createdAt: "2026-01-01T00:00:00Z" };
const proposal: EngineeringProposal = { id: "proposal_1", project: "demo", insightId: "ins_1", type: "refactor", target: { file: "src/user.ts" }, reason: ["high coupling"], expectedGain: ["lower maintenance"], risk: "medium", riskScore: 45, status: "DRAFT", createdAt: "2026-01-01T00:00:00Z" };
const decision: EngineeringDecision = { id: "decision_1", project: "demo", proposalId: "proposal_1", title: "Extract user service", context: "Coupling is increasing", options: [{ name: "keep", risk: "high" }, { name: "extract", risk: "medium" }], recommendation: "extract", status: "DRAFT", createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", history: [{ status: "DRAFT", at: "2026-01-01T00:00:00Z" }] };
const quality: IntelligenceQuality5 = { quality: 82, risk: "medium", architectureScore: 80, maintainabilityScore: 84, riskScore: 35, decisionConfidence: 90, technicalDebt: { score: 35, items: 12 }, recommendations: [], readOnly: true };

function response(body: unknown): Response { return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }); }
function dashboard(insights = [insight], proposals = [proposal], decisions = [decision], q: IntelligenceQuality5 | null = quality): HTMLElement { return renderIntelligenceDashboard(document, insights, proposals, decisions, q); }

describe("Engineering Intelligence dashboard", () => {
  it("has a stable read-only root", () => { const root = dashboard(); expect(root.dataset.role).toBe("engineering-intelligence-dashboard"); expect(root.textContent).toContain("ANALYSIS · READ ONLY"); });
  it("renders insight counts", () => { expect(dashboard().textContent).toContain("1 insights"); });
  it("renders proposal counts", () => { expect(dashboard().textContent).toContain("1 proposals"); });
  it("renders decision counts", () => { expect(dashboard().textContent).toContain("1 decisions"); });
  it("renders quality score", () => { expect(dashboard().textContent).toContain("Quality 82/100"); });
  it("renders risk signal title", () => { expect(dashboard().textContent).toContain("HIGH · High coupling"); });
  it("renders proposal risk", () => { expect(dashboard().textContent).toContain("refactor · medium (45)"); });
  it("renders decision status", () => { expect(dashboard().textContent).toContain("DRAFT · Extract user service"); });
  it("renders technical debt", () => { expect(dashboard().textContent).toContain("Technical debt 35/100 · 12 item(s)"); });
  it("renders quality risk", () => { expect(dashboard().textContent).toContain("Risk medium"); });
  it("renders no controls", () => { expect(dashboard().querySelectorAll("button")).toHaveLength(0); });
  it("does not include execute language", () => { expect(dashboard().textContent?.toLowerCase()).not.toContain("execute"); });
  it("does not include apply language", () => { expect(dashboard().textContent?.toLowerCase()).not.toContain("apply"); });
  it("does not include fix language", () => { expect(dashboard().textContent?.toLowerCase()).not.toContain("fix now"); });
  it("does not include approve controls", () => { expect(dashboard().querySelector("input,select,textarea")).toBeNull(); });
  it("renders empty insight state", () => { expect(dashboard([], [proposal], [decision]).textContent).toContain("No analyzed risks yet"); });
  it("renders empty proposal state", () => { expect(dashboard([insight], [], [decision]).textContent).toContain("No proposals yet"); });
  it("renders empty decision state", () => { expect(dashboard([insight], [proposal], []).textContent).toContain("No decisions recorded"); });
  it("renders missing quality state", () => { expect(dashboard([insight], [proposal], [decision], null).textContent).toContain("Quality pending"); });
  it("renders critical insight tone", () => { const critical = { ...insight, severity: "critical" }; expect(dashboard([critical]).querySelector(".warning")).not.toBeNull(); });
  it("renders medium insight without warning", () => { const medium = { ...insight, severity: "medium" }; expect(dashboard([medium]).querySelector(".warning")).toBeNull(); });
  it("limits visible insights", () => { const many = Array.from({ length: 8 }, (_, i) => ({ ...insight, id: `i${i}`, title: `Risk ${i}` })); expect(dashboard(many).querySelectorAll(".engineering-intelligence-block")[0].textContent).not.toContain("Risk 7"); });
  it("limits visible proposals", () => { const many = Array.from({ length: 8 }, (_, i) => ({ ...proposal, id: `p${i}`, type: `type-${i}` })); expect(dashboard([insight], many).querySelectorAll(".engineering-intelligence-block")[1].textContent).not.toContain("type-7"); });
  it("limits visible decisions", () => { const many = Array.from({ length: 8 }, (_, i) => ({ ...decision, id: `d${i}`, title: `Decision ${i}` })); expect(dashboard([insight], [proposal], many).querySelectorAll(".engineering-intelligence-block")[2].textContent).not.toContain("Decision 7"); });

  const severities = ["low", "medium", "high", "critical"] as const;
  it.each(severities)("renders severity %s safely", (severity) => { const root = dashboard([{ ...insight, severity }]); expect(root.textContent).toContain(`${severity.toUpperCase()} · High coupling`); });
  const proposalRisks = ["low", "medium", "high"] as const;
  it.each(proposalRisks)("renders proposal risk %s", (risk) => { expect(dashboard([insight], [{ ...proposal, risk }]).textContent).toContain(`refactor · ${risk}`); });
  const decisionStatuses = ["DRAFT", "REVIEWING", "APPROVED", "REJECTED", "IMPLEMENTED", "ARCHIVED"] as const;
  it.each(decisionStatuses)("renders decision status %s", (status) => { expect(dashboard([insight], [proposal], [{ ...decision, status }]).textContent).toContain(`${status} · Extract user service`); });
  const qualities = [0, 25, 50, 75, 100];
  it.each(qualities)("renders quality %s", (value) => { expect(dashboard([insight], [proposal], [decision], { ...quality, quality: value }).textContent).toContain(`Quality ${value}/100`); });
  const debts = [0, 10, 35, 70, 100];
  it.each(debts)("renders debt score %s", (value) => { expect(dashboard([insight], [proposal], [decision], { ...quality, technicalDebt: { score: value, items: 1 } }).textContent).toContain(`Technical debt ${value}/100`); });
});

describe("Engineering Intelligence BridgeClient reads", () => {
  it("loads insights", async () => { const fetchImpl = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/intelligence/insights?project=demo"); return response({ project: "demo", insights: [insight], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceInsights("demo"); expect(fetchImpl).toHaveBeenCalledTimes(1); });
  it("loads proposals", async () => { const fetchImpl = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/intelligence/proposals?project=demo"); return response({ project: "demo", proposals: [proposal], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceProposals("demo"); });
  it("loads decisions", async () => { const fetchImpl = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/intelligence/decisions?project=demo"); return response({ project: "demo", decisions: [decision], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceDecisions("demo"); });
  it("loads quality gate five", async () => { const fetchImpl = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/quality/v5/wf_1"); return response(quality); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceQuality("wf_1"); });
  it("encodes intelligence project", async () => { const fetchImpl = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("project=demo%20app"); return response({ project: "demo app", insights: [], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceInsights("demo app"); });
  it("allows all-project insight reads", async () => { const fetchImpl = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("/intelligence/insights"); expect(String(input)).not.toContain("?"); return response({ project: null, insights: [], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceInsights(); });
  it("uses GET for insights", async () => { const methods: string[] = []; const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => { methods.push(init?.method ?? "GET"); return response({ project: "demo", insights: [], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceInsights("demo"); expect(methods).toEqual(["GET"]); });
  it("uses GET for proposals", async () => { const methods: string[] = []; const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => { methods.push(init?.method ?? "GET"); return response({ project: "demo", proposals: [], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceProposals("demo"); expect(methods).toEqual(["GET"]); });
  it("uses GET for decisions", async () => { const methods: string[] = []; const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => { methods.push(init?.method ?? "GET"); return response({ project: "demo", decisions: [], readOnly: true }); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceDecisions("demo"); expect(methods).toEqual(["GET"]); });
  it("uses GET for quality", async () => { const methods: string[] = []; const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => { methods.push(init?.method ?? "GET"); return response(quality); }); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceQuality("wf"); expect(methods).toEqual(["GET"]); });
  it("returns read-only insight payload", async () => { const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ project: "demo", insights: [], readOnly: true })) as unknown as typeof fetch }); expect((await client.intelligenceInsights("demo")).readOnly).toBe(true); });
  it("returns read-only proposal payload", async () => { const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ project: "demo", proposals: [], readOnly: true })) as unknown as typeof fetch }); expect((await client.intelligenceProposals("demo")).readOnly).toBe(true); });
  it("returns read-only decision payload", async () => { const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ project: "demo", decisions: [], readOnly: true })) as unknown as typeof fetch }); expect((await client.intelligenceDecisions("demo")).readOnly).toBe(true); });
  it("returns quality fields", async () => { const client = new BridgeClient({ fetchImpl: vi.fn(async () => response(quality)) as unknown as typeof fetch }); expect((await client.intelligenceQuality("wf")).technicalDebt.items).toBe(12); });
  it("does not expose an analysis write method", () => { const client = new BridgeClient(); expect("intelligenceAnalyze" in client).toBe(false); });
  it("does not expose a decision approval method", () => { const client = new BridgeClient(); expect("approveDecision" in client).toBe(false); });
  it("does not expose an apply proposal method", () => { const client = new BridgeClient(); expect("applyProposal" in client).toBe(false); });
  it("does not expose a refactor method", () => { const client = new BridgeClient(); expect("refactor" in client).toBe(false); });

  const queryKinds = ["architecture", "dependency", "test", "security", "maintenance"];
  it.each(queryKinds)("supports %s response shape", async (kind) => { const client = new BridgeClient({ fetchImpl: vi.fn(async () => response({ project: "demo", insights: [{ ...insight, type: kind }], readOnly: true })) as unknown as typeof fetch }); const result = await client.intelligenceInsights("demo"); expect(result.insights[0].type).toBe(kind); });
  const projectNames = ["demo", "alpha", "repo-1", "project with spaces", "中文项目"];
  it.each(projectNames)("requests project %s", async (project) => { const fetchImpl = vi.fn(async () => response({ project, insights: [], readOnly: true })); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceInsights(project); expect(fetchImpl).toHaveBeenCalledTimes(1); });
  const workflowIds = ["wf_1", "wf_abc", "workflow-2", "team-review", "phase13"];
  it.each(workflowIds)("requests quality workflow %s", async (workflowId) => { const fetchImpl = vi.fn(async () => response(quality)); await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceQuality(workflowId); expect(fetchImpl).toHaveBeenCalledTimes(1); });
});

describe("read-only contract", () => {
  it("renders all major engineering sections", () => { const text = dashboard().textContent ?? ""; expect(text).toContain("Risk signals"); expect(text).toContain("Active proposals"); expect(text).toContain("Pending decisions"); });
  it("renders no link controls", () => { expect(dashboard().querySelectorAll("a")).toHaveLength(0); });
  it("keeps dashboard data text-only", () => { expect(dashboard().querySelectorAll("input,button,select,textarea,a")).toHaveLength(0); });
  it("does not mutate supplied insight", () => { const before = JSON.stringify(insight); dashboard(); expect(JSON.stringify(insight)).toBe(before); });
  it("does not mutate supplied proposal", () => { const before = JSON.stringify(proposal); dashboard(); expect(JSON.stringify(proposal)).toBe(before); });
  it("does not mutate supplied decision", () => { const before = JSON.stringify(decision); dashboard(); expect(JSON.stringify(decision)).toBe(before); });
  it("keeps a stable role marker", () => { expect(dashboard().getAttribute("data-role")).toBe("engineering-intelligence-dashboard"); });
  it("keeps the analysis badge", () => { expect(dashboard().querySelector(".engineering-intelligence-badge")?.textContent).toBe("ANALYSIS · READ ONLY"); });
  it("handles empty all-data state", () => { const root = dashboard([], [], [], null); expect(root.textContent).toContain("No analyzed risks yet"); expect(root.textContent).toContain("No proposals yet"); expect(root.textContent).toContain("No decisions recorded"); });
  it("does not create event handlers", () => { const root = dashboard(); expect(root.querySelectorAll("[onclick]")).toHaveLength(0); });
});
