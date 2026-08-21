import { describe, expect, it, vi } from "vitest";

import { parseActions } from "../src/content/action-parser";
import { BridgeClient } from "../src/bridge/client";
import { Controller } from "../src/content/controller";
import { ExtensionStore } from "../src/state/store";
import { renderApprovalCard } from "../src/ui/approval-card";
import type { CCBAction } from "../src/models/action";

vi.mock("../src/ui/styles.css?inline", () => ({ default: ".panel{}" }));

const ORIGIN = "http://127.0.0.1:8765";

function block(payload: unknown): string {
  return `<ccb_action>${JSON.stringify(payload)}</ccb_action>`;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const APPEND_ACTION = {
  version: "1.0",
  action: "memory.append",
  target: { project: "demo", document: "tasks.md" },
  reason: "record current task",
  risk: "medium",
  payload: { content: "- [ ] implement memory system" },
};

const DECISION_ACTION = {
  version: "1.0",
  action: "memory.decision",
  target: { project: "demo", document: "decisions.md" },
  reason: "record ADR",
  risk: "medium",
  payload: {
    title: "Use SQLite for the memory index",
    context: "We need fast lookups without full text duplication.",
    decision: "Store index metadata only in memory.db.",
    consequence: "Markdown stays the source of truth.",
  },
};

describe("memory action protocol parsing", () => {
  it("parses memory.append and normalises the target", () => {
    const [result] = parseActions(block(APPEND_ACTION));
    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("expected success");

    expect(result.action.action).toBe("memory.append");
    expect(result.action.target.document).toBe("tasks.md");
    expect(result.action.target.path).toBe("memory/tasks.md");
    expect(result.action.payload.content).toContain("implement memory system");
    expect(result.action.requiresApproval).toBe(true);
  });

  it("accepts a document name without the .md suffix", () => {
    const [result] = parseActions(
      block({ ...APPEND_ACTION, target: { project: "demo", document: "changelog" } }),
    );
    if (!result.ok) throw new Error("expected success");
    expect(result.action.target.document).toBe("changelog.md");
  });

  it("parses memory.read", () => {
    const [result] = parseActions(
      block({
        version: "1.0",
        action: "memory.read",
        target: { project: "demo", document: "project.md" },
        reason: "load project context",
        risk: "low",
        payload: {},
      }),
    );
    if (!result.ok) throw new Error("expected success");
    expect(result.action.action).toBe("memory.read");
    expect(result.action.target.document).toBe("project.md");
  });

  it("parses memory.decision with all ADR fields", () => {
    const [result] = parseActions(block(DECISION_ACTION));
    if (!result.ok) throw new Error("expected success");
    expect(result.action.payload.title).toBe("Use SQLite for the memory index");
    expect(result.action.payload.context).toBeTruthy();
    expect(result.action.payload.decision).toBeTruthy();
    expect(result.action.payload.consequence).toBeTruthy();
  });

  it.each([
    [{ ...APPEND_ACTION, target: { project: "demo", document: "secrets.md" } }, "unknown memory document"],
    [{ ...APPEND_ACTION, target: { project: "demo", document: "../beta/project.md" } }, "unknown memory document"],
    [{ ...APPEND_ACTION, target: { project: "demo" } }, "require target.document"],
    [{ ...APPEND_ACTION, payload: {} }, "requires payload.content"],
    [{ ...DECISION_ACTION, payload: { ...DECISION_ACTION.payload, title: "" } }, "payload.title"],
    [
      { ...DECISION_ACTION, payload: { ...DECISION_ACTION.payload, consequence: "  " } },
      "payload.consequence",
    ],
  ])("rejects invalid memory action %#", (payload, expected) => {
    const [result] = parseActions(block(payload));
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.error.toLowerCase()).toContain(expected.toLowerCase());
  });

  it("rejects a memory action targeting another project via the project field", () => {
    const [result] = parseActions(
      block({ ...APPEND_ACTION, target: { project: "../beta", document: "tasks.md" } }),
    );
    expect(result.ok).toBe(false);
  });
});

describe("memory approval flow", () => {
  function pendingResponse(action: string, path: string) {
    return {
      allowed: false,
      requireApproval: true,
      permissionLevel: "LEVEL_1",
      risk: "medium",
      reason: "record",
      status: "pending",
      requestId: "req_0123456789abcdef",
      action,
      project: "demo",
      path,
      preview: "[append -> tasks.md]\n\n- [ ] implement memory system",
      createdAt: "2026-01-01T00:00:00+00:00",
    };
  }

  function parsed(payload: unknown): CCBAction {
    const [result] = parseActions(block(payload));
    if (!result.ok) throw new Error("fixture must be valid");
    return result.action;
  }

  it("stages memory.append then approves in two explicit calls", async () => {
    const calls: string[] = [];
    const fetchImpl = (async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.endsWith("/memory/append")) {
        return jsonResponse(202, pendingResponse("memory_append", "memory/tasks.md"));
      }
      if (url.endsWith("/permission/approve")) {
        return jsonResponse(200, {
          allowed: true,
          requireApproval: false,
          permissionLevel: "LEVEL_1",
          requestId: "req_0123456789abcdef",
          action: "memory_append",
          status: "executed",
          project: "demo",
          path: "memory/tasks.md",
          result: { document: "tasks.md", appendedBytes: 64, size: 320 },
        });
      }
      throw new Error(`unexpected ${url}`);
    }) as unknown as typeof fetch;

    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl }),
      render: () => {},
    });

    await controller.handleParseResults(parseActions(block(APPEND_ACTION)));
    expect(store.getState().pendingActions).toHaveLength(1);
    expect(calls).toHaveLength(0); // captured only, nothing sent

    await controller.approve(store.getState().pendingActions[0].id);

    expect(calls).toEqual([`${ORIGIN}/memory/append`, `${ORIGIN}/permission/approve`]);
    expect(store.getState().pendingActions[0].state).toBe("approved");
  });

  it("routes memory.decision to /memory/decision with ADR fields", async () => {
    let body: Record<string, unknown> = {};
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/memory/decision")) {
        body = JSON.parse(String(init?.body));
        return jsonResponse(202, pendingResponse("memory_decision", "memory/decisions.md"));
      }
      return jsonResponse(200, {
        allowed: true,
        requireApproval: false,
        permissionLevel: "LEVEL_1",
        requestId: "req_0123456789abcdef",
        action: "memory_decision",
        status: "executed",
        project: "demo",
        path: "memory/decisions.md",
        result: { id: "ADR-001" },
      });
    }) as unknown as typeof fetch;

    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl }),
      render: () => {},
    });

    await store.addPending({
      id: "act_adr",
      action: parsed(DECISION_ACTION),
      state: "pending",
      createdAt: new Date().toISOString(),
      fingerprint: "fp_adr",
    });
    await controller.approve("act_adr");

    expect(body.title).toBe("Use SQLite for the memory index");
    expect(body.context).toBeTruthy();
    expect(body.decision).toBeTruthy();
    expect(body.consequence).toBeTruthy();
    expect(store.getState().pendingActions[0].state).toBe("approved");
  });

  it("reads memory through /memory/read instead of /file/read", async () => {
    const calls: string[] = [];
    const fetchImpl = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return jsonResponse(200, {
        project: "demo",
        document: "project.md",
        size: 42,
        content: "# Project\n",
      });
    }) as unknown as typeof fetch;

    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl }),
      render: () => {},
    });

    await store.addPending({
      id: "act_read",
      action: parsed({
        version: "1.0",
        action: "memory.read",
        target: { project: "demo", document: "project.md" },
        reason: "load context",
        risk: "low",
        payload: {},
      }),
      state: "pending",
      createdAt: new Date().toISOString(),
      fingerprint: "fp_read",
    });
    await controller.approve("act_read");

    expect(calls[0]).toContain("/memory/read");
    expect(calls[0]).toContain("document=project.md");
    expect(store.getState().pendingActions[0].preview).toContain("# Project");
  });

  it("rejecting a memory action never calls the Bridge", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, {}));
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl: fetchImpl as unknown as typeof fetch }),
      render: () => {},
    });

    await store.addPending({
      id: "act_rej",
      action: parsed(APPEND_ACTION),
      state: "pending",
      createdAt: new Date().toISOString(),
      fingerprint: "fp_rej",
    });
    await controller.reject("act_rej");

    expect(fetchImpl).not.toHaveBeenCalled();
    expect(store.getState().pendingActions[0].state).toBe("rejected");
  });
});

describe("memory approval card", () => {
  it("shows the memory document and ADR title", () => {
    const [result] = parseActions(block(DECISION_ACTION));
    if (!result.ok) throw new Error("expected success");

    const card = renderApprovalCard(
      document,
      {
        id: "act_1",
        action: result.action,
        state: "pending",
        createdAt: "2026-01-01T00:00:00.000Z",
        fingerprint: "fp_1",
      },
      { onApprove: () => {}, onReject: () => {} },
    );

    const text = card.textContent ?? "";
    expect(text).toContain("Record Decision (ADR)");
    expect(text).toContain("decisions.md");
    expect(text).toContain("Use SQLite for the memory index");
  });
});
