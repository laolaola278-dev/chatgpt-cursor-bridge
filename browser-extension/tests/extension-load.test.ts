import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConversationObserver } from "../src/content/dom-observer";
import { defaultSelectorAdapter } from "../src/content/selectors";
import { mountShadowHost, HOST_ID } from "../src/ui/shadow-root";

vi.mock("../src/ui/styles.css?inline", () => ({ default: ".panel{}" }));

const manifest = JSON.parse(
  readFileSync(resolve(__dirname, "../manifest.json"), "utf-8"),
) as Record<string, any>;

describe("1. extension loads with a valid MV3 manifest", () => {
  it("declares manifest v3 and the required entry points", () => {
    expect(manifest.manifest_version).toBe(3);
    expect(manifest.background.service_worker).toBe("background/service-worker.js");
    // Bundles are self-contained IIFEs, so no "type": "module" is required.
    expect(manifest.background.type).toBeUndefined();
    expect(manifest.content_scripts[0].js).toEqual(["content/content.js"]);
  });

  it("uses least privilege permissions", () => {
    expect(manifest.permissions.sort()).toEqual(["scripting", "storage"]);
    expect(manifest.permissions).not.toContain("tabs");
    expect(manifest.permissions).not.toContain("<all_urls>");
  });

  it("restricts host permissions to ChatGPT and the local bridge", () => {
    for (const host of manifest.host_permissions as string[]) {
      expect(host).toMatch(/^https:\/\/(chatgpt\.com|chat\.openai\.com)\/\*$|^http:\/\/127\.0\.0\.1:\d+\/\*$/);
    }
    expect(manifest.host_permissions).not.toContain("<all_urls>");
    expect(manifest.host_permissions).not.toContain("*://*/*");
  });

  it("only injects content scripts on ChatGPT pages", () => {
    expect(manifest.content_scripts[0].matches).toEqual([
      "https://chatgpt.com/*",
      "https://chat.openai.com/*",
    ]);
  });
});

describe("2. UI injection into the page", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("mounts a shadow root host that does not leak styles", () => {
    const ui = mountShadowHost(document);
    const host = document.getElementById(HOST_ID);

    expect(host).not.toBeNull();
    expect(ui.shadow).toBeTruthy();
    expect(ui.shadow.querySelector("style")?.textContent).toContain(".panel");
    // Panel markup lives inside the shadow root, not in the page DOM.
    expect(document.querySelector(".ccb-container")).toBeNull();
    expect(ui.shadow.querySelector(".ccb-container")).not.toBeNull();
  });

  it("is idempotent: re-mounting replaces the previous host", () => {
    mountShadowHost(document);
    mountShadowHost(document);
    expect(document.querySelectorAll(`#${HOST_ID}`)).toHaveLength(1);
  });

  it("only recognises ChatGPT hosts", () => {
    expect(defaultSelectorAdapter.isChatGPTHost("chatgpt.com")).toBe(true);
    expect(defaultSelectorAdapter.isChatGPTHost("chat.openai.com")).toBe(true);
    expect(defaultSelectorAdapter.isChatGPTHost("evil.com")).toBe(false);
    expect(defaultSelectorAdapter.isChatGPTHost("chatgpt.com.evil.com")).toBe(false);
  });
});

describe("3. MutationObserver captures streamed messages", () => {
  beforeEach(() => {
    document.body.innerHTML = "<main><div role='log'></div></main>";
  });

  const validBlock = `<ccb_action>${JSON.stringify({
    version: "1.0",
    action: "file.write",
    target: { project: "demo", path: "src/main.ts" },
    reason: "update entry point",
    risk: "medium",
    payload: { content: "export const x = 1;\n" },
  })}</ccb_action>`;

  it("detects an action appended after start()", async () => {
    const received: string[] = [];
    const observer = new ConversationObserver({
      debounceMs: 1,
      onResults: (results) => {
        for (const result of results) {
          if (result.ok) received.push(result.action.action);
        }
      },
    });

    expect(observer.start(document)).toBe(true);
    expect(observer.attached).toBe(true);

    const log = document.querySelector("[role='log']")!;
    const message = document.createElement("article");
    message.setAttribute("data-message-author-role", "assistant");
    message.textContent = validBlock;
    log.appendChild(message);

    await new Promise((done) => setTimeout(done, 40));
    expect(received).toEqual(["file.write"]);

    observer.stop();
    expect(observer.attached).toBe(false);
  });

  it("does not emit the same action twice", () => {
    const seen: unknown[] = [];
    const observer = new ConversationObserver({
      debounceMs: 1,
      onResults: (results) => seen.push(...results),
    });

    const log = document.querySelector("[role='log']")!;
    const message = document.createElement("article");
    message.setAttribute("data-message-author-role", "assistant");
    message.textContent = validBlock;
    log.appendChild(message);

    observer.start(document);
    expect(seen).toHaveLength(1);

    observer.scan();
    observer.scan();
    expect(seen).toHaveLength(1);

    observer.stop();
  });

  it("ignores plain conversation text", () => {
    const seen: unknown[] = [];
    const observer = new ConversationObserver({
      debounceMs: 1,
      onResults: (results) => seen.push(...results),
    });

    const log = document.querySelector("[role='log']")!;
    const message = document.createElement("article");
    message.setAttribute("data-message-author-role", "assistant");
    message.textContent = "Sure, I will modify src/main.ts and delete the old file.";
    log.appendChild(message);

    observer.start(document);
    expect(seen).toHaveLength(0);
    observer.stop();
  });
});
