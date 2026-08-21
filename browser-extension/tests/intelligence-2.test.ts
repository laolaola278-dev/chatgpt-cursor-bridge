import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderIntelligenceDashboard } from "../src/intelligence/intelligence-dashboard";
import type { IntelligencePhase26Response } from "../src/intelligence/models";

const phase26: IntelligencePhase26Response = {
  project: "demo",
  trends: [{ trend_id: "trend-1", project_id: "demo", metric: "test_failure_trend", period: "daily", direction: "increasing", change_rate: 0.5, confidence: 0.72, evidence: ["obs-1"], readOnly: true }],
  correlations: [{ correlation_id: "corr-1", project_id: "demo", events: ["obs-1", "obs-2"], relationship: "code_change_followed_regression", confidence: 0.65, evidence: ["obs-1", "obs-2"], interpretation: "correlation_only", causation_claim: false, readOnly: true }],
  impact: [{ prediction_id: "impact-1", project_id: "demo", affected_files: ["src/parser.ts"], affected_modules: ["parser"], affected_tests: ["parser.test.ts"], risk_level: "HIGH", confidence: 0.74, evidence: ["obs-1"], why_risky: ["historical failure"], readOnly: true }],
  dependencies: [{ risk_id: "dep-1", project_id: "demo", dependency: "lib-x", risk: "HIGH", reason: "historical failure", historical_evidence: ["obs-2"], affected_components: ["parser"], confidence: 0.7, readOnly: true }],
  ranking: { project_id: "demo", ranked: [{ recommendation_id: "rec-1", project_id: "demo", rank: 1, priority: 0.8, confidence: 0.74, risk_reduction: 0.8, effort_estimate: "medium", evidence_strength: 0.6, recommendation: "Review parser tests", reason: "evidence", evidence: ["obs-1"], risk_level: "high", readOnly: true }], recommended_action: "Review parser tests", alternative_actions: [], reason: "evidence ranking", evidence: ["obs-1"], confidence: 0.74, humanDecisionRequired: true, readOnly: true },
  evaluations: [{ evaluation_id: "eval-1", project_id: "demo", prediction_id: "pred-1", predicted: true, actual: true, correct: true, confidence: 0.74, evaluated_at: "2026-01-03T00:00:00Z", evidence: ["obs-1"], readOnly: true }],
  metrics: { project_id: "demo", predictions: 1, correct: 1, incorrect: 0, accuracy: 1, precision: 1, recall: 1, false_positive_rate: 0, false_negative_rate: 0, recommendation_count: 1, recommendation_successes: 1, recommendation_success_rate: 1, readOnly: true },
  evidenceGraph: { project_id: "demo", nodes: [{ node_id: "obs-1", node_type: "OBSERVATION", project_id: "demo", label: "failure", metadata: {}, readOnly: true }], edges: [], readOnly: true },
  readOnly: true,
};

function response(body: unknown): Response { return new Response(JSON.stringify(body), { status: 200 }); }

describe("Phase 26 intelligence dashboard", () => {
  it("renders Phase 26 headings and counts", () => {
    const root = renderIntelligenceDashboard(document, [], [], [], null, null, phase26);
    expect(root.textContent).toContain("Engineering Intelligence 2.0");
    expect(root.textContent).toContain("1 trends");
    expect(root.textContent).toContain("1 impact predictions");
    expect(root.textContent).toContain("1 graph nodes");
  });

  it("renders trend, correlation, impact, and dependency evidence", () => {
    const text = renderIntelligenceDashboard(document, [], [], [], null, null, phase26).textContent ?? "";
    expect(text).toContain("Trend · test_failure_trend · increasing");
    expect(text).toContain("Correlation · code_change_followed_regression");
    expect(text).toContain("Impact · HIGH");
    expect(text).toContain("Dependency · HIGH · lib-x");
  });

  it("renders ranking and historical accuracy", () => {
    const text = renderIntelligenceDashboard(document, [], [], [], null, null, phase26).textContent ?? "";
    expect(text).toContain("Recommendation ranking");
    expect(text).toContain("Recommended · Review parser tests");
    expect(text).toContain("Prediction accuracy · 1");
  });

  it("has no controls or unsafe action labels", () => {
    const root = renderIntelligenceDashboard(document, [], [], [], null, null, phase26);
    expect(root.querySelectorAll("button,input,select,textarea,a")).toHaveLength(0);
    const text = root.textContent?.toLowerCase() ?? "";
    expect(text).not.toContain("execute");
    expect(text).not.toContain("approve");
    expect(text).not.toContain("auto-fix");
  });

  it.each(Array.from({ length: 25 }, (_, index) => index))("keeps phase26 output text-only %i", () => {
    const root = renderIntelligenceDashboard(document, [], [], [], null, null, phase26);
    expect(root.dataset.role).toBe("engineering-intelligence-dashboard");
    expect(root.querySelector("button")).toBeNull();
  });
});

describe("Phase 26 BridgeClient reads", () => {
  it.each([
    ["intelligenceTrends", "/intelligence/trends?project=demo&period=daily"],
    ["intelligenceCorrelations", "/intelligence/correlations?project=demo"],
    ["intelligenceImpact", "/intelligence/impact?project=demo"],
    ["intelligenceDependencies", "/intelligence/dependencies?project=demo"],
    ["intelligenceEvaluations", "/intelligence/evaluations?project=demo"],
    ["intelligenceRecommendationRanking", "/intelligence/recommendations/ranking?project=demo"],
    ["intelligenceEvidenceGraph", "/intelligence/evidence/graph?project=demo"],
  ] as const)("uses GET for %s", async (method, path) => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain(path);
      expect(init?.method ?? "GET").toBe("GET");
      return response(method === "intelligenceTrends" ? { project: "demo", trends: [], readOnly: true } : method === "intelligenceRecommendationRanking" ? { project_id: "demo", ranked: [], alternative_actions: [], evidence: [], confidence: 0, readOnly: true } : { project: "demo", readOnly: true, correlations: [], impact: [], predictions: [], dependencies: [], risks: [], evaluations: [], metrics: null, nodes: [], edges: [] });
    });
    const client = new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    await (client[method] as (project: string) => Promise<unknown>)("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("encodes changed files for impact reads", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => { expect(String(input)).toContain("changed_file=src%2Fparser.ts"); return response({ project: "demo", impact: [], predictions: [], readOnly: true }); });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceImpact("demo", ["src/parser.ts"]);
  });

  it("does not expose Phase 26 mutation helpers", () => {
    const client = new BridgeClient();
    expect("executePrediction" in client).toBe(false);
    expect("applyRecommendation" in client).toBe(false);
    expect("fixDependency" in client).toBe(false);
    expect("approveRecommendation" in client).toBe(false);
  });
});
