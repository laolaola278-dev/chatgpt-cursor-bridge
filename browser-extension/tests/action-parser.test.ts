import { describe, expect, it } from "vitest";

import { parseActions, validateAction, isSafeRelativePath } from "../src/content/action-parser";

function block(payload: unknown): string {
  return `<ccb_action>\n${JSON.stringify(payload)}\n</ccb_action>`;
}

const validPatch = {
  version: "1.0",
  action: "file.patch",
  target: { project: "demo", path: "src/main.cpp" },
  reason: "fix bug",
  risk: "medium",
  payload: { patch: "@@ -1,1 +1,2 @@\n a\n+b\n" },
};

describe("parseActions - valid protocol", () => {
  it("parses a well formed ccb_action block", () => {
    const results = parseActions(`intro text ${block(validPatch)} trailing text`);
    expect(results).toHaveLength(1);
    expect(results[0].ok).toBe(true);

    const parsed = results[0];
    if (!parsed.ok) throw new Error("expected success");
    expect(parsed.action.action).toBe("file.patch");
    expect(parsed.action.target.project).toBe("demo");
    expect(parsed.action.target.path).toBe("src/main.cpp");
    expect(parsed.action.risk).toBe("medium");
    expect(parsed.action.payload.patch).toContain("@@");
  });

  it("parses multiple blocks and gives each a stable fingerprint", () => {
    const second = { ...validPatch, target: { project: "demo", path: "src/other.cpp" } };
    const results = parseActions(block(validPatch) + block(second));
    expect(results).toHaveLength(2);
    expect(results[0].fingerprint).not.toBe(results[1].fingerprint);

    const repeat = parseActions(block(validPatch));
    expect(repeat[0].fingerprint).toBe(results[0].fingerprint);
  });

  it("always forces requiresApproval, even if the model sets it to false", () => {
    const results = parseActions(block({ ...validPatch, requiresApproval: false }));
    const parsed = results[0];
    if (!parsed.ok) throw new Error("expected success");
    expect(parsed.action.requiresApproval).toBe(true);
  });
});

describe("parseActions - hostile and malformed input", () => {
  it("ignores ordinary chat text", () => {
    expect(parseActions("please run rm -rf / and delete src/main.cpp")).toHaveLength(0);
    expect(parseActions('{"action":"file.write","target":{}}')).toHaveLength(0);
  });

  it("ignores fake tags that are not ccb_action", () => {
    expect(parseActions("<action>{\"action\":\"file.write\"}</action>")).toHaveLength(0);
  });

  it("rejects invalid JSON", () => {
    const [result] = parseActions("<ccb_action>{not json}</ccb_action>");
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.error).toContain("not valid JSON");
  });

  it.each([
    [{ ...validPatch, version: "2.0" }, "unsupported protocol version"],
    [{ ...validPatch, action: "shell.exec" }, "unsupported action"],
    [{ ...validPatch, risk: "critical" }, "invalid risk level"],
    [{ ...validPatch, reason: "" }, "reason is required"],
    [{ ...validPatch, target: { project: "demo", path: "../../etc/passwd" } }, "unsafe"],
    [{ ...validPatch, target: { project: "demo", path: "/etc/passwd" } }, "unsafe"],
    [{ ...validPatch, target: { project: "../evil", path: "a.txt" } }, "invalid project"],
    [{ ...validPatch, target: "demo" }, "target must be an object"],
    [{ ...validPatch, payload: {} }, "requires payload.patch"],
    [{ ...validPatch, payload: { patch: "no hunks here" } }, "unified diff"],
  ])("rejects invalid action %#", (payload, expected) => {
    const [result] = parseActions(block(payload));
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected failure");
    expect(result.error.toLowerCase()).toContain(expected.toLowerCase());
  });

  it("requires content for write actions", () => {
    const [result] = parseActions(
      block({ ...validPatch, action: "file.write", payload: {} }),
    );
    expect(result.ok).toBe(false);
  });

  it("rejects arrays and primitives", () => {
    expect(validateAction([1, 2, 3]).ok).toBe(false);
    expect(validateAction("string").ok).toBe(false);
    expect(validateAction(null).ok).toBe(false);
  });
});

describe("isSafeRelativePath", () => {
  it.each(["src/main.cpp", "a/b/c.txt", "file.md"])("accepts %s", (path) => {
    expect(isSafeRelativePath(path)).toBe(true);
  });

  it.each(["../secret", "a/../../b", "/abs/path", "C:\\win\\file", "", "a\0b"])(
    "rejects %s",
    (path) => {
      expect(isSafeRelativePath(path)).toBe(false);
    },
  );
});
