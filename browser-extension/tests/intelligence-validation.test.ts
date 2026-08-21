import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderIntelligenceDashboard } from "../src/intelligence/intelligence-dashboard";
import type { IntelligencePhase27Response } from "../src/intelligence/models";
import { ExtensionStore } from "../src/state/store";

const phase27: IntelligencePhase27Response = {
  project: "demo",
  evaluations: [
    { evaluation_id: "eval-1", project_id: "demo", prediction_id: "pred-1", evaluation_kind: "prediction", input_context: "parser change", prediction_result: "high regression risk", expected_outcome: "regression", actual_outcome: "regression occurred", evaluation_result: "correct", correct: true, confidence: 0.8, evaluated_at: "2026-01-03T00:00:00Z", evidence: ["obs-1"], readOnly: true },
    { evaluation_id: "eval-2", project_id: "demo", prediction_id: "pred-2", evaluation_kind: "failure_prediction", input_context: "cache change", prediction_result: "failure risk", expected_outcome: "failure", actual_outcome: "no failure", evaluation_result: "incorrect", correct: false, confidence: 0.7, evaluated_at: "2026-01-04T00:00:00Z", evidence: ["obs-2"], readOnly: true },
  ],
  accuracy: {
    projectId: "demo", predictions: 2, counted: 2, correct: 1, incorrect: 1, partial: 0, unknown: 0,
    accuracy: 0.5, precision: 1, recall: 0.5, falsePositive: 0, falseNegative: 1,
    falsePositiveRate: 0, falseNegativeRate: 0.5, successRate: 0.5, calibrationError: 0.15,
    calibration: [
      { lower: 0.6, upper: 0.8, count: 1, correct: 0, binAccuracy: 0, binMeanConfidence: 0.7 },
      { lower: 0.8, upper: 1, count: 1, correct: 1, binAccuracy: 1, binMeanConfidence: 0.8 },
    ],
    byKind: {}, filters: {}, readOnly: true,
  },
  failedPredictions: [
    { evaluation_id: "eval-2", project_id: "demo", prediction_id: "pred-2", evaluation_kind: "failure_prediction", input_context: "", prediction_result: "failure risk", expected_outcome: "failure", actual_outcome: "no failure", evaluation_result: "incorrect", correct: false, confidence: 0.7, evaluated_at: "2026-01-04T00:00:00Z", evidence: [], readOnly: true },
  ],
  effectiveness: [
    { effectiveness_id: "effect-1", project_id: "demo", recommendation_id: "rec-1", content: "review parser tests", confidence: 0.8, user_decision: "accepted", actual_result: "tests passed", effectiveness_score: 1, classification: "correct", failure_reason: "", evaluated_at: "2026-01-03T00:00:00Z", readOnly: true },
    { effectiveness_id: "effect-2", project_id: "demo", recommendation_id: "rec-2", content: "drop cache layer", confidence: 0.6, user_decision: "rejected", actual_result: "not tried", effectiveness_score: 0, classification: "rejected", failure_reason: "", evaluated_at: "2026-01-04T00:00:00Z", readOnly: true },
  ],
  effectivenessSummary: { projectId: "demo", total: 2, correct: 1, partiallyUseful: 0, incorrect: 0, rejected: 1, effectivenessRate: 1, meanEffectivenessScore: 0.5, readOnly: true },
  decisionOutcomes: [
    { outcome_id: "dout-1", project_id: "demo", decision_id: "decision-1", decision_type: "architecture", title: "use repository layer", expected_outcome: "cleaner", actual_outcome: "cleaner", status: "SUCCESS", evaluated_at: "2026-01-02T00:00:00Z", readOnly: true },
  ],
  decisionSummary: { projectId: "demo", total: 1, byType: { architecture: { total: 1, successes: 1, successRate: 1 } }, overallSuccessRate: 1, readOnly: true },
  benchmarks: [
    { benchmark_id: "bench-1", dataset_id: "builtin_engineering_prediction", dataset_name: "builtin-engineering_prediction", project_id: "demo", category: "engineering_prediction", model_id: "router", score: 0.9, accuracy: 0.8, determinism_hash: "abc123", created_at: "2026-01-05T00:00:00Z", cases: [], readOnly: true },
  ],
  builtinDatasets: [],
  improvements: [
    { improvement_id: "improve-1", project_id: "demo", evaluation_id: "eval-1", prediction_id: "pred-1", category: "predictions", content: "parser changes correlate with regressions", source: "evaluation_feedback", evidence: ["obs-1"], confidence: 0.7, status: "validated", created_at: "2026-01-05T00:00:00Z", readOnly: true },
    { improvement_id: "req-1", project_id: "demo", evaluation_id: "eval-2", prediction_id: "pred-2", category: "patterns", content: "cache patterns", source: "evaluation_feedback", evidence: [], confidence: 0.5, status: "pending", created_at: "2026-01-06T00:00:00Z", readOnly: true },
  ],
  quality13: { gate: "13.0", status: "WARN", quality: 89, checks: { predictionTraceable: true, evaluationTraceable: true, outcomeTraceable: true, accuracyComputable: true, recommendationEffectivenessComputable: true, benchmarkRunnable: true, knowledgeImprovementAudited: true, noAutoKnowledgeWrite: true, noPermissionBypass: true }, predictionCount: 2, evaluationCount: 2, outcomeCount: 2, accuracyCount: 2, effectivenessCount: 2, benchmarkCount: 1, improvementCount: 2, blockingIssues: [], warnings: ["no_accuracy_data"], readOnly: true },
  readOnly: true,
};

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

function render(overrides: Partial<IntelligencePhase27Response> = {}) {
  return renderIntelligenceDashboard(document, [], [], [], null, null, undefined, { ...phase27, ...overrides });
}

describe("Phase 27 validation dashboard", () => {
  it("renders the validation heading", () => {
    expect(render().textContent).toContain("Engineering Intelligence Validation");
  });

  it("renders evaluation count", () => {
    expect(render().textContent).toContain("2 evaluations");
  });

  it("renders accuracy value", () => {
    expect(render().textContent).toContain("accuracy 0.5");
  });

  it("renders effectiveness rate", () => {
    expect(render().textContent).toContain("effectiveness 1");
  });

  it("renders decision success rate", () => {
    expect(render().textContent).toContain("decision success 1");
  });

  it("renders benchmark run count", () => {
    expect(render().textContent).toContain("1 benchmark runs");
  });

  it("renders improvement count", () => {
    expect(render().textContent).toContain("2 knowledge improvements");
  });

  it("renders accuracy detail line", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Accuracy · 0.5");
    expect(text).toContain("precision 1");
    expect(text).toContain("recall 0.5");
  });

  it("renders false positive and false negative counts", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("False positives 0");
    expect(text).toContain("false negatives 1");
  });

  it("renders calibration error", () => {
    expect(render().textContent).toContain("calibration error 0.15");
  });

  it("renders confidence calibration bins", () => {
    expect(render().textContent).toContain("Confidence calibration");
    expect(render().textContent).toContain("0.8-1: 1");
  });

  it("renders failed predictions", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Failed · pred-2");
    expect(text).toContain("failure_prediction");
  });

  it("renders effectiveness buckets", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("correct 1");
    expect(text).toContain("partially useful 0");
    expect(text).toContain("rejected 1");
  });

  it("renders effectiveness records", () => {
    expect(render().textContent).toContain("Recommendation · correct · score 1");
  });

  it("renders decision outcomes", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Decision outcomes · 1");
    expect(text).toContain("architecture 1");
  });

  it("renders decision records", () => {
    expect(render().textContent).toContain("Decision · architecture · SUCCESS");
  });

  it("renders benchmark runs", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Benchmark · builtin-engineering_prediction");
    expect(text).toContain("score 0.9");
    expect(text).toContain("model router");
  });

  it("renders improvement proposals", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Improvement · validated · predictions");
    expect(text).toContain("Improvement · pending · patterns");
  });

  it("renders quality gate 13", () => {
    expect(render().textContent).toContain("Quality Gate 13 · WARN · 89/100");
  });

  it("empty accuracy shows pending label", () => {
    const root = render({ accuracy: null });
    expect(root.textContent).toContain("accuracy pending");
  });

  it("empty effectiveness shows pending label", () => {
    const root = render({ effectivenessSummary: null, effectiveness: [] });
    expect(root.textContent).toContain("effectiveness pending");
  });

  it("empty decisions shows pending label", () => {
    const root = render({ decisionSummary: null, decisionOutcomes: [] });
    expect(root.textContent).toContain("decision outcomes pending");
  });

  it("no benchmark runs shows placeholder", () => {
    expect(render({ benchmarks: [] }).textContent).toContain("No benchmark runs recorded");
  });

  it("no improvements shows placeholder", () => {
    expect(render({ improvements: [] }).textContent).toContain("No knowledge improvement proposals");
  });

  it("no validation records shows placeholder", () => {
    const root = render({ evaluations: [], accuracy: null, failedPredictions: [] });
    expect(root.textContent).toContain("No validation records yet");
  });

  it("no quality13 shows nothing", () => {
    const root = render({ quality13: null });
    expect(root.textContent).not.toContain("Quality Gate 13");
  });

  it("marks low accuracy with warning tone", () => {
    const root = render();
    expect(root.querySelector(".warning")).not.toBeNull();
  });

  it("keeps dataset role for accessibility", () => {
    expect(render().dataset.role).toBe("engineering-intelligence-dashboard");
  });
});

describe("Phase 27 dashboard accuracy details", () => {
  it("renders calibration error line", () => {
    expect(render().textContent).toContain("calibration error 0.15");
  });

  it("renders only populated calibration bins", () => {
    const root = render();
    expect(root.textContent).toContain("0.6-0.8: 0");
    expect(root.textContent).not.toContain("0-0.2:");
  });

  it("does not render calibration when no populated bins", () => {
    const accuracy = { ...phase27.accuracy!, calibration: [] };
    expect(render({ accuracy }).textContent).not.toContain("Confidence calibration");
  });

  it("renders accuracy pending when accuracy is null", () => {
    expect(render({ accuracy: null }).textContent).toContain("accuracy pending");
  });

  it("renders multiple failed predictions", () => {
    const failedPredictions = [
      phase27.failedPredictions[0],
      { ...phase27.failedPredictions[0], prediction_id: "pred-3", evaluation_kind: "test_prediction" },
    ];
    const root = render({ failedPredictions });
    expect(root.textContent).toContain("Failed · pred-2");
    expect(root.textContent).toContain("Failed · pred-3");
  });

  it("limits failed predictions to three", () => {
    const failedPredictions = Array.from({ length: 6 }, (_, index) => ({ ...phase27.failedPredictions[0], prediction_id: `pred-${index}` }));
    const text = render({ failedPredictions }).textContent ?? "";
    expect(text.match(/Failed · pred-/g)?.length ?? 0).toBe(3);
  });

  it("flags failed predictions with warning tone", () => {
    expect(render().querySelectorAll(".warning").length).toBeGreaterThan(0);
  });

  it("accuracy zero renders warning tone", () => {
    const accuracy = { ...phase27.accuracy!, accuracy: 0, correct: 0 };
    const root = render({ accuracy });
    expect(root.querySelector(".warning")).not.toBeNull();
  });

  it("shows false positive rate when non-zero", () => {
    const accuracy = { ...phase27.accuracy!, falsePositive: 2, falsePositiveRate: 0.66 };
    const text = render({ accuracy }).textContent ?? "";
    expect(text).toContain("False positives 2");
  });
});

describe("Phase 27 dashboard benchmark and improvement details", () => {
  it("renders multiple benchmark runs", () => {
    const benchmarks = [phase27.benchmarks[0], { ...phase27.benchmarks[0], benchmark_id: "bench-2", dataset_name: "builtin-context_understanding" }];
    const text = render({ benchmarks }).textContent ?? "";
    expect(text).toContain("builtin-engineering_prediction");
    expect(text).toContain("builtin-context_understanding");
  });

  it("renders benchmark accuracy", () => {
    expect(render().textContent).toContain("accuracy 0.8");
  });

  it("limits benchmark runs to three", () => {
    const benchmarks = Array.from({ length: 5 }, (_, index) => ({ ...phase27.benchmarks[0], benchmark_id: `bench-${index}` }));
    const text = render({ benchmarks }).textContent ?? "";
    expect(text.match(/Benchmark · /g)?.length ?? 0).toBe(3);
  });

  it("renders all improvement statuses", () => {
    const text = render().textContent ?? "";
    expect(text).toContain("Improvement · validated");
    expect(text).toContain("Improvement · pending");
  });

  it("marks pending improvements with recommendation tone", () => {
    expect(render().querySelectorAll(".recommendation").length).toBeGreaterThan(0);
  });

  it("limits improvements to four", () => {
    const improvements = Array.from({ length: 6 }, (_, index) => ({ ...phase27.improvements[0], improvement_id: `improve-${index}` }));
    const text = render({ improvements }).textContent ?? "";
    expect(text.match(/Improvement · /g)?.length ?? 0).toBe(4);
  });

  it("renders improvement confidence", () => {
    expect(render().textContent).toContain("confidence 0.7");
  });
});

describe("Phase 27 dashboard decision and effectiveness details", () => {
  it("renders decision type rates", () => {
    expect(render().textContent).toContain("architecture 1");
  });

  it("renders multiple decision types", () => {
    const decisionSummary = {
      projectId: "demo", total: 2,
      byType: { architecture: { total: 1, successes: 1, successRate: 1 }, debugging: { total: 1, successes: 0, successRate: 0 } },
      overallSuccessRate: 0.5, readOnly: true as const,
    };
    const text = render({ decisionSummary }).textContent ?? "";
    expect(text).toContain("debugging 0");
  });

  it("renders partial decision status", () => {
    const decisionOutcomes = [{ ...phase27.decisionOutcomes[0], status: "PARTIAL", decision_id: "decision-2" }];
    expect(render({ decisionOutcomes }).textContent).toContain("PARTIAL");
  });

  it("renders effectiveness record score", () => {
    expect(render().textContent).toContain("score 1");
  });

  it("renders effectiveness records with content", () => {
    expect(render().textContent).toContain("review parser tests");
  });

  it("flags incorrect effectiveness with warning tone", () => {
    const effectiveness = [{ ...phase27.effectiveness[0], effectiveness_id: "e-3", classification: "incorrect" }];
    const root = render({ effectiveness });
    expect(root.querySelector(".warning")).not.toBeNull();
  });
});

describe("Phase 27 dashboard read-only enforcement", () => {
  it("has no interactive controls", () => {
    expect(render().querySelectorAll("button,input,select,textarea,a")).toHaveLength(0);
  });

  it("never contains execute text", () => {
    expect((render().textContent ?? "").toLowerCase()).not.toContain("execute");
  });

  it("never contains approve text", () => {
    expect((render().textContent ?? "").toLowerCase()).not.toContain("approve");
  });

  it("never contains auto-fix text", () => {
    expect((render().textContent ?? "").toLowerCase()).not.toContain("auto-fix");
  });

  it("never contains apply button", () => {
    expect((render().textContent ?? "").toLowerCase()).not.toContain("apply");
  });

  it("never contains auto-learn text", () => {
    expect((render().textContent ?? "").toLowerCase()).not.toContain("auto-learn");
  });

  it("renders with all optional data missing without crashing", () => {
    const root = render({ evaluations: [], accuracy: null, failedPredictions: [], effectiveness: [], effectivenessSummary: null, decisionOutcomes: [], decisionSummary: null, benchmarks: [], improvements: [], quality13: null });
    expect(root.querySelectorAll("button")).toHaveLength(0);
  });

  it("fails no further than one element per empty section", () => {
    const root = render({ benchmarks: [], improvements: [] });
    expect(root.textContent).toContain("No benchmark runs recorded");
    expect(root.textContent).toContain("No knowledge improvement proposals");
  });
});

describe("Phase 27 BridgeClient read methods", () => {
  it.each([
    ["intelligenceValidation", "/intelligence/validation?project=demo"],
    ["intelligenceAccuracy", "/intelligence/accuracy?project=demo"],
    ["intelligenceEffectiveness", "/intelligence/effectiveness?project=demo"],
    ["intelligenceDecisionOutcomes", "/intelligence/decision-outcomes?project=demo"],
    ["intelligenceBenchmarks", "/intelligence/benchmarks?project=demo"],
    ["intelligenceKnowledgeImprovements", "/intelligence/knowledge/improvements?project=demo"],
  ] as const)("uses GET for %s", async (method, path) => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain(path);
      expect(init?.method ?? "GET").toBe("GET");
      return response({ project: "demo", readOnly: true });
    });
    const client = new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    await (client[method] as (project: string) => Promise<unknown>)("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("encodes project in accuracy path", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/intelligence/accuracy?project=my+project");
      return response({ readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceAccuracy("my project");
  });

  it("passes agent and model filters to accuracy", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("agent_id=agent-1");
      expect(String(input)).toContain("model_id=router");
      return response({ readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceAccuracy("demo", { agentId: "agent-1", modelId: "router" });
  });

  it("passes kind filter to accuracy", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("kind=failure_prediction");
      return response({ readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceAccuracy("demo", { kind: "failure_prediction" });
  });

  it("passes status filter to knowledge improvements", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("status=validated");
      return response({ project: "demo", improvements: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceKnowledgeImprovements("demo", "validated");
  });

  it("does not send status when omitted", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/intelligence/knowledge/improvements?project=demo");
      expect(String(input)).not.toContain("status=");
      return response({ project: "demo", improvements: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceKnowledgeImprovements("demo");
  });
});

describe("Phase 27 BridgeClient staging helpers", () => {
  it("stages evaluation with POST", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/intelligence/evaluation");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.project_id).toBe("demo");
      expect(body.prediction_id).toBe("pred-1");
      return response({ requestId: "req-1", status: "pending", permissionLevel: "LEVEL_1" });
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).stageEvaluation({
      project_id: "demo", prediction_id: "pred-1", evaluation_kind: "prediction",
      prediction_result: "claim", expected_outcome: "expected", actual_outcome: "actual",
      evaluation_result: "correct",
    });
    expect(result.status).toBe("pending");
  });

  it("stages benchmark run with POST and dataset id", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/intelligence/benchmark/run");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.dataset_id).toBe("builtin_engineering_prediction");
      return response({ requestId: "req-2", status: "pending" });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).stageBenchmarkRun({ project_id: "demo", dataset_id: "builtin_engineering_prediction" });
  });

  it("stages knowledge improvement with POST", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/intelligence/knowledge/improvements/propose");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.category).toBe("patterns");
      expect(body.evaluation_id).toBe("eval-1");
      return response({ requestId: "req-3", status: "pending" });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).stageKnowledgeImprovement({
      project_id: "demo", evaluation_id: "eval-1", prediction_id: "pred-1",
      category: "patterns", content: "pattern found",
    });
  });

  it("staging evaluation never executes", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ requestId: "req-1", status: "pending" }));
    const client = new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.stageEvaluation({ project_id: "demo", prediction_id: "pred-1", evaluation_kind: "prediction", prediction_result: "claim", expected_outcome: "expected", actual_outcome: "actual", evaluation_result: "correct" });
    const call = fetchImpl.mock.calls[0][1] as RequestInit;
    expect(call.method).toBe("POST");
    expect(JSON.parse(String(call.body))).not.toHaveProperty("autoApprove");
  });

  it("staging benchmark run never executes", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ requestId: "req-2", status: "pending" }));
    const client = new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.stageBenchmarkRun({ project_id: "demo", dataset_id: "builtin_engineering_prediction" });
    const body = JSON.parse(String((fetchImpl.mock.calls[0][1] as RequestInit).body));
    expect(body).not.toHaveProperty("execute");
    expect(body).not.toHaveProperty("apply");
  });
});

describe("Phase 27 client has no mutation shortcuts", () => {
  it("has no executePrediction helper", () => {
    const client = new BridgeClient();
    expect("executePrediction" in client).toBe(false);
  });

  it("has no applyRecommendation helper", () => {
    const client = new BridgeClient();
    expect("applyRecommendation" in client).toBe(false);
  });

  it("has no autoFix helper", () => {
    const client = new BridgeClient();
    expect("autoFix" in client).toBe(false);
  });

  it("has no autoApprove helper", () => {
    const client = new BridgeClient();
    expect("autoApprove" in client).toBe(false);
  });

  it("has no approveEvaluation helper", () => {
    const client = new BridgeClient();
    expect("approveEvaluation" in client).toBe(false);
  });

  it("has no runBenchmarkWithoutApproval helper", () => {
    const client = new BridgeClient();
    expect("runBenchmarkWithoutApproval" in client).toBe(false);
  });

  it("has no writeKnowledge helper", () => {
    const client = new BridgeClient();
    expect("writeKnowledge" in client).toBe(false);
  });

  it("has no learnFromEvaluation helper", () => {
    const client = new BridgeClient();
    expect("learnFromEvaluation" in client).toBe(false);
  });
});

describe("Phase 27 extension store state", () => {
  function freshStore() {
    return new ExtensionStore();
  }

  it("initializes validation fields empty", () => {
    const state = freshStore().getState();
    expect(state.intelligenceValidation).toBeNull();
    expect(state.intelligenceAccuracy).toBeNull();
    expect(state.intelligenceEffectiveness).toEqual([]);
    expect(state.intelligenceEffectivenessSummary).toBeNull();
    expect(state.intelligenceDecisionOutcomes).toEqual([]);
    expect(state.intelligenceDecisionSummary).toBeNull();
    expect(state.intelligenceBenchmarks).toEqual([]);
    expect(state.intelligenceImprovements).toEqual([]);
  });

  it("updates validation snapshot", async () => {
    const store = freshStore();
    await store.update({ intelligenceValidation: phase27 });
    expect(store.getState().intelligenceValidation?.project).toBe("demo");
  });

  it("update derives accuracy from snapshot", async () => {
    const store = freshStore();
    await store.update({ intelligenceAccuracy: phase27.accuracy });
    expect(store.getState().intelligenceAccuracy?.accuracy).toBe(0.5);
  });

  it("update derives effectiveness records", async () => {
    const store = freshStore();
    await store.update({ intelligenceEffectiveness: phase27.effectiveness });
    expect(store.getState().intelligenceEffectiveness).toHaveLength(2);
  });

  it("update derives benchmarks", async () => {
    const store = freshStore();
    await store.update({ intelligenceBenchmarks: phase27.benchmarks });
    expect(store.getState().intelligenceBenchmarks[0].score).toBe(0.9);
  });

  it("update derives improvements", async () => {
    const store = freshStore();
    await store.update({ intelligenceImprovements: phase27.improvements });
    expect(store.getState().intelligenceImprovements).toHaveLength(2);
  });

  it("clearing validation fields restores empty state", async () => {
    const store = freshStore();
    await store.update({ intelligenceValidation: phase27, intelligenceAccuracy: phase27.accuracy, intelligenceEffectiveness: phase27.effectiveness, intelligenceEffectivenessSummary: phase27.effectivenessSummary, intelligenceDecisionOutcomes: phase27.decisionOutcomes, intelligenceDecisionSummary: phase27.decisionSummary, intelligenceBenchmarks: phase27.benchmarks, intelligenceImprovements: phase27.improvements });
    await store.update({ intelligenceValidation: null, intelligenceAccuracy: null, intelligenceEffectiveness: [], intelligenceEffectivenessSummary: null, intelligenceDecisionOutcomes: [], intelligenceDecisionSummary: null, intelligenceBenchmarks: [], intelligenceImprovements: [] });
    const state = store.getState();
    expect(state.intelligenceValidation).toBeNull();
    expect(state.intelligenceAccuracy).toBeNull();
    expect(state.intelligenceEffectiveness).toEqual([]);
    expect(state.intelligenceImprovements).toEqual([]);
  });

  it("store remains usable after clearing validation", async () => {
    const store = freshStore();
    await store.update({ intelligenceValidation: null });
    expect(store.getState().intelligenceValidation).toBeNull();
    expect(store.getState().intelligenceAccuracy).toBeNull();
  });
});

describe("Phase 27 readonly enforcement in panel wiring", () => {
  it("renders validation section without controls through the dashboard", () => {
    const root = renderIntelligenceDashboard(document, [], [], [], null, null, undefined, phase27);
    expect(root.querySelector("button")).toBeNull();
    expect(root.querySelector("input")).toBeNull();
    expect(root.querySelector("a")).toBeNull();
  });

  it("combines phase26 and phase27 sections safely", () => {
    const root = renderIntelligenceDashboard(document, [], [], [], null, null, undefined, phase27);
    expect(root.textContent).toContain("Engineering Intelligence Validation");
  });

  it("phase27 output is text only", () => {
    const root = render();
    for (const element of Array.from(root.querySelectorAll("*"))) {
      expect(element.tagName.toLowerCase()).not.toBe("button");
      expect(element.tagName.toLowerCase()).not.toBe("input");
    }
  });
});

describe("Phase 27 client URL encoding edge cases", () => {
  it("encodes spaces in knowledge improvement project", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/intelligence/knowledge/improvements?project=my+project");
      return response({ project: "my project", improvements: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceKnowledgeImprovements("my project");
  });

  it("encodes status filter value", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("status=validated");
      return response({ project: "demo", improvements: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceKnowledgeImprovements("demo", "validated");
  });

  it("intelligenceValidation uses exact project param", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/intelligence/validation?project=demo");
      return response(phase27);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceValidation("demo");
  });

  it("staging evaluation forwards evidence list", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.evidence).toEqual(["obs-1", "obs-2"]);
      expect(body.confidence).toBe(0.8);
      return response({ requestId: "req-9", status: "pending" });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).stageEvaluation({
      project_id: "demo", prediction_id: "pred-1", evaluation_kind: "risk_assessment",
      prediction_result: "claim", expected_outcome: "expected", actual_outcome: "actual",
      evaluation_result: "correct", confidence: 0.8, evidence: ["obs-1", "obs-2"],
    });
  });

  it("staging benchmark forwards model id", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.model_id).toBe("router-v2");
      return response({ requestId: "req-10", status: "pending" });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).stageBenchmarkRun({ project_id: "demo", dataset_id: "builtin_engineering_prediction", model_id: "router-v2" });
  });

  it("staging improvement forwards confidence and source", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.confidence).toBe(0.6);
      expect(body.source).toBe("evaluation_feedback");
      return response({ requestId: "req-11", status: "pending" });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).stageKnowledgeImprovement({
      project_id: "demo", evaluation_id: "eval-1", prediction_id: "pred-1",
      category: "trends", content: "build failures increasing", confidence: 0.6,
      source: "evaluation_feedback",
    });
  });

  it("reads accuracy by kind only", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("kind=test_prediction");
      expect(String(input)).not.toContain("agent_id=");
      return response({ readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).intelligenceAccuracy("demo", { kind: "test_prediction" });
  });
});
