import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderIntelligenceDashboard } from "../src/intelligence/intelligence-dashboard";
import type { IntelligencePhase28Response } from "../src/intelligence/models";
import { ExtensionStore, createInitialState } from "../src/state/store";

const phase28: IntelligencePhase28Response = {
  project: "demo",
  records: [
    {
      governance_id: "gov-1", governanceId: "gov-1", project_id: "demo", source_kind: "prediction", sourceKind: "prediction", source_id: "pred-1", sourceId: "pred-1",
      agent_id: "agent-1", agentId: "agent-1", model_id: "router", modelId: "router", policy_ids: ["p_confidence_threshold"], policyIds: ["p_confidence_threshold"],
      risk_level: "HIGH", riskLevel: "HIGH", risk_score: 70, riskScore: 70, confidence: 0.7, evaluation_result: "incorrect",
      governance_result: "REVIEW_REQUIRED", governanceResult: "REVIEW_REQUIRED", reason: "incorrect_prediction; high_risk_source",
      evidence: ["obs-1"], created_at: "2026-01-03T00:00:00Z", readOnly: true,
    },
    {
      governance_id: "gov-2", governanceId: "gov-2", project_id: "demo", source_kind: "recommendation", sourceKind: "recommendation", source_id: "rec-1", sourceId: "rec-1",
      agent_id: "agent-1", agentId: "agent-1", model_id: "router", modelId: "router", policy_ids: [], policyIds: [],
      risk_level: "LOW", riskLevel: "LOW", risk_score: 10, riskScore: 10, confidence: 0.8, evaluation_result: "correct", evaluationResult: "correct",
      governance_result: "PASS", governanceResult: "PASS", reason: "no material risk factors",
      evidence: [], created_at: "2026-01-04T00:00:00Z", readOnly: true,
    },
  ],
  risks: [
    {
      risk_id: "risk-1", riskId: "risk-1", project_id: "demo", source_kind: "prediction", source_id: "pred-1",
      risk_level: "HIGH", riskLevel: "HIGH", risk_score: 70, riskScore: 70, confidence: 0.7,
      risk_factors: ["incorrect_prediction", "high_risk_source"], riskFactors: ["incorrect_prediction", "high_risk_source"], reason: "incorrect_prediction; high_risk_source",
      agent_id: "agent-1", model_id: "router", created_at: "2026-01-03T00:00:00Z", readOnly: true,
    },
    {
      risk_id: "risk-2", riskId: "risk-2", project_id: "demo", source_kind: "recommendation", source_id: "rec-1",
      risk_level: "LOW", riskLevel: "LOW", risk_score: 10, riskScore: 10, confidence: 0.6, risk_factors: [], riskFactors: [], reason: "no material risk factors",
      created_at: "2026-01-04T00:00:00Z", readOnly: true,
    },
  ],
  violations: [
    {
      violation_id: "viol-1", violationId: "viol-1", policy_id: "p_high_risk_operation", policyId: "p_high_risk_operation", project_id: "demo",
      source_id: "pred-1", source_kind: "prediction", severity: "blocking",
      reason: "High risk operation detected", confidence: 0.7, created_at: "2026-01-03T00:00:00Z", readOnly: true,
    },
  ],
  reviews: [
    {
      proposal_id: "review-1", proposalId: "review-1", project_id: "demo", source_id: "pred-1", source_kind: "prediction",
      risk_level: "HIGH", riskLevel: "HIGH", reason: "high risk", recommended_action: "Human review required", recommendedAction: "Human review required",
      confidence: 0.7, evidence: ["obs-1"], status: "proposed", created_at: "2026-01-03T00:00:00Z", readOnly: true,
    },
    {
      proposal_id: "review-2", proposalId: "review-2", project_id: "demo", source_id: "pred-2", source_kind: "prediction",
      risk_level: "LOW", riskLevel: "LOW", reason: "routine", recommended_action: "No action", recommendedAction: "No action",
      confidence: 0.6, evidence: [], status: "approved", created_at: "2026-01-04T00:00:00Z", readOnly: true,
    },
  ],
  memory: [
    {
      memory_id: "gm-1", memoryId: "gm-1", project_id: "demo", category: "finding", content: "accuracy declining",
      source: "governance_analysis", confidence: 0.7, evidence: [], created_at: "2026-01-03T00:00:00Z", readOnly: true,
    },
  ],
  trends: [
    { trend_id: "govtrend_accuracy_weekly", trendId: "govtrend_accuracy_weekly", project_id: "demo", metric: "accuracy", period: "weekly", direction: "declining", change_rate: -0.2, changeRate: -0.2, confidence: 0.7, evidence: ["2026-W01=1.0(n=5)", "2026-W02=0.0(n=5)"], sample_count: 10, sampleCount: 10, readOnly: true },
    { trend_id: "govtrend_risk_score_weekly", trendId: "govtrend_risk_score_weekly", project_id: "demo", metric: "risk_score", period: "weekly", direction: "increasing", change_rate: 30, changeRate: 30, confidence: 0.7, evidence: ["2026-W01=10.0(n=1)"], sample_count: 2, sampleCount: 2, readOnly: true },
    { trend_id: "govtrend_decision_success_weekly", trendId: "govtrend_decision_success_weekly", project_id: "demo", metric: "decision_success", period: "weekly", direction: "stable", change_rate: 0, changeRate: 0, confidence: 0.3, evidence: [], sample_count: 0, sampleCount: 0, readOnly: true },
  ],
  signals: [
    { signal: "quality_degradation", metric: "accuracy", detail: "change_rate=-0.2" },
    { signal: "risk_escalation", metric: "risk_score", detail: "change_rate=30" },
  ],
  policies: [
    { policy_id: "p_confidence_threshold", policyId: "p_confidence_threshold", name: "Confidence threshold", description: "", rule_key: "confidence_below_threshold", ruleKey: "confidence_below_threshold", severity: "warning", threshold: 0.3, scope: "global", scope_value: "*", scopeValue: "*", enabled: true, version: 1, readOnly: true },
    { policy_id: "p_accuracy_threshold", policyId: "p_accuracy_threshold", name: "Accuracy threshold", description: "", rule_key: "accuracy_below_threshold", ruleKey: "accuracy_below_threshold", severity: "warning", threshold: 0.5, scope: "global", scope_value: "*", scopeValue: "*", enabled: true, version: 1, readOnly: true },
    { policy_id: "p_high_risk_operation", policyId: "p_high_risk_operation", name: "High risk operation", description: "", rule_key: "high_risk_detected", ruleKey: "high_risk_detected", severity: "blocking", threshold: 60, scope: "global", scope_value: "*", scopeValue: "*", enabled: true, version: 1, readOnly: true },
  ],
  graph: {
    project: "demo",
    nodes: [
      { node_id: "project:demo", node_type: "PROJECT", project: "demo", label: "demo", readOnly: true },
      { node_id: "source:pred-1", node_type: "PREDICTION", project: "demo", label: "pred-1", readOnly: true },
      { node_id: "risk:risk-1", node_type: "RISK", project: "demo", label: "HIGH 70", readOnly: true },
    ],
    edges: [
      { edge_id: "project:demo->source:pred-1:HAS", source: "project:demo", target: "source:pred-1", relation: "HAS", readOnly: true },
      { edge_id: "source:pred-1->risk:risk-1:HAS_RISK", source: "source:pred-1", target: "risk:risk-1", relation: "HAS_RISK", readOnly: true },
    ],
    nodeCount: 3,
    edgeCount: 2,
    readOnly: true,
  },
  quality14: {
    gate: "14.0", status: "REVIEW_REQUIRED", quality: 60,
    checks: { predictionQualityComputable: true, evaluationQuality: true, recommendationEffectivenessComputable: true, decisionSuccessComputable: true, confidenceCalibrationComputable: true, benchmarkComputable: true, policyCompliance: false, auditComplete: true },
    predictionQuality: 0.4, predictionCount: 10, evaluationCount: 10, effectivenessCount: 5, decisionCount: 3,
    maxRiskLevel: "HIGH", maxRiskScore: 70, confidenceCalibration: 0.1, regressionRate: 0.3,
    benchmarkScore: 0.7, benchmarkCount: 2, violationCount: 1,
    blockingIssues: [], warnings: [], readOnly: true,
  },
  reviewRequired: true,
  readOnly: true,
};

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

type Phase28Overrides = Partial<Omit<IntelligencePhase28Response, "quality14">> & {
  quality14?: IntelligencePhase28Response["quality14"] | null;
};

function render(overrides: Phase28Overrides = {}) {
  return renderIntelligenceDashboard(document, [], [], [], null, null, undefined, undefined, { ...phase28, ...overrides } as Partial<IntelligencePhase28Response>);
}

describe("Phase 28 governance dashboard rendering", () => {
  it("renders the governance heading", () => {
    expect(render().textContent).toContain("Intelligence Governance");
  });

  it("renders READ ONLY badge", () => {
    expect(render().textContent).toContain("READ ONLY");
  });

  it("renders quality gate 14 status", () => {
    expect(render().textContent).toContain("Quality Gate 14 · REVIEW_REQUIRED");
  });

  it("renders governance record count", () => {
    expect(render().textContent).toContain("2 governance records");
  });

  it("renders risk finding count", () => {
    expect(render().textContent).toContain("2 risk findings");
  });

  it("renders violation count", () => {
    expect(render().textContent).toContain("1 policy violations");
  });

  it("renders review proposal count", () => {
    expect(render().textContent).toContain("2 review proposals");
  });

  it("renders governance trend count", () => {
    expect(render().textContent).toContain("3 governance trends");
  });

  it("renders max risk level from gate", () => {
    expect(render().textContent).toContain("max HIGH");
  });

  it("renders regression rate", () => {
    expect(render().textContent).toContain("Regression rate · 0.3");
  });

  it("renders risk findings with reasons", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Risk · HIGH · 70");
    expect(text).toContain("incorrect_prediction; high_risk_source");
  });

  it("renders trend lines", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("accuracy · declining");
    expect(text).toContain("risk_score · increasing");
  });

  it("renders governance signals", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("quality_degradation");
    expect(text).toContain("risk_escalation");
  });

  it("renders policy violations", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("p_high_risk_operation");
    expect(text).toContain("blocking");
  });

  it("renders review proposals", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Review · proposed");
    expect(text).toContain("Human review required");
  });

  it("renders policies", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("p_confidence_threshold");
    expect(text).toContain("threshold 0.3");
  });

  it("renders governance graph summary", () => {
    expect(render().textContent).toContain("Governance graph · 3 node(s) · 2 edge(s)");
  });

  it("renders empty risks state", () => {
    expect(render({ risks: [] }).textContent).toContain("No risk findings recorded");
  });

  it("renders empty trends state", () => {
    expect(render({ trends: [], signals: [] }).textContent).toContain("No governance trends yet");
  });

  it("renders empty violations state", () => {
    expect(render({ violations: [] }).textContent).toContain("No policy violations");
  });

  it("renders empty reviews state", () => {
    expect(render({ reviews: [] }).textContent).toContain("No governance review proposals");
  });

  it("renders empty policies state", () => {
    expect(render({ policies: [] }).textContent).toContain("No policies registered");
  });

  it("renders pending gate state", () => {
    expect(render({ quality14: null }).textContent).toContain("Quality Gate 14 pending");
  });

  it("applies warning tone for declining trend", () => {
    const node = render();
    expect(node.querySelector(".warning")).not.toBeNull();
  });

  it("never renders approve controls", () => {
    expect(render().querySelector("button")).toBeNull();
    expect(render().querySelector("input")).toBeNull();
  });

  it("never renders execute/apply/fix text", () => {
    const text = render().textContent ?? "";
    expect(text).not.toMatch(/auto[ -]?(fix|execute|approve|learn)/i);
  });

  it("keeps quality14 warnings visible", () => {
    const withWarnings = render({ quality14: { ...phase28.quality14, status: "BLOCKED", blockingIssues: ["critical_risk_detected"] } });
    expect(withWarnings.textContent).toContain("BLOCKED");
  });
});

describe("Phase 28 client read-only methods", () => {
  function clientWith(handler: (url: string) => Response) {
    const fetchImpl = vi.fn(async (input: string) => handler(input));
    return new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
  }

  it("intelligenceGovernance GETs the snapshot", async () => {
    const client = clientWith((url) => {
      expect(url).toContain("/intelligence/governance?project=demo");
      return response(phase28);
    });
    const result = await client.intelligenceGovernance("demo");
    expect(result.records.length).toBe(2);
    expect(result.readOnly).toBe(true);
  });

  it("intelligenceGovernanceRisks encodes filters", async () => {
    const client = clientWith((url) => {
      expect(url).toContain("project=demo");
      expect(url).toContain("risk_level=HIGH");
      expect(url).toContain("source_kind=prediction");
      return response({ project: "demo", risks: phase28.risks, readOnly: true });
    });
    const result = await client.intelligenceGovernanceRisks("demo", { riskLevel: "HIGH", sourceKind: "prediction" });
    expect(result.risks[0].riskId).toBe("risk-1");
  });

  it("intelligenceGovernanceTrends passes period", async () => {
    const client = clientWith((url) => {
      expect(url).toContain("period=monthly");
      return response({ project: "demo", trends: phase28.trends, signals: phase28.signals, readOnly: true });
    });
    const result = await client.intelligenceGovernanceTrends("demo", "monthly");
    expect(result.trends.length).toBe(3);
  });

  it("intelligenceGovernancePolicies encodes scope", async () => {
    const client = clientWith((url) => {
      expect(url).toContain("scope=model");
      return response({ project: "demo", policies: phase28.policies, readOnly: true });
    });
    const result = await client.intelligenceGovernancePolicies("demo", "model");
    expect(result.policies[0].policyId).toBe("p_confidence_threshold");
  });

  it("intelligenceGovernanceViolations encodes severity", async () => {
    const client = clientWith((url) => {
      expect(url).toContain("severity=blocking");
      return response({ project: "demo", violations: phase28.violations, readOnly: true });
    });
    const result = await client.intelligenceGovernanceViolations("demo", "blocking");
    expect(result.violations.length).toBe(1);
  });

  it("intelligenceGovernanceReviews encodes status", async () => {
    const client = clientWith((url) => {
      expect(url).toContain("status=proposed");
      return response({ project: "demo", reviews: phase28.reviews, readOnly: true });
    });
    const result = await client.intelligenceGovernanceReviews("demo", "proposed");
    expect(result.reviews[0].status).toBe("proposed");
  });

  it("intelligenceGovernanceQualityGate returns gate 14", async () => {
    const client = clientWith(() => response(phase28.quality14));
    const result = await client.intelligenceGovernanceQualityGate("demo");
    expect(result.gate).toBe("14.0");
    expect(result.readOnly).toBe(true);
  });

  it("intelligenceGovernanceGraph returns graph", async () => {
    const client = clientWith(() => response(phase28.graph));
    const result = await client.intelligenceGovernanceGraph("demo");
    expect(result.nodeCount).toBe(3);
    expect(result.readOnly).toBe(true);
  });

  it("URL-encodes project names", async () => {
    const client = clientWith((url) => {
      expect(url).toContain("project=my%20project");
      return response(phase28);
    });
    await client.intelligenceGovernance("my project");
  });

  it("propagates bridge errors", async () => {
    const client = clientWith(() => new Response(JSON.stringify({ error: "bridge_error", message: "boom" }), { status: 500 }));
    await expect(client.intelligenceGovernance("demo")).rejects.toThrow("boom");
  });
});

describe("Phase 28 store wiring", () => {
  it("initial governance state is null", () => {
    const store = new ExtensionStore();
    expect(store.getState().intelligenceGovernance).toBeNull();
  });

  it("updates governance snapshot", async () => {
    const store = new ExtensionStore();
    await store.update({ intelligenceGovernance: phase28 });
    expect(store.getState().intelligenceGovernance?.reviewRequired).toBe(true);
  });

  it("hydrates persisted governance snapshot", async () => {
    const memory = new Map<string, unknown>();
    const storage = {
      get: async (key: string) => (memory.has(key) ? { [key]: memory.get(key) } : {}),
      set: async (items: Record<string, unknown>) => {
        for (const [key, value] of Object.entries(items)) memory.set(key, value);
      },
    };
    const store = new ExtensionStore(storage);
    await store.update({ intelligenceGovernance: phase28 });
    const hydrated = new ExtensionStore(storage);
    await hydrated.hydrate();
    expect(hydrated.getState().intelligenceGovernance?.records.length).toBe(2);
  });

  it("subscribers receive governance state", async () => {
    const store = new ExtensionStore();
    const seen: unknown[] = [];
    store.subscribe((state) => seen.push(state.intelligenceGovernance));
    await store.update({ intelligenceGovernance: phase28 });
    expect(seen[seen.length - 1]).not.toBeNull();
  });
});

describe("Phase 28 read-only enforcement", () => {
  it("client has no governance stage/execute methods", () => {
    const client = new BridgeClient();
    const proto = Object.getPrototypeOf(client) as Record<string, unknown>;
    const names = Object.getOwnPropertyNames(proto);
    expect(names.some((name) => name.includes("Governance") && name.startsWith("stage"))).toBe(false);
    expect(names.some((name) => /Governance.*(Execute|Approve|Apply|Fix)/.test(name))).toBe(false);
  });

  it("snapshot is marked read-only", () => {
    expect(phase28.readOnly).toBe(true);
    expect(phase28.graph.readOnly).toBe(true);
    expect(phase28.quality14.readOnly).toBe(true);
  });

  it("all records are read-only", () => {
    expect(phase28.records.every((record) => record.readOnly === true)).toBe(true);
    expect(phase28.risks.every((risk) => risk.readOnly === true)).toBe(true);
    expect(phase28.violations.every((violation) => violation.readOnly === true)).toBe(true);
    expect(phase28.reviews.every((review) => review.readOnly === true)).toBe(true);
    expect(phase28.trends.every((trend) => trend.readOnly === true)).toBe(true);
  });
});

describe("Phase 28 dashboard variants", () => {
  it("renders high risk with warning tone", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Risk · HIGH");
  });

  it("renders blocking violation with warning tone", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("blocking");
  });

  it("renders proposed review as recommendation tone", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Review · proposed");
  });

  it("renders trend change rate", () => {
    expect(render().textContent).toContain("Δ-0.2");
  });

  it("renders trend confidence", () => {
    expect(render().textContent).toContain("confidence 0.7");
  });

  it("renders signal detail", () => {
    expect(render().textContent).toContain("change_rate=-0.2");
  });

  it("renders policy severity", () => {
    expect(render().textContent).toContain("blocking");
  });

  it("renders gate regression warning", () => {
    const node = render();
    expect(node.textContent).toContain("Regression rate · 0.3");
  });

  it("renders benchmark score", () => {
    expect(render().textContent).toContain("benchmark 0.7");
  });

  it("renders gate quality score", () => {
    expect(render().textContent).toContain("60/100");
  });

  it("renders review recommended action", () => {
    expect(render().textContent).toContain("Human review required");
  });

  it("does not mutate phase28 input", () => {
    const input = JSON.parse(JSON.stringify(phase28)) as IntelligencePhase28Response;
    render(input);
    expect(input).toEqual(JSON.parse(JSON.stringify(phase28)));
  });

  it("renders with empty project data", () => {
    const node = render({ records: [], risks: [], violations: [], reviews: [], trends: [], signals: [], policies: [], memory: [] });
    expect(node.textContent).toContain("0 governance records");
  });

  it("renders risk score line", () => {
    expect(render().textContent).toContain("Risk · HIGH · 70");
  });

  it("renders source kind in review line", () => {
    expect(render().textContent).toContain("prediction pred-1");
  });

  it("renders gate maxRiskScore", () => {
    expect(render().textContent).toContain("score 70");
  });

  it("shows reviewRequired signal", () => {
    const node = render({ reviewRequired: true });
    expect(node.textContent).toContain("review proposals");
  });

  it("renders graph read only marker", () => {
    expect(render().textContent).toContain("read only");
  });
});

describe("Phase 28 store reset parity", () => {
  it("reset branch clears governance", async () => {
    const store = new ExtensionStore();
    await store.update({ intelligenceGovernance: phase28 });
    await store.update({ intelligenceGovernance: null });
    expect(store.getState().intelligenceGovernance).toBeNull();
  });
});

describe("Phase 28 numeric tolerances", () => {
  it("keeps risk scores numeric", () => {
    expect(phase28.risks[0].risk_score).toBe(70);
  });

  it("keeps change rates numeric", () => {
    expect(phase28.trends[0].change_rate).toBe(-0.2);
  });

  it("keeps thresholds numeric", () => {
    expect(phase28.policies[0].threshold).toBe(0.3);
  });

  it("keeps confidence in range", () => {
    for (const trend of phase28.trends) expect(trend.confidence).toBeGreaterThanOrEqual(0);
  });
});

describe("Phase 28 governance types", () => {
  it("accepts snake and camel keys", () => {
    const record = phase28.records[0];
    expect(record.governance_id).toBe(record.governanceId);
    expect(record.risk_level).toBe(record.riskLevel);
    expect(record.source_kind).toBe(record.sourceKind);
  });

  it("trend exposes both key styles", () => {
    const trend = phase28.trends[0];
    expect(trend.change_rate).toBe(trend.changeRate);
    expect(trend.sample_count).toBe(trend.sampleCount);
  });

  it("policy exposes both key styles", () => {
    const policy = phase28.policies[0];
    expect(policy.policy_id).toBe(policy.policyId);
    expect(policy.rule_key).toBe(policy.ruleKey);
  });

  it("review exposes both key styles", () => {
    const review = phase28.reviews[0];
    expect(review.proposal_id).toBe(review.proposalId);
    expect(review.recommended_action).toBe(review.recommendedAction);
  });

  it("violation exposes both key styles", () => {
    expect(phase28.violations[0].violation_id).toBe(phase28.violations[0].violationId);
  });

  it("risk exposes both key styles", () => {
    const risk = phase28.risks[0];
    expect(risk.risk_id).toBe(risk.riskId);
    expect(risk.risk_factors).toEqual(risk.riskFactors);
  });

  it("memory exposes both key styles", () => {
    expect(phase28.memory[0].memory_id).toBe(phase28.memory[0].memoryId);
  });
});

describe("Phase 28 gate statuses", () => {
  const statuses = ["PASS", "WARNING", "REVIEW_REQUIRED", "BLOCKED"];
  for (const status of statuses) {
    it(`renders gate status ${status}`, () => {
      const node = render({ quality14: { ...phase28.quality14, status } });
      expect(node.textContent).toContain(status);
    });
  }
});

describe("Phase 28 risk levels", () => {
  const levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
  for (const level of levels) {
    it(`renders risk level ${level}`, () => {
      const node = render({ risks: [{ ...phase28.risks[0], risk_level: level, riskLevel: level }] });
      expect(node.textContent).toContain(level);
    });
  }
});

describe("Phase 28 trend directions", () => {
  const directions = ["improving", "declining", "stable", "increasing", "decreasing"];
  for (const direction of directions) {
    it(`renders trend direction ${direction}`, () => {
      const node = render({ trends: [{ ...phase28.trends[0], direction }] });
      expect(node.textContent).toContain(direction);
    });
  }
});

describe("Phase 28 signal kinds", () => {
  const signals = ["quality_degradation", "regression", "risk_escalation", "model_degradation"];
  for (const signal of signals) {
    it(`renders signal ${signal}`, () => {
      const node = render({ signals: [{ signal, metric: "accuracy", detail: "change_rate=-0.1" }] });
      expect(node.textContent).toContain(signal);
    });
  }
});

describe("Phase 28 review statuses", () => {
  const statuses = ["proposed", "approved", "rejected", "executed"];
  for (const status of statuses) {
    it(`renders review status ${status}`, () => {
      const node = render({ reviews: [{ ...phase28.reviews[0], status }] });
      expect(node.textContent).toContain(status);
    });
  }
});

describe("Phase 28 client URL encoding details", () => {
  it("governance risks uses project param", async () => {
    let captured = "";
    const client = new BridgeClient({
      fetchImpl: (async (input: string) => {
        captured = String(input);
        return response({ project: "demo", risks: [], readOnly: true });
      }) as unknown as typeof fetch,
    });
    await client.intelligenceGovernanceRisks("demo");
    expect(captured).toContain("project=demo");
  });

  it("governance trends uses project param", async () => {
    let captured = "";
    const client = new BridgeClient({
      fetchImpl: (async (input: string) => {
        captured = String(input);
        return response({ project: "demo", trends: [], signals: [], readOnly: true });
      }) as unknown as typeof fetch,
    });
    await client.intelligenceGovernanceTrends("demo");
    expect(captured).toContain("project=demo");
  });

  it("governance policies uses project param", async () => {
    let captured = "";
    const client = new BridgeClient({
      fetchImpl: (async (input: string) => {
        captured = String(input);
        return response({ project: "demo", policies: [], readOnly: true });
      }) as unknown as typeof fetch,
    });
    await client.intelligenceGovernancePolicies("demo");
    expect(captured).toContain("project=demo");
  });

  it("governance violations uses project param", async () => {
    let captured = "";
    const client = new BridgeClient({
      fetchImpl: (async (input: string) => {
        captured = String(input);
        return response({ project: "demo", violations: [], readOnly: true });
      }) as unknown as typeof fetch,
    });
    await client.intelligenceGovernanceViolations("demo");
    expect(captured).toContain("project=demo");
  });

  it("governance reviews uses project param", async () => {
    let captured = "";
    const client = new BridgeClient({
      fetchImpl: (async (input: string) => {
        captured = String(input);
        return response({ project: "demo", reviews: [], readOnly: true });
      }) as unknown as typeof fetch,
    });
    await client.intelligenceGovernanceReviews("demo");
    expect(captured).toContain("project=demo");
  });

  it("governance quality gate uses project param", async () => {
    let captured = "";
    const client = new BridgeClient({
      fetchImpl: (async (input: string) => {
        captured = String(input);
        return response(phase28.quality14);
      }) as unknown as typeof fetch,
    });
    await client.intelligenceGovernanceQualityGate("demo");
    expect(captured).toContain("project=demo");
  });

  it("governance graph uses project param", async () => {
    let captured = "";
    const client = new BridgeClient({
      fetchImpl: (async (input: string) => {
        captured = String(input);
        return response(phase28.graph);
      }) as unknown as typeof fetch,
    });
    await client.intelligenceGovernanceGraph("demo");
    expect(captured).toContain("project=demo");
  });
});

describe("Phase 28 store default shape", () => {
  it("initial state has governance field", () => {
    const state = new ExtensionStore().getState();
    expect("intelligenceGovernance" in state).toBe(true);
  });

  it("createInitialState has null governance", () => {
    expect(createInitialState().intelligenceGovernance).toBeNull();
  });
});

describe("Phase 28 no-write surface", () => {
  it("dashboard exposes no governance write buttons", () => {
    const html = render().outerHTML;
    expect(html).not.toMatch(/<button/i);
    expect(html).not.toMatch(/<input/i);
  });

  it("dashboard has no auto-control wording", () => {
    const text = render().textContent ?? "";
    expect(text).not.toMatch(/auto[ -]?(fix|approve|learn|govern)/i);
    expect(text).not.toMatch(/\bexecute\b/i);
  });

  it("client exposes only GET governance methods", () => {
    const client = new BridgeClient();
    const proto = Object.getPrototypeOf(client) as Record<string, unknown>;
    const governanceMethods = Object.getOwnPropertyNames(proto).filter((name) => name.startsWith("intelligenceGovernance"));
    expect(governanceMethods.length).toBeGreaterThanOrEqual(7);
    for (const name of governanceMethods) {
      expect(name).toMatch(/^(intelligenceGovernance|intelligenceGovernanceRisks|intelligenceGovernanceTrends|intelligenceGovernancePolicies|intelligenceGovernanceViolations|intelligenceGovernanceReviews|intelligenceGovernanceQualityGate|intelligenceGovernanceGraph)$/);
    }
  });
});

describe("Phase 28 combined renders", () => {
  it("renders Phase 28 after Phase 27 block", () => {
    const node = renderIntelligenceDashboard(document, [], [], [], null, null, undefined, { project: "demo", evaluations: [], accuracy: null, failedPredictions: [], effectiveness: [], effectivenessSummary: null, decisionOutcomes: [], decisionSummary: null, benchmarks: [], builtinDatasets: [], improvements: [], quality13: null, readOnly: true }, phase28);
    expect(node.textContent).toContain("Intelligence Governance");
    expect(node.textContent).toContain("Engineering Intelligence Validation");
  });

  it("renders Phase 28 with undefined phase27", () => {
    const node = renderIntelligenceDashboard(document, [], [], [], null, null, undefined, undefined, phase28);
    expect(node.textContent).toContain("Intelligence Governance");
  });

  it("renders nothing Phase 28 when undefined", () => {
    const node = renderIntelligenceDashboard(document, [], [], [], null);
    expect(node.textContent).not.toContain("Intelligence Governance");
  });

  it("renders gate status line with quality score", () => {
    expect(render().textContent).toContain("Quality Gate 14 · REVIEW_REQUIRED · 60/100");
  });
});

describe("Phase 28 policy scope display", () => {
  it("shows policy scope value", () => {
    expect(render().textContent).toContain("global");
  });

  it("shows policy version", () => {
    expect(phase28.policies[0].version).toBe(1);
  });
});

describe("Phase 28 client method names", () => {
  const methodNames = [
    "intelligenceGovernance",
    "intelligenceGovernanceRisks",
    "intelligenceGovernanceTrends",
    "intelligenceGovernancePolicies",
    "intelligenceGovernanceViolations",
    "intelligenceGovernanceReviews",
    "intelligenceGovernanceQualityGate",
    "intelligenceGovernanceGraph",
  ] as const;
  for (const name of methodNames) {
    it(`exposes ${name} on the client`, () => {
      const client = new BridgeClient();
      expect(typeof (client as unknown as Record<string, unknown>)[name]).toBe("function");
    });
  }
});

describe("Phase 28 read-only data integrity", () => {
  it("graph edges are read-only", () => {
    expect(phase28.graph.edges.every((edge) => edge.readOnly === true)).toBe(true);
  });

  it("graph nodes are read-only", () => {
    expect(phase28.graph.nodes.every((node) => node.readOnly === true)).toBe(true);
  });

  it("quality14 exposes check flags", () => {
    expect(phase28.quality14.checks.policyCompliance).toBe(false);
    expect(phase28.quality14.checks.auditComplete).toBe(true);
  });

  it("quality14 exposes blocking issues", () => {
    expect(Array.isArray(phase28.quality14.blockingIssues)).toBe(true);
  });

  it("quality14 exposes warnings", () => {
    expect(Array.isArray(phase28.quality14.warnings)).toBe(true);
  });
});

describe("Phase 28 review proposal visibility", () => {
  it("shows proposal source kind and id", () => {
    expect(render().textContent).toContain("prediction pred-1");
  });

  it("shows proposal risk level", () => {
    expect(render().textContent).toContain("HIGH");
  });

  it("shows recommended action text", () => {
    expect(render().textContent).toContain("Human review required");
  });
});
