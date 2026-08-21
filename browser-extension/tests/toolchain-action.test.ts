import { describe, expect, it, vi } from "vitest";

import { parseActions } from "../src/content/action-parser";
import { BridgeClient } from "../src/bridge/client";

function block(payload: unknown): string {
  return `<ccb_action>${JSON.stringify(payload)}</ccb_action>`;
}

const base = {
  version: "1.0",
  target: { project: "demo" },
  reason: "engineering verification",
  risk: "low",
};

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

describe("Phase 6 toolchain protocol", () => {
  it.each(["git.status", "git.diff", "workflow.status"])("parses %s", (action) => {
    const extra = action === "workflow.status" ? { workflow_id: "wf_aaaaaaaaaaaaaaaa" } : {};
    const [result] = parseActions(block({ ...base, ...extra, action, payload: {} }));
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.action.requiresApproval).toBe(true);
  });

  it("parses test.run with workflow binding", () => {
    const [result] = parseActions(block({
      ...base,
      action: "test.run",
      risk: "medium",
      workflow_id: "wf_aaaaaaaaaaaaaaaa",
      stage_id: "stg_bbbbbbbbbbbbbbbb",
      payload: { command: "pytest" },
    }));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.action.payload.command).toBe("pytest");
    expect(result.action.workflow_id).toBe("wf_aaaaaaaaaaaaaaaa");
  });

  it.each(["pytest; whoami", "npm run test", "bash test.sh", "cmake --build ."])(
    "rejects non-whitelisted test command %s",
    (command) => {
      const [result] = parseActions(block({
        ...base,
        action: "test.run",
        workflow_id: "wf_aaaaaaaaaaaaaaaa",
        stage_id: "stg_bbbbbbbbbbbbbbbb",
        payload: { command },
      }));
      expect(result.ok).toBe(false);
    },
  );

  it("rejects test.run without workflow and stage", () => {
    const [result] = parseActions(block({ ...base, action: "test.run", payload: { command: "pytest" } }));
    expect(result.ok).toBe(false);
  });

  it("rejects invalid workflow identifiers", () => {
    const [result] = parseActions(block({
      ...base,
      action: "workflow.status",
      workflow_id: "../workflow",
      payload: {},
    }));
    expect(result.ok).toBe(false);
  });

  it("validates git.diff staged boolean", () => {
    const [bad] = parseActions(block({ ...base, action: "git.diff", payload: { staged: "yes" } }));
    expect(bad.ok).toBe(false);
    const [good] = parseActions(block({ ...base, action: "git.diff", payload: { staged: true } }));
    expect(good.ok).toBe(true);
  });

  it("BridgeClient calls git diff without executing shell", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      response({ diff: "@@", staged: true }),
    );
    const client = new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    const result = await client.gitDiff("demo", true);
    expect(result.diff).toBe("@@");
    expect(String(fetchImpl.mock.calls[0][0])).toContain("/git/diff?project=demo&staged=true");
  });

  it("BridgeClient stages test.run at the fixed API", async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      response({ requestId: "req_x" }),
    );
    const client = new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch });
    await client.runTest({
      project: "demo", workflow_id: "wf_aaaaaaaaaaaaaaaa",
      stage_id: "stg_bbbbbbbbbbbbbbbb", command: "pytest", reason: "verify",
    });
    expect(String(fetchImpl.mock.calls[0][0])).toContain("/test/run");
    const init = fetchImpl.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body)).command).toBe("pytest");
  });
});
