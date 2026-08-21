import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { BridgeRequestError } from "../src/bridge/types";
import { renderIntelligenceDashboard } from "../src/context/intelligence-dashboard";
import type { Phase30Snapshot } from "../src/context/types";
import { ExtensionStore, createInitialState } from "../src/state/store";

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

function snapshotFixture(overrides: Partial<Phase30Snapshot> = {}): Phase30Snapshot {
  return {
    source: "context/dev/intelligence",
    project: "demo",
    suggested: {
      source: "context/dev/intelligence",
      project: "demo",
      agent: "ASSISTANT",
      query: "auth login",
      items: [
        {
          id: "file:src/auth/service.py",
          kind: "file",
          path: "src/auth/service.py",
          name: "service.py",
          score: 0.92,
          reason: "query keyword matched in path",
          source: "file",
          size: 1200,
          included: true,
          exclusion: "",
          truncated: false,
          securityFiltered: true,
        },
        {
          id: "symbol:src/auth/service.py:authenticate",
          kind: "symbol",
          path: "src/auth/service.py",
          name: "authenticate",
          score: 0.71,
          reason: "query keyword matched symbol or file name",
          source: "symbol",
          size: 400,
          included: false,
          exclusion: "score",
          truncated: false,
          securityFiltered: true,
        },
      ],
      budget: [
        { bucket: "code", used: 1200, limit: 40960, remaining: 39760, items: 1 },
        { bucket: "tests", used: 0, limit: 12288, remaining: 12288, items: 0 },
        { bucket: "git", used: 0, limit: 8192, remaining: 8192, items: 0 },
        { bucket: "metadata", used: 0, limit: 4096, remaining: 4096, items: 0 },
      ],
      dedup: { totalCandidates: 3, unique: 2, dropped: 1 },
      truncated: true,
      securityFiltering: true,
      readOnly: true,
    },
    relationships: null,
    errorBundle: {
      source: "context/dev/intelligence",
      project: "demo",
      error: "ValueError: bad credentials",
      kind: "python_exception",
      sourceLocation: { path: "src/auth/service.py", line: 3 },
      relatedFiles: ["src/auth/service.py", "src/auth/controller.py"],
      relatedSymbols: [],
      dependencies: [],
      recentDiff: ["src/auth/service.py"],
      relevantTests: ["tests/test_auth.py"],
      sanitized: true,
      absolutePathsRemoved: true,
      secretsRedacted: true,
      readOnly: true,
    },
    testFailure: {
      source: "context/dev/intelligence",
      project: "demo",
      test: "test_login_success",
      failure: "assert false is True",
      expected: "True",
      actual: "False",
      testFile: "tests/test_auth.py",
      relatedSource: ["src/auth/service.py"],
      relatedSymbols: [],
      suggestedInvestigation: ["Open the failing test and confirm the assertion.", "Generate a Patch Proposal via ApprovalStore."],
      patchProposalOnly: true,
      readOnly: true,
    },
    gitAnalysis: {
      source: "context/dev/intelligence",
      project: "demo",
      changeSummary: ["2 file(s) changed, 10 added / 2 removed line(s)."],
      changedFiles: [
        { path: "src/auth/service.py", added: 10, removed: 2 },
        { path: "src/app.py", added: 1, removed: 0 },
      ],
      changedSymbols: [{ name: "authenticate", type: "function", file: "src/auth/service.py", line: 1 }],
      affectedTests: ["tests/test_auth.py"],
      affectedDependencies: [],
      riskIndicators: [{ severity: "high", label: "dangerous API usage", matches: 2 }],
      reviewPoints: ["Review 2 changed file(s).", "High-risk pattern 'dangerous API usage' requires explicit human review."],
      stats: { files: 2, added: 11, removed: 2, symbols: 1, tests: 1 },
      readOnly: true,
      noGitMutation: true,
    },
    review: {
      source: "context/dev/intelligence",
      project: "demo",
      target: "src/app.py",
      summary: "2 finding(s) for src/app.py.",
      findings: [
        {
          id: "f1",
          severity: "Critical",
          category: "security",
          location: "src/app.py:2",
          title: "Shell execution via shell=True",
          explanation: "shell=True allows shell metacharacter injection.",
          recommendation: "Use an argument list with shell=False.",
        },
        {
          id: "f2",
          severity: "Medium",
          category: "error_handling",
          location: "src/app.py:4",
          title: "Bare except swallows errors",
          explanation: "A bare except hides the real failure.",
          recommendation: "Catch specific exception types.",
        },
      ],
      patchProposalOnly: true,
      readOnly: true,
    },
    injection: {
      source: "context/dev/intelligence",
      project: "demo",
      trusted: "system",
      untrusted: ["project_content"],
      signals: [{ pattern: "instruction override", severity: "high", snippet: "ignore previous instructions" }],
      verdict: "untrusted_content_detected",
      readOnly: true,
    },
    budget: [
      { bucket: "code", used: 1200, limit: 40960, remaining: 39760, items: 1 },
      { bucket: "tests", used: 0, limit: 12288, remaining: 12288, items: 0 },
      { bucket: "git", used: 0, limit: 8192, remaining: 8192, items: 0 },
      { bucket: "metadata", used: 0, limit: 4096, remaining: 4096, items: 0 },
    ],
    proposals: [
      {
        id: "proposal-1",
        project: "demo",
        agent: "ASSISTANT",
        targetFile: "src/auth/service.py",
        targetSymbol: "authenticate",
        proposedChange: "add rate limiting",
        reason: "prevent brute force",
        expectedImpact: "slower logins",
        risk: "medium",
        status: "proposed",
        applied: false,
        approvalRequestId: "req_1",
        createdAt: "2026-08-19T00:00:00Z",
      },
    ],
    readOnly: true,
    securityFiltering: true,
    ...overrides,
  };
}

function render(snapshot: Phase30Snapshot | null) {
  return renderIntelligenceDashboard(document, snapshot);
}

describe("Phase 30 dashboard shell", () => {
  it("renders the heading", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Context Intelligence");
  });

  it("renders READ ONLY badge", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("READ ONLY");
  });

  it("renders empty state without snapshot", () => {
    const root = render(null);
    expect(root.textContent).toContain("No context intelligence loaded");
  });

  it("renders all sections", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Suggested Context");
    expect(root.textContent).toContain("Error Analysis");
    expect(root.textContent).toContain("Test Failure Intelligence");
    expect(root.textContent).toContain("Git Diff Intelligence");
    expect(root.textContent).toContain("Code Review");
    expect(root.textContent).toContain("Prompt Injection Protection");
    expect(root.textContent).toContain("Context Budget 2.0");
    expect(root.textContent).toContain("Patch Proposals");
  });

  it("has no interactive execute/approve/apply controls", () => {
    const root = render(snapshotFixture());
    expect(root.querySelectorAll("button").length).toBe(0);
    expect(root.querySelectorAll('input[type="submit"]').length).toBe(0);
    expect(root.textContent).toContain("Read-only. No execute, approve, apply, fix, auto-learn or auto-govern.");
  });
});

describe("Phase 30 suggested context", () => {
  it("renders the query", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("auth login");
  });

  it("renders ranked items with scores", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("src/auth/service.py");
    expect(root.textContent).toContain("0.92");
    expect(root.textContent).toContain("0.71");
  });

  it("renders the explanation reason", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("query keyword matched in path");
    expect(root.textContent).toContain("query keyword matched symbol or file name");
  });

  it("shows no-data message when suggested missing", () => {
    const root = render(snapshotFixture({ suggested: null }));
    expect(root.textContent).toContain("No suggestion data in this snapshot.");
  });
});

describe("Phase 30 error analysis", () => {
  it("renders the error message", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("ValueError: bad credentials");
  });

  it("renders kind and sanitization flags", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("python_exception");
    expect(root.textContent).toContain("sanitized=true");
    expect(root.textContent).toContain("absPathsRemoved=true");
  });

  it("renders related files", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("src/auth/service.py");
    expect(root.textContent).toContain("src/auth/controller.py");
  });

  it("shows no-data message when error bundle missing", () => {
    const root = render(snapshotFixture({ errorBundle: null }));
    expect(root.textContent).toContain("No error analysis in this snapshot.");
  });
});

describe("Phase 30 test failure intelligence", () => {
  it("renders the failing test", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("test_login_success");
  });

  it("renders the test file", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("tests/test_auth.py");
  });

  it("renders suggested investigation steps", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Open the failing test");
    expect(root.textContent).toContain("Patch Proposal");
  });

  it("renders the proposal-only boundary note", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Changes only via Patch Proposal → Approval.");
  });

  it("shows no-data message when test failure missing", () => {
    const root = render(snapshotFixture({ testFailure: null }));
    expect(root.textContent).toContain("No test-failure analysis in this snapshot.");
  });
});

describe("Phase 30 git diff intelligence", () => {
  it("renders the change summary", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("2 file(s) changed");
  });

  it("renders risk indicators with severity tone", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("dangerous API usage");
    expect(root.textContent).toContain("high");
  });

  it("renders review points", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Review 2 changed file(s)");
  });

  it("shows no-data message when git analysis missing", () => {
    const root = render(snapshotFixture({ gitAnalysis: null }));
    expect(root.textContent).toContain("No git diff analysis in this snapshot.");
  });
});

describe("Phase 30 code review", () => {
  it("renders the summary", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("2 finding(s)");
  });

  it("renders findings with severity", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("Critical");
    expect(root.textContent).toContain("Shell execution via shell=True");
    expect(root.textContent).toContain("src/app.py:2");
    expect(root.textContent).toContain("Medium");
    expect(root.textContent).toContain("Bare except swallows errors");
  });

  it("shows no-data message when review missing", () => {
    const root = render(snapshotFixture({ review: null }));
    expect(root.textContent).toContain("No code review in this snapshot.");
  });
});

describe("Phase 30 prompt injection protection", () => {
  it("renders the verdict", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("untrusted_content_detected");
  });

  it("labels project content as untrusted data", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("never instructions");
  });

  it("renders detected signals", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("instruction override");
    expect(root.textContent).toContain("ignore previous instructions");
  });

  it("renders clean verdict tone", () => {
    const root = render(snapshotFixture({ injection: { ...snapshotFixture().injection!, verdict: "clean", signals: [] } }));
    expect(root.textContent).toContain("clean");
  });
});

describe("Phase 30 context budget", () => {
  it("renders each bucket with usage", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("code: 1200 / 40960 B");
    expect(root.textContent).toContain("tests: 0 / 12288 B");
    expect(root.textContent).toContain("git: 0 / 8192 B");
    expect(root.textContent).toContain("metadata: 0 / 4096 B");
  });

  it("renders remaining bytes", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("39760 B left");
  });
});

describe("Phase 30 patch proposals", () => {
  it("renders approved proposal records", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("src/auth/service.py");
    expect(root.textContent).toContain("prevent brute force");
    expect(root.textContent).toContain("medium");
  });

  it("renders record-only boundary note", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("never modified here");
  });

  it("shows empty proposals message", () => {
    const root = render(snapshotFixture({ proposals: [] }));
    expect(root.textContent).toContain("No approved patch proposals yet.");
  });
});

describe("Phase 30 store state", () => {
  it("initialises phase30 intelligence to null", () => {
    const state = createInitialState();
    expect(state.phase30Intelligence).toBeNull();
  });

  it("updates phase30 intelligence", async () => {
    const store = new ExtensionStore();
    await store.update({ phase30Intelligence: snapshotFixture() });
    expect(store.getState().phase30Intelligence?.project).toBe("demo");
  });

  it("resets phase30 intelligence via update", async () => {
    const store = new ExtensionStore();
    await store.update({ phase30Intelligence: snapshotFixture() });
    await store.update({ phase30Intelligence: null });
    expect(store.getState().phase30Intelligence).toBeNull();
  });
});

describe("Phase 30 bridge client (GET only)", () => {
  it("fetches suggested context", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/suggest?project=demo&query=auth");
      return response(snapshotFixture().suggested);
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceSuggest("demo", "auth");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches relationships", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/relationships?project=demo&file=src%2Fauth%2Fservice.py");
      return response({ imports: [], importers: [], readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceRelationships("demo", "src/auth/service.py");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches error bundle", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/error?project=demo&error=boom");
      return response(snapshotFixture().errorBundle);
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceError("demo", "boom");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches test failure context", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/test-failure?project=demo&test=test_login_success");
      return response(snapshotFixture().testFailure);
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceTestFailure("demo", "test_login_success");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches git diff intelligence", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/git?project=demo");
      return response(snapshotFixture().gitAnalysis);
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceGit("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches code review", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/review?project=demo&file=src%2Fapp.py");
      return response(snapshotFixture().review);
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceReview("demo", { file: "src/app.py" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches injection report", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/injection?project=demo&text=ignore&source=project_content");
      return response(snapshotFixture().injection);
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceInjection("demo", "ignore");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches budget report", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/budget?project=demo");
      return response({ budget: [], dedup: {}, truncated: false, globalLimit: 65536, readOnly: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceBudget("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches the phase30 snapshot", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/intelligence/snapshot?project=demo");
      return response(snapshotFixture());
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceSnapshot("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("never exposes file content in suggestion items", () => {
    const items = snapshotFixture().suggested?.items ?? [];
    for (const item of items) {
      expect("content" in item).toBe(false);
    }
  });
});

describe("Phase 30 patch proposal client (approval-gated POST)", () => {
  it("stages a patch proposal via POST", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain("/context/dev/intelligence/patch-proposal");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body));
      expect(body.project).toBe("demo");
      expect(body.target_file).toBe("src/auth/service.py");
      return response({ requestId: "req_1", status: "pending", preview: "RECORD Patch Proposal" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.stagePatchProposal({
      project: "demo",
      target_file: "src/auth/service.py",
      proposed_change: "add rate limiting",
      reason: "prevent brute force",
      expected_impact: "slower logins",
      risk: "medium",
    });
    expect(result.requestId).toBe("req_1");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe("Phase 30 suggested context ranking data", () => {
  it("sorts suggested items by score descending", () => {
    const items = snapshotFixture().suggested!.items;
    expect(items[0].score).toBeGreaterThanOrEqual(items[1].score);
  });

  it("exposes item size", () => {
    for (const item of snapshotFixture().suggested!.items) {
      expect(item.size).toBeGreaterThan(0);
    }
  });

  it("exposes item source", () => {
    expect(snapshotFixture().suggested!.items[0].source).toBe("file");
    expect(snapshotFixture().suggested!.items[1].source).toBe("symbol");
  });

  it("exposes the exclusion reason when not included", () => {
    expect(snapshotFixture().suggested!.items[1].exclusion).toBe("score");
  });

  it("exposes the per-item truncated flag", () => {
    for (const item of snapshotFixture().suggested!.items) {
      expect(typeof item.truncated).toBe("boolean");
    }
  });

  it("exposes the per-item security-filtered flag", () => {
    for (const item of snapshotFixture().suggested!.items) {
      expect(item.securityFiltered).toBe(true);
    }
  });

  it("reports dedup totals", () => {
    const dedup = snapshotFixture().suggested!.dedup;
    expect(dedup.totalCandidates).toBe(3);
    expect(dedup.unique).toBe(2);
    expect(dedup.dropped).toBe(1);
  });

  it("renders included items with a checkmark", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("✓");
  });

  it("renders excluded items without a checkmark", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("·");
  });

  it("caps rendered items at eight", () => {
    const items = snapshotFixture().suggested!.items;
    const many = Array.from({ length: 10 }, (_, index) => ({
      ...items[0],
      id: `item-${index}`,
      path: `file-${index}.py`,
      score: 1 - index * 0.05,
    }));
    const snapshot = snapshotFixture({ suggested: { ...snapshotFixture().suggested!, items: many } });
    const root = render(snapshot);
    const matches = root.textContent!.match(/score \d+\.\d+/g) ?? [];
    expect(matches.length).toBe(8);
  });

  it("formats scores with two decimals", () => {
    const root = render(snapshotFixture());
    expect(root.textContent).toContain("score 0.92");
    expect(root.textContent).toContain("score 0.71");
  });

  it("falls back to a (no query) label", () => {
    const suggested = snapshotFixture().suggested!;
    const snapshot = snapshotFixture({ suggested: { ...suggested, query: "" } });
    const root = render(snapshot);
    expect(root.textContent).toContain("(no query)");
  });
});

describe("Phase 30 error context data", () => {
  it("exposes the source location path", () => {
    expect(snapshotFixture().errorBundle!.sourceLocation?.path).toBe("src/auth/service.py");
  });

  it("exposes the source location line", () => {
    expect(snapshotFixture().errorBundle!.sourceLocation?.line).toBe(3);
  });

  it("exposes related symbols", () => {
    expect(Array.isArray(snapshotFixture().errorBundle!.relatedSymbols)).toBe(true);
  });

  it("exposes dependencies", () => {
    expect(Array.isArray(snapshotFixture().errorBundle!.dependencies)).toBe(true);
  });

  it("exposes recent diff files", () => {
    expect(snapshotFixture().errorBundle!.recentDiff).toContain("src/auth/service.py");
  });

  it("exposes relevant tests", () => {
    expect(snapshotFixture().errorBundle!.relevantTests).toContain("tests/test_auth.py");
  });

  it("flags secrets redaction", () => {
    expect(snapshotFixture().errorBundle!.secretsRedacted).toBe(true);
  });

  it("is read-only", () => {
    expect(snapshotFixture().errorBundle!.readOnly).toBe(true);
  });

  it("truncates long error messages in the UI", () => {
    const long = "x".repeat(500);
    const errorBundle = snapshotFixture().errorBundle!;
    const snapshot = snapshotFixture({ errorBundle: { ...errorBundle, error: long } });
    const root = render(snapshot);
    expect(root.textContent).toContain(long.slice(0, 200));
    expect(root.textContent).not.toContain(long.slice(200));
  });

  it("caps related files at five in the UI", () => {
    const errorBundle = snapshotFixture().errorBundle!;
    const files = Array.from({ length: 7 }, (_, index) => `src/f${index}.py`);
    const snapshot = snapshotFixture({ errorBundle: { ...errorBundle, relatedFiles: files } });
    const root = render(snapshot);
    expect(root.textContent).toContain("src/f0.py");
    expect(root.textContent).not.toContain("src/f5.py");
  });
});

describe("Phase 30 test failure data", () => {
  it("exposes the expected value", () => {
    expect(snapshotFixture().testFailure!.expected).toBe("True");
  });

  it("exposes the actual value", () => {
    expect(snapshotFixture().testFailure!.actual).toBe("False");
  });

  it("exposes related source files", () => {
    expect(snapshotFixture().testFailure!.relatedSource).toContain("src/auth/service.py");
  });

  it("exposes related symbols", () => {
    expect(Array.isArray(snapshotFixture().testFailure!.relatedSymbols)).toBe(true);
  });

  it("flags the patch-proposal-only boundary", () => {
    expect(snapshotFixture().testFailure!.patchProposalOnly).toBe(true);
  });

  it("is read-only", () => {
    expect(snapshotFixture().testFailure!.readOnly).toBe(true);
  });

  it("caps suggested investigation steps at four", () => {
    const testFailure = snapshotFixture().testFailure!;
    const steps = ["a", "b", "c", "d", "e", "f"];
    const snapshot = snapshotFixture({ testFailure: { ...testFailure, suggestedInvestigation: steps } });
    const root = render(snapshot);
    expect(root.textContent).toContain("• a");
    expect(root.textContent).not.toContain("• e");
  });

  it("truncates long test names in the UI", () => {
    const testFailure = snapshotFixture().testFailure!;
    const long = "t".repeat(300);
    const snapshot = snapshotFixture({ testFailure: { ...testFailure, test: long } });
    const root = render(snapshot);
    expect(root.textContent).toContain(long.slice(0, 120));
    expect(root.textContent).not.toContain(long.slice(120));
  });
});

describe("Phase 30 git diff data", () => {
  it("exposes added line counts", () => {
    expect(snapshotFixture().gitAnalysis!.changedFiles[0].added).toBe(10);
  });

  it("exposes removed line counts", () => {
    expect(snapshotFixture().gitAnalysis!.changedFiles[0].removed).toBe(2);
  });

  it("exposes changed symbols", () => {
    const symbol = snapshotFixture().gitAnalysis!.changedSymbols[0];
    expect(symbol.name).toBe("authenticate");
    expect(symbol.type).toBe("function");
    expect(symbol.file).toBe("src/auth/service.py");
    expect(symbol.line).toBe(1);
  });

  it("exposes affected tests", () => {
    expect(snapshotFixture().gitAnalysis!.affectedTests).toContain("tests/test_auth.py");
  });

  it("exposes affected dependencies", () => {
    expect(Array.isArray(snapshotFixture().gitAnalysis!.affectedDependencies)).toBe(true);
  });

  it("exposes summary stats", () => {
    const stats = snapshotFixture().gitAnalysis!.stats;
    expect(stats.files).toBe(2);
    expect(stats.added).toBe(11);
    expect(stats.removed).toBe(2);
    expect(stats.symbols).toBe(1);
    expect(stats.tests).toBe(1);
  });

  it("flags the no-git-mutation boundary", () => {
    expect(snapshotFixture().gitAnalysis!.noGitMutation).toBe(true);
  });

  it("is read-only", () => {
    expect(snapshotFixture().gitAnalysis!.readOnly).toBe(true);
  });

  it("renders an empty change summary without crashing", () => {
    const gitAnalysis = snapshotFixture().gitAnalysis!;
    const snapshot = snapshotFixture({ gitAnalysis: { ...gitAnalysis, changeSummary: [] } });
    const root = render(snapshot);
    expect(root.textContent).toContain("Git Diff Intelligence");
  });

  it("caps review points at four", () => {
    const gitAnalysis = snapshotFixture().gitAnalysis!;
    const points = ["p1", "p2", "p3", "p4", "p5"];
    const snapshot = snapshotFixture({ gitAnalysis: { ...gitAnalysis, reviewPoints: points } });
    const root = render(snapshot);
    expect(root.textContent).toContain("• p1");
    expect(root.textContent).not.toContain("• p5");
  });
});

describe("Phase 30 code review data", () => {
  it("exposes finding categories", () => {
    expect(snapshotFixture().review!.findings[0].category).toBe("security");
  });

  it("exposes finding explanations", () => {
    expect(snapshotFixture().review!.findings[0].explanation).toContain("shell=True");
  });

  it("exposes finding recommendations", () => {
    expect(snapshotFixture().review!.findings[0].recommendation).toContain("shell=False");
  });

  it("applies the danger tone to critical findings", () => {
    const root = render(snapshotFixture());
    const sev = root.querySelector(".phase30-severity.danger");
    expect(sev?.textContent).toBe("Critical");
  });

  it("applies the warn tone to medium findings", () => {
    const root = render(snapshotFixture());
    const sev = root.querySelector(".phase30-severity.warn");
    expect(sev?.textContent).toBe("Medium");
  });

  it("applies the ok tone to low findings", () => {
    const review = snapshotFixture().review!;
    const low = { ...review.findings[0], id: "low1", severity: "Low", category: "maintainability" };
    const snapshot = snapshotFixture({ review: { ...review, findings: [low] } });
    const root = render(snapshot);
    const sev = root.querySelector(".phase30-severity.ok");
    expect(sev?.textContent).toBe("Low");
  });

  it("caps findings at eight", () => {
    const review = snapshotFixture().review!;
    const many = Array.from({ length: 10 }, (_, index) => ({
      ...review.findings[0],
      id: `f${index}`,
      title: `finding ${index}`,
    }));
    const snapshot = snapshotFixture({ review: { ...review, findings: many } });
    const root = render(snapshot);
    expect(root.textContent).toContain("finding 0");
    expect(root.textContent).not.toContain("finding 8");
  });

  it("is suggestions-only", () => {
    const review = snapshotFixture().review!;
    expect(review.patchProposalOnly).toBe(true);
    expect(review.readOnly).toBe(true);
  });
});

describe("Phase 30 prompt injection data", () => {
  it("marks the system instruction as trusted", () => {
    expect(snapshotFixture().injection!.trusted).toBe("system");
  });

  it("marks project content as untrusted", () => {
    expect(snapshotFixture().injection!.untrusted).toContain("project_content");
  });

  it("exposes signal severity", () => {
    expect(snapshotFixture().injection!.signals[0].severity).toBe("high");
  });

  it("exposes the matched snippet", () => {
    expect(snapshotFixture().injection!.signals[0].snippet).toBe("ignore previous instructions");
  });

  it("is read-only", () => {
    expect(snapshotFixture().injection!.readOnly).toBe(true);
  });

  it("renders a clean verdict without bullet lines", () => {
    const injection = snapshotFixture().injection!;
    const snapshot = snapshotFixture({ injection: { ...injection, verdict: "clean", signals: [] } });
    const root = render(snapshot);
    const blocks = Array.from(root.querySelectorAll(".phase30-block"));
    const injectionBlock = blocks.find((block) => block.querySelector("h4")?.textContent === "Prompt Injection Protection");
    expect(injectionBlock?.textContent).toContain("clean");
    expect(injectionBlock?.textContent).not.toContain("• ");
  });
});

describe("Phase 30 budget data", () => {
  it("exposes the four standard buckets", () => {
    const buckets = snapshotFixture().budget.map((item) => item.bucket);
    expect(buckets).toEqual(["code", "tests", "git", "metadata"]);
  });

  it("never exceeds a bucket limit", () => {
    for (const usage of snapshotFixture().budget) {
      expect(usage.used).toBeLessThanOrEqual(usage.limit);
    }
  });

  it("computes remaining bytes correctly", () => {
    for (const usage of snapshotFixture().budget) {
      expect(usage.remaining).toBe(usage.limit - usage.used);
    }
  });

  it("exposes per-bucket item counts", () => {
    expect(snapshotFixture().budget[0].items).toBe(1);
  });

  it("flags snapshot security filtering", () => {
    expect(snapshotFixture().securityFiltering).toBe(true);
  });

  it("is read-only at the snapshot level", () => {
    expect(snapshotFixture().readOnly).toBe(true);
  });
});

describe("Phase 30 patch proposal data", () => {
  it("exposes proposal status", () => {
    expect(snapshotFixture().proposals[0].status).toBe("proposed");
  });

  it("exposes the applied flag", () => {
    expect(snapshotFixture().proposals[0].applied).toBe(false);
  });

  it("exposes the approval request id", () => {
    expect(snapshotFixture().proposals[0].approvalRequestId).toBe("req_1");
  });

  it("exposes the creation timestamp", () => {
    expect(snapshotFixture().proposals[0].createdAt).toBe("2026-08-19T00:00:00Z");
  });

  it("caps proposals at five", () => {
    const base = snapshotFixture().proposals[0];
    const many = Array.from({ length: 7 }, (_, index) => ({ ...base, id: `proposal-${index}`, reason: `reason ${index}` }));
    const snapshot = snapshotFixture({ proposals: many });
    const root = render(snapshot);
    expect(root.textContent).toContain("reason 0");
    expect(root.textContent).not.toContain("reason 5");
  });

  it("renders high-risk proposals with the warn tone", () => {
    const base = snapshotFixture().proposals[0];
    const high = { ...base, id: "phigh-01", risk: "high" };
    const snapshot = snapshotFixture({ proposals: [high] });
    const root = render(snapshot);
    const warnLines = Array.from(root.querySelectorAll(".phase30-line.warn"));
    expect(warnLines.some((line) => line.textContent?.includes("phigh-01"))).toBe(true);
  });
});

describe("Phase 30 snapshot structure", () => {
  it("carries the source marker", () => {
    expect(snapshotFixture().source).toBe("context/dev/intelligence");
  });

  it("carries the project id", () => {
    expect(snapshotFixture().project).toBe("demo");
  });

  it("keeps relationships as a nullable field", () => {
    expect(snapshotFixture().relationships).toBeNull();
  });

  it("renders every section as no-data when only the shell is present", () => {
    const snapshot = snapshotFixture({
      suggested: null,
      errorBundle: null,
      testFailure: null,
      gitAnalysis: null,
      review: null,
      injection: null,
      proposals: [],
    });
    const root = render(snapshot);
    expect(root.textContent).toContain("No suggestion data");
    expect(root.textContent).toContain("No error analysis");
    expect(root.textContent).toContain("No test-failure analysis");
    expect(root.textContent).toContain("No git diff analysis");
    expect(root.textContent).toContain("No code review");
    expect(root.textContent).toContain("No injection scan");
    expect(root.textContent).toContain("No approved patch proposals yet.");
  });

  it("never includes file contents in suggested items", () => {
    for (const item of snapshotFixture().suggested!.items) {
      expect("content" in item).toBe(false);
    }
  });
});

describe("Phase 30 store integration", () => {
  it("merges phase30 intelligence without clobbering other state", async () => {
    const store = new ExtensionStore();
    await store.update({ phase30Intelligence: snapshotFixture() });
    const state = store.getState();
    expect(state.phase30Intelligence?.project).toBe("demo");
    expect(state.bridgeStatus).toBe("unknown");
    expect(state.currentProject).toBeNull();
  });

  it("overwrites existing phase30 intelligence", async () => {
    const store = new ExtensionStore();
    await store.update({ phase30Intelligence: snapshotFixture() });
    await store.update({ phase30Intelligence: snapshotFixture({ project: "other" }) });
    expect(store.getState().phase30Intelligence?.project).toBe("other");
  });

  it("persists the snapshot for rendering", async () => {
    const store = new ExtensionStore();
    await store.update({ phase30Intelligence: snapshotFixture() });
    expect(store.getState().phase30Intelligence?.readOnly).toBe(true);
  });
});

describe("Phase 30 client error handling", () => {
  async function expectStatus(call: Promise<unknown>, status: number): Promise<void> {
    try {
      await call;
    } catch (error) {
      expect(error).toBeInstanceOf(BridgeRequestError);
      expect((error as BridgeRequestError).status).toBe(status);
      return;
    }
    throw new Error("expected BridgeRequestError");
  }

  it("rejects suggest on 404", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "not_found", message: "missing" }), { status: 404 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.contextIntelligenceSuggest("demo", "auth"), 404);
  });

  it("rejects relationships on 500", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "boom" }), { status: 500 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.contextIntelligenceRelationships("demo", "src/app.py"), 500);
  });

  it("rejects git analysis on 403", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "forbidden" }), { status: 403 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(client.contextIntelligenceGit("demo"), 403);
  });

  it("rejects patch proposal staging on 400", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: "bad_request" }), { status: 400 }));
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await expectStatus(
      client.stagePatchProposal({
        project: "demo",
        target_file: "src/app.py",
        proposed_change: "x",
        reason: "y",
        expected_impact: "z",
        risk: "low",
      }),
      400,
    );
  });

  it("issues GET requests without a body", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(_input)).toContain("/context/dev/intelligence/snapshot");
      expect(init?.method).toBeUndefined();
      expect(init?.body).toBeUndefined();
      return response(snapshotFixture());
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.contextIntelligenceSnapshot("demo");
  });

  it("passes every field of a patch proposal", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      expect(body.project).toBe("demo");
      expect(body.target_file).toBe("src/auth/service.py");
      expect(body.proposed_change).toBe("add rate limiting");
      expect(body.reason).toBe("prevent brute force");
      expect(body.expected_impact).toBe("slower logins");
      expect(body.risk).toBe("medium");
      return response({ requestId: "req_9", status: "pending", preview: "RECORD Patch Proposal" });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.stagePatchProposal({
      project: "demo",
      target_file: "src/auth/service.py",
      proposed_change: "add rate limiting",
      reason: "prevent brute force",
      expected_impact: "slower logins",
      risk: "medium",
    });
  });
});
