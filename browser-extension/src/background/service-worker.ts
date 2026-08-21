/**
 * MV3 service worker.
 *
 * Deliberately minimal: it initialises default storage and answers simple
 * status pings. It does NOT execute actions and does NOT talk to the Bridge
 * on its own, so there is no path that bypasses user approval.
 */

import { createInitialState, STORAGE_KEY } from "../state/store";

type Message = { type: "ccb:get-state" } | { type: "ccb:ping" };

chrome.runtime.onInstalled.addListener(() => {
  void chrome.storage.local.get(STORAGE_KEY).then((stored) => {
    if (!stored[STORAGE_KEY]) {
      void chrome.storage.local.set({ [STORAGE_KEY]: createInitialState() });
    }
  });
});

chrome.runtime.onMessage.addListener((message: Message, _sender, sendResponse) => {
  if (message?.type === "ccb:ping") {
    sendResponse({ ok: true });
    return false;
  }

  if (message?.type === "ccb:get-state") {
    void chrome.storage.local.get(STORAGE_KEY).then((stored) => {
      sendResponse({ ok: true, state: stored[STORAGE_KEY] ?? createInitialState() });
    });
    return true; // async response
  }

  return false;
});
