import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderApprovalCard, renderRecoveredApprovalCard } from "../src/ui/approval-card";
import { Panel } from "../src/ui/panel";
import { createInitialState, ExtensionStore } from "../src/state/store";
import type { PendingAction } from "../src/models/action";
import type { RecoveredApproval } from "../src/bridge/types";

vi.mock("../src/ui/styles.css?inline", () => ({ default: ".panel{}" }));

function pendingItem(overrides: Partial<PendingAction> = {}): PendingAction {
  return {
    id: "act_1",
    state: "pending",
    createdAt: "2026-01-01T00:00:00.000Z",
    fingerprint: "fp_1",
    action: {
      version: "1.0",
      action: "file.write",
      target: { project: "demo", path: "src/main.cpp" },
      reason: "Fix memory leak",
      risk: "medium",
      payload: { content: "int main(){}\n" },
      requiresApproval: true,
    },
    ...overrides,
  };
}

describe("approval card", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows operation, file, reason and risk", () => {
    const card = renderApprovalCard(document, pendingItem(), {
      onApprove: () => {},
      onReject: () => {},
    });
    const text = card.textContent ?? "";

    expect(text).toContain("Modify File");
    expect(text).toContain("src/main.cpp");
    expect(text).toContain("Fix memory leak");
    expect(text).toContain("medium");
    expect(card.querySelector(".risk")?.className).toContain("medium");
  });

  it("wires Approve and Reject buttons", () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    const card = renderApprovalCard(document, pendingItem(), { onApprove, onReject });

    card.querySelector<HTMLButtonElement>("[data-role='approve']")!.click();
    card.querySelector<HTMLButtonElement>("[data-role='reject']")!.click();

    expect(onApprove).toHaveBeenCalledWith("act_1");
    expect(onReject).toHaveBeenCalledWith("act_1");
  });

  it("hides buttons and shows the state once resolved", () => {
    const card = renderApprovalCard(
      document,
      pendingItem({ state: "approved", message: "Applied via Bridge" }),
      { onApprove: () => {}, onReject: () => {} },
    );

    expect(card.querySelector("[data-role='approve']")).toBeNull();
    expect(card.querySelector(".state")?.textContent).toBe("Applied via Bridge");
  });

  it("renders the diff preview when the Bridge returned one", () => {
    const card = renderApprovalCard(document, pendingItem({ preview: "@@ -1 +1 @@\n-a\n+b" }), {
      onApprove: () => {},
      onReject: () => {},
    });
    expect(card.querySelector(".preview")?.textContent).toContain("@@");
  });

  it("requires reconfirmation before recovered execution", () => {
    const recovered: RecoveredApproval = {
      requestId: "req_abcdef0123456789",
      action: "file_write",
      project: "demo",
      path: "README.md",
      reason: "Change docs",
      preview: "diff",
      status: "recovered",
      createdAt: "2026-01-01T00:00:00Z",
    };
    const onReconfirm = vi.fn();
    const onApprove = vi.fn();
    const card = renderRecoveredApprovalCard(document, recovered, onReconfirm, onApprove);

    expect(card.textContent).toContain("RECONFIRM REQUIRED");
    card.querySelector<HTMLButtonElement>("[data-role='reconfirm']")!.click();
    expect(onReconfirm).toHaveBeenCalledWith(recovered.requestId);
    expect(onApprove).not.toHaveBeenCalled();
  });
});

describe("floating panel", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("renders bridge status, project and pending count", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);

    const panel = new Panel(document, container, {
      onConnect: () => {},
      onSelectProject: () => {},
      onApprove: () => {},
      onReject: () => {},
    });
    panel.setProjects(["demo", "other"]);
    panel.render({
      ...createInitialState(),
      // Sessions and the engineering dashboards are Developer Mode surfaces.
      uiMode: "developer",
      bridgeStatus: "connected",
      currentProject: "demo",
      pendingActions: [pendingItem()],
      sessions: [{ id: "ses_1", status: "ACTIVE" }],
    });

    const text = container.textContent ?? "";
    expect(text).toContain("ChatGPT Cursor Bridge");
    expect(text).toContain("Connected");
    expect(text).toContain("demo");
    expect(container.querySelector(".dot")?.className).toContain("connected");
    expect(container.querySelectorAll(".card")).toHaveLength(1);
    expect(text).toContain("Sessions:");
  });

  it("shows the offline hint when the Bridge is unreachable", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);

    const panel = new Panel(document, container, {
      onConnect: () => {},
      onSelectProject: () => {},
      onApprove: () => {},
      onReject: () => {},
    });
    panel.render({ ...createInitialState(), bridgeStatus: "offline" });

    expect(container.textContent).toContain("Local Bridge unavailable");
  });

  it("emits connect and project selection intents", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const onConnect = vi.fn();
    const onSelectProject = vi.fn();

    const panel = new Panel(document, container, {
      onConnect,
      onSelectProject,
      onApprove: () => {},
      onReject: () => {},
    });
    panel.setProjects(["demo"]);
    panel.render(createInitialState());

    container.querySelector<HTMLButtonElement>("[data-role='connect']")!.click();
    expect(onConnect).toHaveBeenCalled();

    const select = container.querySelector<HTMLSelectElement>("[data-role='project-select']")!;
    select.value = "demo";
    select.dispatchEvent(new Event("change"));
    expect(onSelectProject).toHaveBeenCalledWith("demo");
  });
});

describe("extension state store", () => {
  it("persists and restores state through a storage adapter", async () => {
    const data = new Map<string, unknown>();
    const storage = {
      async get(key: string) {
        return data.has(key) ? { [key]: data.get(key) } : {};
      },
      async set(items: Record<string, unknown>) {
        for (const [key, value] of Object.entries(items)) data.set(key, value);
      },
    };

    const store = new ExtensionStore(storage);
    await store.hydrate();
    await store.setProject("demo");
    await store.setBridgeStatus("connected");

    const restored = new ExtensionStore(storage);
    const state = await restored.hydrate();

    expect(state.currentProject).toBe("demo");
    expect(state.bridgeStatus).toBe("connected");
  });

  it("counts only pending actions and de-duplicates by fingerprint", async () => {
    const store = new ExtensionStore();
    await store.addPending(pendingItem());
    await store.addPending(pendingItem({ id: "act_dup" }));
    expect(store.getState().pendingActions).toHaveLength(1);

    await store.addPending(pendingItem({ id: "act_2", fingerprint: "fp_2" }));
    expect(store.pendingCount).toBe(2);

    await store.patchPending("act_2", { state: "rejected" });
    expect(store.pendingCount).toBe(1);
  });
});
