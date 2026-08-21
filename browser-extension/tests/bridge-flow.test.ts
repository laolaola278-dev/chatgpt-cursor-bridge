import { beforeEach, describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { BridgeRequestError, BridgeUnavailableError } from "../src/bridge/types";
import { Controller } from "../src/content/controller";
import { parseActions } from "../src/content/action-parser";
import { ExtensionStore } from "../src/state/store";
import type { CCBAction } from "../src/models/action";

const ORIGIN = "http://127.0.0.1:8765";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function writeAction(): CCBAction {
  const [result] = parseActions(
    `<ccb_action>${JSON.stringify({
      version: "1.0",
      action: "file.write",
      target: { project: "demo", path: "src/main.ts" },
      reason: "fix memory leak",
      risk: "medium",
      payload: { content: "export const x = 1;\n" },
    })}</ccb_action>`,
  );
  if (!result.ok) throw new Error("fixture must be valid");
  return result.action;
}

const PENDING_RESPONSE = {
  allowed: false,
  requireApproval: true,
  permissionLevel: "LEVEL_1",
  risk: "medium",
  reason: "fix memory leak",
  status: "pending",
  requestId: "req_abcdef0123456789",
  action: "file_write",
  project: "demo",
  path: "src/main.ts",
  preview: "--- a/src/main.ts\n+++ b/src/main.ts\n@@ -1 +1 @@\n-old\n+new\n",
  createdAt: "2026-01-01T00:00:00+00:00",
};

const EXECUTED_RESPONSE = {
  allowed: true,
  requireApproval: false,
  permissionLevel: "LEVEL_1",
  requestId: "req_abcdef0123456789",
  action: "file_write",
  status: "executed",
  project: "demo",
  path: "src/main.ts",
  result: { file: "src/main.ts", size: 21, created: false, diff: "..." },
};

describe("6. Bridge connection succeeds", () => {
  it("reports connected and loads the project list", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return jsonResponse(200, { status: "ok", service: "bridge", version: "0.1.0" });
      }
      if (url.endsWith("/workspace/list")) {
        return jsonResponse(200, { projects: [{ name: "demo", path: "/w/demo" }] });
      }
      throw new Error(`unexpected ${url}`);
    });

    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl: fetchImpl as unknown as typeof fetch }),
      render: () => {},
    });

    await controller.connect();

    expect(store.getState().bridgeStatus).toBe("connected");
    // A single project is auto-selected for convenience (not auto-executed).
    expect(store.getState().currentProject).toBe("demo");
  });
});

describe("7. Bridge offline handling", () => {
  it("maps network failures to a friendly message", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const client = new BridgeClient({ origin: ORIGIN, fetchImpl: fetchImpl as unknown as typeof fetch });

    await expect(client.health()).rejects.toBeInstanceOf(BridgeUnavailableError);
  });

  it("sets offline status and surfaces the message in state", async () => {
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({
        origin: ORIGIN,
        fetchImpl: (async () => {
          throw new TypeError("Failed to fetch");
        }) as unknown as typeof fetch,
      }),
      render: () => {},
    });

    await controller.connect();

    expect(store.getState().bridgeStatus).toBe("offline");
    expect(store.getState().lastResult).toBe("Local Bridge unavailable");
  });

  it("propagates structured bridge errors", async () => {
    const client = new BridgeClient({
      origin: ORIGIN,
      fetchImpl: (async () =>
        jsonResponse(403, { error: "sandbox_violation", message: "escapes sandbox" })) as unknown as typeof fetch,
    });

    await expect(client.health()).rejects.toBeInstanceOf(BridgeRequestError);
  });
});

describe("8. Approve flow", () => {
  let calls: Array<{ url: string; body: unknown }>;
  let fetchImpl: typeof fetch;

  beforeEach(() => {
    calls = [];
    fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.endsWith("/file/write")) return jsonResponse(202, PENDING_RESPONSE);
      if (url.endsWith("/permission/approve")) return jsonResponse(200, EXECUTED_RESPONSE);
      throw new Error(`unexpected ${url}`);
    }) as unknown as typeof fetch;
  });

  it("captures an action as pending without touching the Bridge", async () => {
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl }),
      render: () => {},
    });

    await controller.handleParseResults(
      parseActions(
        `<ccb_action>${JSON.stringify({
          version: "1.0",
          action: "file.write",
          target: { project: "demo", path: "src/main.ts" },
          reason: "fix memory leak",
          risk: "medium",
          payload: { content: "export const x = 1;\n" },
        })}</ccb_action>`,
      ),
    );

    expect(store.getState().pendingActions).toHaveLength(1);
    expect(store.getState().pendingActions[0].state).toBe("pending");
    // No auto-execution: nothing was sent to the Bridge yet.
    expect(calls).toHaveLength(0);
  });

  it("stages then approves in two explicit calls", async () => {
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl }),
      render: () => {},
    });

    await store.addPending({
      id: "act_1",
      action: writeAction(),
      state: "pending",
      createdAt: new Date().toISOString(),
      fingerprint: "fp_1",
    });

    await controller.approve("act_1");

    expect(calls.map((call) => call.url)).toEqual([
      `${ORIGIN}/file/write`,
      `${ORIGIN}/permission/approve`,
    ]);
    expect(calls[1].body).toEqual({ request_id: "req_abcdef0123456789" });

    const item = store.getState().pendingActions[0];
    expect(item.state).toBe("approved");
    expect(item.bridgeRequestId).toBe("req_abcdef0123456789");
    expect(item.preview).toContain("@@");

    const log = store.getState().log;
    expect(log.some((entry) => entry.event === "action.approved" && entry.approved)).toBe(true);
  });

  it("marks the action failed when the Bridge rejects it", async () => {
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({
        origin: ORIGIN,
        fetchImpl: (async () =>
          jsonResponse(403, { error: "sandbox_violation", message: "escapes sandbox" })) as unknown as typeof fetch,
      }),
      render: () => {},
    });

    await store.addPending({
      id: "act_2",
      action: writeAction(),
      state: "pending",
      createdAt: new Date().toISOString(),
      fingerprint: "fp_2",
    });

    await controller.approve("act_2");

    const item = store.getState().pendingActions[0];
    expect(item.state).toBe("failed");
    expect(item.message).toContain("escapes sandbox");
  });
});

describe("9. Reject flow", () => {
  it("records the rejection and never calls the Bridge", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, {}));
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl: fetchImpl as unknown as typeof fetch }),
      render: () => {},
    });

    await store.addPending({
      id: "act_3",
      action: writeAction(),
      state: "pending",
      createdAt: new Date().toISOString(),
      fingerprint: "fp_3",
    });

    await controller.reject("act_3");

    expect(fetchImpl).not.toHaveBeenCalled();
    expect(store.getState().pendingActions[0].state).toBe("rejected");

    const log = store.getState().log;
    expect(log.some((entry) => entry.event === "action.rejected" && entry.result === "rejected")).toBe(
      true,
    );
  });

  it("ignores approve after reject", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, {}));
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN, fetchImpl: fetchImpl as unknown as typeof fetch }),
      render: () => {},
    });

    await store.addPending({
      id: "act_4",
      action: writeAction(),
      state: "pending",
      createdAt: new Date().toISOString(),
      fingerprint: "fp_4",
    });

    await controller.reject("act_4");
    await controller.approve("act_4");

    expect(fetchImpl).not.toHaveBeenCalled();
    expect(store.getState().pendingActions[0].state).toBe("rejected");
  });

  it("logs schema-invalid actions as ignored and never queues them", async () => {
    const store = new ExtensionStore();
    const controller = new Controller({
      store,
      client: new BridgeClient({ origin: ORIGIN }),
      render: () => {},
    });

    await controller.handleParseResults(
      parseActions("<ccb_action>{\"version\":\"1.0\",\"action\":\"shell.exec\"}</ccb_action>"),
    );

    expect(store.getState().pendingActions).toHaveLength(0);
    expect(store.getState().log[0].result).toBe("ignored");
  });
});
