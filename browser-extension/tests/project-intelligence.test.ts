import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderProjectIntelligenceDashboard } from "../src/project-intelligence/project-intelligence-dashboard";
import type { ProjectProfile } from "../src/project-intelligence/models";

const profile: ProjectProfile = {
  projectId: "demo",
  languages: { Python: 4, TypeScript: 2 },
  frameworks: ["FastAPI/Python"],
  architectureSummary: "layered",
  moduleCount: 6,
  complexityScore: 18,
  readOnly: true,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("Project Intelligence dashboard", () => {
  it("renders the read-only heading", () => {
    const root = renderProjectIntelligenceDashboard(document, profile, null, null, null);
    expect(root.dataset.role).toBe("project-intelligence-dashboard");
    expect(root.textContent).toContain("Project Intelligence");
    expect(root.textContent).toContain("READ ONLY");
  });

  it("renders project overview metrics", () => {
    const root = renderProjectIntelligenceDashboard(document, profile, null, null, null);
    expect(root.textContent).toContain("6 modules");
    expect(root.textContent).toContain("Complexity 18/100");
    expect(root.textContent).toContain("layered");
  });

  it("renders a graph summary", () => {
    const root = renderProjectIntelligenceDashboard(document, profile, { project: "demo", nodes: [{ id: "module:a", type: "Module", label: "a.py", metadata: {} }], edges: [], readOnly: true }, null, null);
    expect(root.textContent).toContain("1 nodes · 0 relations");
    expect(root.textContent).toContain("Module · a.py");
  });

  it("renders impact risk", () => {
    const root = renderProjectIntelligenceDashboard(document, profile, null, { project: "demo", changedFiles: ["a.py"], affectedModules: ["b.py"], risk: "high", readOnly: true }, null);
    expect(root.textContent).toContain("HIGH · 1 affected modules");
    expect(root.textContent).toContain("b.py");
  });

  it("renders memory history", () => {
    const root = renderProjectIntelligenceDashboard(document, profile, null, null, { project: "demo", history: [{ category: "decisions", path: "decisions/one.md", updatedAt: "2026-01-01T00:00:00Z", size: 20 }], readOnly: true });
    expect(root.textContent).toContain("decisions · 2026-01-01T00:00:00Z");
  });

  it("shows an empty state before indexing", () => {
    const root = renderProjectIntelligenceDashboard(document, null, null, null, null);
    expect(root.textContent).toContain("No indexed project yet");
    expect(root.textContent).toContain("approval-gated");
  });
});

describe("Project Intelligence bridge methods", () => {
  it("requests a project profile", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/project/profile?project=demo");
      return jsonResponse(profile);
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).projectProfile("demo");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("requests a project graph", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/project/graph?project=demo");
      return jsonResponse({ project: "demo", nodes: [], edges: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).projectGraph("demo");
  });

  it("encodes project names for graph queries", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("project=demo%20app");
      return jsonResponse({ project: "demo app", nodes: [], edges: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).projectGraph("demo app");
  });

  it("requests impact with repeated changed files", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      expect(url).toContain("changed_file=a.py");
      expect(url).toContain("changed_file=b.py");
      return jsonResponse({ project: "demo", changedFiles: ["a.py", "b.py"], affectedModules: [], risk: "low", readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).impactAnalysis("demo", ["a.py", "b.py"]);
  });

  it("requests project memory history", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/memory/project/history?project=demo");
      return jsonResponse({ project: "demo", history: [], readOnly: true });
    });
    await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).projectMemoryHistory("demo");
  });

  it("keeps all intelligence methods GET-only", async () => {
    const methods: string[] = [];
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      methods.push(init?.method ?? "GET");
      return jsonResponse({ project: "demo", nodes: [], edges: [], history: [], affectedModules: [], changedFiles: [], risk: "low", readOnly: true });
    });
    const client = new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.projectProfile("demo");
    await client.projectGraph("demo");
    await client.impactAnalysis("demo");
    await client.projectMemoryHistory("demo");
    expect(methods).toEqual(["GET", "GET", "GET", "GET"]);
  });

  it("does not render execution controls", () => {
    const root = renderProjectIntelligenceDashboard(document, profile, null, null, null);
    expect(root.querySelector("button")).toBeNull();
    expect(root.textContent).not.toContain("Execute");
  });

  it("marks the dashboard root for refresh tests", () => {
    const root = renderProjectIntelligenceDashboard(document, profile, null, null, null);
    expect(root.matches("[data-role='project-intelligence-dashboard']")).toBe(true);
  });
});
