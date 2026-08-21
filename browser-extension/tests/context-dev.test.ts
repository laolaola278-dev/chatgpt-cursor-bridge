import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderContextDashboard } from "../src/context/context-dashboard";
import type { DevContextResponse } from "../src/context/types";
import { ExtensionStore, createInitialState } from "../src/state/store";

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

function fixture(overrides: Partial<DevContextResponse> = {}): DevContextResponse {
  return {
    source: "context/dev",
    project: "demo",
    agent: "ASSISTANT",
    contextType: "bundle",
    generatedAt: "2026-08-19T00:00:00Z",
    size: 4096,
    truncated: false,
    securityFiltering: true,
    projectContext: {
      project: "demo",
      workspaceRoot: "projects/demo",
      languages: { Python: 2, TypeScript: 1 },
      fileCount: 3,
      packageManagers: ["npm", "pip"],
      git: {
        branch: "main",
        clean: false,
        changedFiles: ["src/main.py"],
        untracked: [],
        staged: [],
        diff: "diff --git a/src/main.py",
        diffTruncated: false,
        commits: [{ hash: "abc1234", subject: "fix: initial", author: "tester", authoredAt: "2026-08-18T00:00:00Z" }],
        securityFiltered: true,
      },
      testStatus: { status: "passed" },
      buildStatus: { status: "passed" },
      truncated: false,
    },
    files: [
      { path: "src/main.py", language: "Python", size: 120 },
      { path: "src/types.ts", language: "TypeScript", size: 240 },
    ],
    symbols: {
      symbols: [
        { id: "sym-1", name: "run", type: "function", file: "src/main.py", line: 1, endLine: 3, signature: "run()", parent: null, exported: false },
        { id: "sym-2", name: "User", type: "interface", file: "src/types.ts", line: 1, endLine: 1, signature: "interface User", parent: null, exported: true },
      ],
      total: 2,
      truncated: false,
    },
    dependencies: {
      dependencies: [
        { name: "react", version: "^18.0.0", type: "runtime", sourceFile: "package.json" },
        { name: "fastapi", version: ">=0.100", type: "runtime", sourceFile: "requirements.txt" },
      ],
      total: 2,
      truncated: false,
    },
    git: {
      branch: "main",
      clean: false,
      changedFiles: ["src/main.py"],
      untracked: [],
      staged: [],
      diff: "diff --git a/src/main.py",
      diffTruncated: false,
      commits: [{ hash: "abc1234", subject: "fix: initial", author: "tester", authoredAt: "2026-08-18T00:00:00Z" }],
      securityFiltered: true,
    },
    tests: { testStatus: { status: "passed" }, buildStatus: { status: "passed" } },
    ...overrides,
  };
}

function render(devContext: DevContextResponse | null, selection: string[] = [], onToggle: (id: string) => void = () => {}) {
  return renderContextDashboard(document, devContext, selection, onToggle);
}

describe("Phase 29 developer context dashboard", () => {
  it("renders the heading", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("Developer Context");
  });

  it("renders READ ONLY badge", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("READ ONLY");
  });

  it("renders project name and agent", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("demo");
    expect(root.textContent).toContain("ASSISTANT");
  });

  it("renders bundle size and truncation flag", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("4.0 KB");
    expect(root.textContent).toContain("no");
  });

  it("renders truncated warning when bundle truncated", () => {
    const root = render(fixture({ truncated: true }));
    expect(root.textContent).toContain("yes");
  });

  it("renders security filtering as active", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("active");
  });

  it("renders project context detail", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("3 files");
    expect(root.textContent).toContain("Python");
    expect(root.textContent).toContain("npm");
  });

  it("renders git context detail", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("branch main");
    expect(root.textContent).toContain("1 changed");
  });

  it("renders test and build status", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("test passed");
    expect(root.textContent).toContain("build passed");
  });

  it("renders symbol rows", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("function run");
    expect(root.textContent).toContain("interface User");
    expect(root.textContent).toContain("(exported)");
  });

  it("renders dependency rows", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("react@^18.0.0");
    expect(root.textContent).toContain("fastapi@>=0.100");
  });

  it("shows empty state without context", () => {
    const root = render(null);
    expect(root.textContent).toContain("No developer context loaded");
  });

  it("does not render any execute/apply/approve control", () => {
    const root = render(fixture());
    // No buttons at all: the only interactive elements are context selectors.
    expect(root.querySelectorAll("button").length).toBe(0);
    const inputs = root.querySelectorAll("input");
    expect(inputs.length).toBeGreaterThan(0);
    for (const input of inputs) {
      expect(input.getAttribute("data-role")).toBe("context-select");
    }
  });
});

describe("Phase 29 context preview", () => {
  it("renders six context sections", () => {
    const root = render(fixture());
    const toggles = root.querySelectorAll<HTMLInputElement>('input[data-role="context-select"]');
    expect(toggles.length).toBe(6);
  });

  it("shows user-send note", () => {
    const root = render(fixture());
    expect(root.textContent).toContain("Nothing is sent automatically");
  });

  it("marks selected sections as checked", () => {
    const root = render(fixture(), ["git", "symbols"]);
    const toggles = root.querySelectorAll<HTMLInputElement>('input[data-role="context-select"]');
    const byId = new Map([...toggles].map((t) => [t.dataset.contextId, t.checked]));
    expect(byId.get("git")).toBe(true);
    expect(byId.get("symbols")).toBe(true);
    expect(byId.get("project")).toBe(false);
  });

  it("reports selected count in preview summary", () => {
    const root = render(fixture(), ["project", "git", "tests"]);
    expect(root.textContent).toContain("3 context item(s) ready to attach");
  });

  it("reports empty selection", () => {
    const root = render(fixture(), []);
    expect(root.textContent).toContain("No context items selected");
  });

  it("fires toggle callback on change", () => {
    const onToggle = vi.fn();
    const root = render(fixture(), [], onToggle);
    const toggle = root.querySelector<HTMLInputElement>('input[data-role="context-select"][data-context-id="git"]');
    expect(toggle).not.toBeNull();
    toggle!.dispatchEvent(new Event("change"));
    expect(onToggle).toHaveBeenCalledWith("git");
  });
});

describe("Phase 29 store state", () => {
  it("initialises dev context to null", () => {
    const state = createInitialState();
    expect(state.devContext).toBeNull();
    expect(state.devContextSelection).toEqual([]);
  });

  it("updates dev context", async () => {
    const store = new ExtensionStore();
    await store.update({ devContext: fixture() });
    expect(store.getState().devContext?.project).toBe("demo");
  });

  it("toggles dev context selection", async () => {
    const store = new ExtensionStore();
    await store.toggleDevContextSelection("git");
    expect(store.getState().devContextSelection).toEqual(["git"]);
    await store.toggleDevContextSelection("git");
    expect(store.getState().devContextSelection).toEqual([]);
  });

  it("clears dev context selection", async () => {
    const store = new ExtensionStore();
    await store.toggleDevContextSelection("project");
    await store.toggleDevContextSelection("tests");
    await store.clearDevContextSelection();
    expect(store.getState().devContextSelection).toEqual([]);
  });
});

describe("Phase 29 bridge client (GET only)", () => {
  it("fetches the context bundle", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/bundle?project=demo&agent=ASSISTANT");
      return response(fixture());
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.devContextBundle("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches a single file with encoded path", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/file/src%2Fmain.py");
      return response({ data: {} });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.devFile("demo", "src/main.py");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches symbols with query", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/symbols?project=demo&limit=200&q=User");
      return response({ data: { symbols: [], total: 0, truncated: false } });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.devSymbols("demo", "User");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches git context", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/git?project=demo");
      return response({ data: {} });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.devGit("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches tests context", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/tests?project=demo");
      return response({ data: { testStatus: null, buildStatus: null } });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.devTests("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("fetches dev status", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/context/dev/status?project=demo");
      return response({ project: "demo", available: {}, git: { branch: "main", clean: true }, testStatus: null, buildStatus: null, securityFiltering: true });
    });
    const client = new BridgeClient({ origin: "http://bridge.test", fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.devContextStatus("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
