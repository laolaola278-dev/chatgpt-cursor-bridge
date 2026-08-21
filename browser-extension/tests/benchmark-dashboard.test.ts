import { describe, expect, it } from "vitest";

import { renderBenchmarkDashboard } from "../src/benchmark/benchmark-dashboard";
import type { BenchmarkRecord, BenchmarkResultRecord } from "../src/benchmark/models";

const benchmark: BenchmarkRecord = {
  id: "bench_1",
  project: "demo",
  repository: "local/demo",
  createdAt: "2026-01-01T00:00:00Z",
  status: "COMPLETED",
  readOnly: true,
};

const result: BenchmarkResultRecord = {
  id: "br_1",
  runId: "run_1",
  success: true,
  qualityScore: 88,
  rollbackTriggered: false,
  verificationResult: { status: "PASS" },
  humanRating: 90,
  readOnly: true,
};

const failedResult: BenchmarkResultRecord = { ...result, id: "br_2", success: false, qualityScore: 40, rollbackTriggered: true };

function render(overrides: Partial<Parameters<typeof renderBenchmarkDashboard>[1]> = {}) {
  return renderBenchmarkDashboard(document, {
    benchmarks: [benchmark],
    results: [result, failedResult],
    failurePatterns: [{ category: "test_failure", severity: "high", occurrences: 2 }],
    capabilities: [{ agentId: "ag_coder", successRate: 80, averageQuality: 85, rollbackRate: 10 }],
    ...overrides,
  });
}

describe("benchmark dashboard", () => {
  it.each(Array.from({ length: 20 }, (_, index) => index))("renders read-only benchmark case %i", () => {
    const root = render();
    expect(root.dataset.role).toBe("benchmark-dashboard");
    expect(root.textContent).toContain("READ ONLY");
    expect(root.textContent).toContain("Benchmark Dashboard");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders rates case %i", () => {
    const root = render();
    expect(root.textContent).toContain("success 50%");
    expect(root.textContent).toContain("quality 64/100");
    expect(root.textContent).toContain("rollback 50%");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders agent performance case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Agent Performance");
    expect(root.textContent).toContain("ag_coder");
    expect(root.textContent).toContain("success 80%");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders failure patterns case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Failure Patterns");
    expect(root.textContent).toContain("test_failure");
    expect(root.textContent).toContain("2 occurrence(s)");
  });

  it("renders an empty read-only state", () => {
    const root = renderBenchmarkDashboard(document, { benchmarks: [], results: [], failurePatterns: [], capabilities: [] });
    expect(root.textContent).toContain("No benchmark data recorded yet");
    expect(root.querySelector("button")).toBeNull();
  });
});
