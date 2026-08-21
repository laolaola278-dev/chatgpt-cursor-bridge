/**
 * MutationObserver based watcher for the ChatGPT conversation area.
 *
 * The observer only extracts text and hands it to the strict action parser.
 * It never executes anything on its own.
 */

import { defaultSelectorAdapter, type SelectorAdapter } from "./selectors";
import { parseActions, type ParseResult } from "./action-parser";

export interface ObserverOptions {
  adapter?: SelectorAdapter;
  /** Debounce window used while ChatGPT streams tokens. */
  debounceMs?: number;
  onResults: (results: ParseResult[]) => void;
}

export class ConversationObserver {
  private readonly adapter: SelectorAdapter;
  private readonly debounceMs: number;
  private readonly onResults: (results: ParseResult[]) => void;
  private readonly seen = new Set<string>();

  private observer: MutationObserver | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private root: Element | null = null;

  constructor(options: ObserverOptions) {
    this.adapter = options.adapter ?? defaultSelectorAdapter;
    this.debounceMs = options.debounceMs ?? 400;
    this.onResults = options.onResults;
  }

  /** Attach to the conversation root. Returns false when it is not found yet. */
  start(doc: Document = document): boolean {
    const root = this.adapter.findConversationRoot(doc);
    if (!root) return false;

    this.stop();
    this.root = root;
    this.observer = new MutationObserver(() => this.schedule());
    this.observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    // Handle content that already exists when the extension loads.
    this.scan();
    return true;
  }

  stop(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.observer?.disconnect();
    this.observer = null;
    this.root = null;
  }

  get attached(): boolean {
    return this.observer !== null;
  }

  private schedule(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.scan();
    }, this.debounceMs);
  }

  /** Scan the conversation for new, not-yet-seen action blocks. */
  scan(): ParseResult[] {
    if (!this.root) return [];

    const messages = this.adapter.findMessageNodes(this.root);
    const sources = messages.length > 0 ? messages : [this.root];

    const fresh: ParseResult[] = [];
    for (const element of sources) {
      const text = this.adapter.extractText(element);
      if (!text.includes("<ccb_action>")) continue;

      for (const result of parseActions(text)) {
        if (this.seen.has(result.fingerprint)) continue;
        this.seen.add(result.fingerprint);
        fresh.push(result);
      }
    }

    if (fresh.length > 0) {
      this.onResults(fresh);
    }
    return fresh;
  }

  /** Testing/debug helper. */
  reset(): void {
    this.seen.clear();
  }
}
