/**
 * DOM Selector Adapter.
 *
 * ChatGPT's markup changes frequently, so every DOM assumption is isolated
 * here. When the page structure changes only this file needs an update.
 *
 * Strategy: try a list of increasingly generic candidate selectors and fall
 * back to structural heuristics instead of hardcoding one brittle path.
 */

/** Candidate containers for the conversation thread, ordered by specificity. */
const CONVERSATION_CANDIDATES: readonly string[] = [
  "main [role='log']",
  "main [class*='conversation']",
  "main [class*='thread']",
  "main",
  "#__next main",
  "body",
];

/** Candidate selectors for a single assistant message node. */
const MESSAGE_CANDIDATES: readonly string[] = [
  "[data-message-author-role='assistant']",
  "[data-message-author-role]",
  "[data-message-id]",
  "article",
  "[class*='markdown']",
];

export interface SelectorAdapter {
  findConversationRoot(doc: Document): Element | null;
  findMessageNodes(root: ParentNode): Element[];
  closestMessageNode(node: Node): Element | null;
  extractText(element: Element): string;
  isChatGPTHost(hostname: string): boolean;
}

const SUPPORTED_HOSTS = ["chatgpt.com", "chat.openai.com"];

function queryFirst(root: ParentNode, candidates: readonly string[]): Element | null {
  for (const selector of candidates) {
    try {
      const found = root.querySelector(selector);
      if (found) return found;
    } catch {
      // Ignore selectors unsupported by the current engine.
    }
  }
  return null;
}

export const defaultSelectorAdapter: SelectorAdapter = {
  isChatGPTHost(hostname: string): boolean {
    const host = hostname.toLowerCase();
    return SUPPORTED_HOSTS.some((base) => host === base || host.endsWith(`.${base}`));
  },

  findConversationRoot(doc: Document): Element | null {
    return queryFirst(doc, CONVERSATION_CANDIDATES);
  },

  findMessageNodes(root: ParentNode): Element[] {
    for (const selector of MESSAGE_CANDIDATES) {
      try {
        const nodes = Array.from(root.querySelectorAll(selector));
        if (nodes.length > 0) return nodes;
      } catch {
        // Ignore and try the next candidate.
      }
    }
    return [];
  },

  closestMessageNode(node: Node): Element | null {
    const start: Element | null =
      node.nodeType === 1 ? (node as Element) : (node.parentElement ?? null);
    if (!start) return null;

    for (const selector of MESSAGE_CANDIDATES) {
      try {
        const found = start.closest(selector);
        if (found) return found;
      } catch {
        // Ignore and try the next candidate.
      }
    }
    return start;
  },

  extractText(element: Element): string {
    return element.textContent ?? "";
  },
};
