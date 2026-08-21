import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderIntelligenceDashboard } from "../src/intelligence/intelligence-dashboard";
import type { EngineeringObservation, IntelligenceEvidenceBundle, IntelligenceKnowledgeRecord, IntelligencePattern, IntelligencePrediction, IntelligenceQuality11, IntelligenceRecommendation, StrategyOutcomeRecord } from "../src/intelligence/models";

const observation: EngineeringObservation = { id: "obs_1", project_id: "demo", timestamp: "2026-01-01T00:00:00Z", type: "test_result", source: "pytest", summary: "test failed", metadata: {}, risk_level: "high", readOnly: true };
const pattern: IntelligencePattern = { pattern_id: "pat_1", project_id: "demo", pattern_type: "repeated_failure", evidence: ["obs_1"], similar_history: [], confidence: 0.7, summary: "Repeated failure", created_at: "2026-01-01T00:00:00Z", readOnly: true };
const prediction: IntelligencePrediction = { prediction_id: "pred_1", project_id: "demo", prediction_type: "test_failure_risk", prediction: "Elevated test failure risk", confidence: 0.78, evidence: ["obs_1"], observations: ["obs_1"], risk_level: "high", created_at: "2026-01-01T00:00:00Z", readOnly: true };
const recommendation: IntelligenceRecommendation = { recommendation_id: "rec_1", project_id: "demo", prediction_id: "pred_1", recommendation: "Review focused tests", rationale: "Repeated failure", evidence: ["obs_1"], confidence: 0.78, risk_level: "high", readOnly: true };
const outcome: StrategyOutcomeRecord = { outcome_id: "out_1", project_id: "demo", strategy_id: "strategy_1", decision_id: "decision_1", status: "PARTIAL_SUCCESS", expected_outcome: "stable build", actual_outcome: "one warning", difference: "warning remained", evidence: ["obs_1"], source: "build_result", confidence: 0.6, created_at: "2026-01-01T00:00:00Z", readOnly: true };
const knowledge: IntelligenceKnowledgeRecord = { id: "knowledge_1", project_id: "demo", category: "patterns", content: "Repeated failure", source: "human_review", evidence: ["obs_1"], confidence: 0.8, created_at: "2026-01-01T00:00:00Z", metadata: {}, readOnly: true };
const evidence: IntelligenceEvidenceBundle = { bundle_id: "evidence_1", project_id: "demo", decision_id: "decision_1", observation_ids: ["obs_1"], pattern_ids: ["pat_1"], prediction_ids: ["pred_1"], risk_ids: [], strategy_ids: ["strategy_1"], recommendation_ids: ["rec_1"], historical_evidence: [], provenance: ["pytest"], confidence: 0.8, created_at: "2026-01-01T00:00:00Z", readOnly: true };
const quality: IntelligenceQuality11 = { project: "demo", gate: "11.0", status: "WARN", quality: 86, checks: { observationIntegrity: true, patternEvidence: true, predictionConfidence: 0.78, recommendationTraceability: true, decisionEvidence: true, outcomeCompleteness: true, knowledgeProvenance: true }, observationCount: 1, patternCount: 1, predictionCount: 1, recommendationCount: 1, decisionCount: 0, outcomeCount: 1, knowledgeCount: 1, blockingIssues: [], warnings: ["prediction_confidence_low"], readOnly: true };

const emptyBase = renderIntelligenceDashboard(document, [], [], [], null);

describe("Phase 25 intelligence dashboard", () => {
  it("renders the evolution timeline as read-only text", () => {
    const root = renderIntelligenceDashboard(document, [], [], [], null, { project: "demo", observations: [observation], patterns: [pattern], predictions: [prediction], recommendations: [recommendation], outcomes: [outcome], knowledge: [knowledge], evidence: [evidence], quality, readOnly: true });
    expect(root.dataset.role).toBe("engineering-intelligence-dashboard");
    expect(root.textContent).toContain("Observation → Pattern → Prediction");
    expect(root.textContent).toContain("HIGH · test_failure_risk · confidence 0.78");
    expect(root.textContent).toContain("Review focused tests");
    expect(root.textContent).toContain("Quality Gate 11 · WARN");
    expect(root.textContent).toContain("1 outcomes");
    expect(root.textContent).toContain("Knowledge · patterns");
    expect(root.textContent).toContain("Evidence · evidence_1");
  });

  it("does not render controls or action words", () => {
    const root = renderIntelligenceDashboard(document, [], [], [], null, { project: "demo", observations: [observation], patterns: [pattern], predictions: [prediction], recommendations: [recommendation], outcomes: [outcome], knowledge: [knowledge], evidence: [evidence], quality, readOnly: true });
    expect(root.querySelectorAll("button,input,select,textarea,a")).toHaveLength(0);
    expect(root.textContent?.toLowerCase()).not.toContain("execute");
    expect(root.textContent?.toLowerCase()).not.toContain("approve");
  });

  it("keeps the legacy empty dashboard stable", () => {
    expect(emptyBase.dataset.role).toBe("engineering-intelligence-dashboard");
    expect(emptyBase.textContent).toContain("ANALYSIS · READ ONLY");
  });
});

describe("Phase 25 BridgeClient reads", () => {
  it.each([
    ["intelligenceObservations", "/intelligence/observations?project=demo", { project: "demo", observations: [observation], readOnly: true }],
    ["intelligencePatterns", "/intelligence/patterns?project=demo", { project: "demo", patterns: [pattern], readOnly: true }],
    ["intelligencePredictions", "/intelligence/predictions?project=demo", { project: "demo", predictions: [prediction], readOnly: true }],
    ["intelligenceRecommendations", "/intelligence/recommendations?project=demo", { project: "demo", recommendations: [recommendation], readOnly: true }],
    ["intelligenceOutcomes", "/intelligence/outcomes?project=demo", { project: "demo", outcomes: [], readOnly: true }],
    ["intelligenceKnowledge", "/intelligence/knowledge?project=demo", { project: "demo", knowledge: [], readOnly: true }],
    ["intelligenceEvidence", "/intelligence/evidence?project=demo", { project: "demo", evidence: [], readOnly: true }],
    ["intelligenceQuality11", "/intelligence/quality?project=demo", quality],
  ] as const)("loads %s with GET", async (method, path, body) => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => { expect(String(input)).toContain(path); expect(init?.method ?? "GET").toBe("GET"); return new Response(JSON.stringify(body), { status: 200 }); });
    await (new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch })[method] as (project: string) => Promise<unknown>)("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
