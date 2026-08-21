/**
 * Phase 32 · Safe Markdown rendering for assistant replies.
 *
 * Supported (spec §10): paragraph, heading, unordered/ordered list, block
 * quote, inline code, fenced code block. Everything else is rendered as plain
 * text — there is no raw-HTML path, no link/image embedding and no script.
 *
 * A fenced code block gets a language label and a Copy button. It never gets a
 * Run / Execute / Terminal / Shell control: the assistant cannot execute code.
 */

export type MarkdownBlockKind = "paragraph" | "heading" | "list" | "quote" | "code";

export interface MarkdownBlock {
  kind: MarkdownBlockKind;
  /** Heading level 1-6, otherwise 0. */
  level: number;
  /** Fenced-code language tag, otherwise "". */
  language: string;
  /** Paragraph/quote text, code body, or one entry per list item. */
  lines: string[];
  ordered: boolean;
}

const HEADING = /^(#{1,6})\s+(.*)$/;
const FENCE = /^```([A-Za-z0-9+#._-]*)\s*$/;
const BULLET = /^[-*+]\s+(.*)$/;
const ORDERED = /^\d{1,3}[.)]\s+(.*)$/;
const QUOTE = /^>\s?(.*)$/;

export function parseMarkdown(source: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = (source ?? "").replace(/\r\n?/g, "\n").split("\n");
  let index = 0;

  const flushParagraph = (buffer: string[]) => {
    if (buffer.length) blocks.push({ kind: "paragraph", level: 0, language: "", lines: [buffer.join(" ")], ordered: false });
    buffer.length = 0;
  };

  const paragraph: string[] = [];
  while (index < lines.length) {
    const line = lines[index];
    const fence = FENCE.exec(line.trim());
    if (fence) {
      flushParagraph(paragraph);
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !FENCE.test(lines[index].trim())) {
        body.push(lines[index]);
        index += 1;
      }
      // An unterminated fence still renders as code; the closing line is dropped.
      index += 1;
      blocks.push({ kind: "code", level: 0, language: fence[1] ?? "", lines: body, ordered: false });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      flushParagraph(paragraph);
      blocks.push({ kind: "heading", level: heading[1].length, language: "", lines: [heading[2].trim()], ordered: false });
      index += 1;
      continue;
    }

    const quote = QUOTE.exec(line);
    if (quote) {
      flushParagraph(paragraph);
      const body: string[] = [quote[1]];
      index += 1;
      while (index < lines.length && QUOTE.test(lines[index])) {
        body.push(QUOTE.exec(lines[index])![1]);
        index += 1;
      }
      blocks.push({ kind: "quote", level: 0, language: "", lines: [body.join(" ")], ordered: false });
      continue;
    }

    const bullet = BULLET.exec(line);
    const ordered = ORDERED.exec(line);
    if (bullet || ordered) {
      flushParagraph(paragraph);
      const isOrdered = Boolean(ordered);
      const items: string[] = [(bullet ?? ordered)![1]];
      index += 1;
      while (index < lines.length) {
        const next = isOrdered ? ORDERED.exec(lines[index]) : BULLET.exec(lines[index]);
        if (!next) break;
        items.push(next[1]);
        index += 1;
      }
      blocks.push({ kind: "list", level: 0, language: "", lines: items, ordered: isOrdered });
      continue;
    }

    if (!line.trim()) {
      flushParagraph(paragraph);
      index += 1;
      continue;
    }

    paragraph.push(line.trim());
    index += 1;
  }
  flushParagraph(paragraph);
  return blocks;
}

export interface MarkdownHandlers {
  /** Receives the code body when Copy is pressed (clipboard fallback). */
  onCopy?: (code: string) => void;
}

/** Append inline text, turning `code` spans into <code> and nothing else. */
export function appendInline(doc: Document, parent: Node, text: string): void {
  const parts = (text ?? "").split("`");
  parts.forEach((part, position) => {
    if (position % 2 === 1 && position < parts.length - 1) {
      const code = doc.createElement("code");
      code.className = "assistant-inline-code";
      code.textContent = part;
      parent.appendChild(code);
      return;
    }
    // An unmatched backtick stays literal instead of swallowing the tail.
    const literal = position % 2 === 1 ? "`" + part : part;
    if (literal) parent.appendChild(doc.createTextNode(literal));
  });
}

function renderCodeBlock(doc: Document, block: MarkdownBlock, handlers: MarkdownHandlers): HTMLElement {
  const wrapper = doc.createElement("div");
  wrapper.className = "assistant-code";
  wrapper.dataset.role = "code-block";

  const head = doc.createElement("div");
  head.className = "assistant-code-head";
  const language = doc.createElement("span");
  language.className = "assistant-code-language";
  language.dataset.role = "code-language";
  language.textContent = block.language || "text";

  const copy = doc.createElement("button");
  copy.className = "assistant-code-copy";
  copy.dataset.role = "copy-code";
  copy.type = "button";
  copy.textContent = "Copy";
  const body = block.lines.join("\n");
  copy.addEventListener("click", () => {
    handlers.onCopy?.(body);
    const clipboard = (globalThis.navigator as { clipboard?: { writeText(value: string): Promise<void> } } | undefined)?.clipboard;
    void clipboard?.writeText(body)?.catch?.(() => {});
    copy.dataset.copied = "true";
    copy.textContent = "Copied";
  });

  head.append(language, copy);
  const pre = doc.createElement("pre");
  pre.className = "assistant-code-body";
  const code = doc.createElement("code");
  code.textContent = body;
  pre.appendChild(code);
  wrapper.append(head, pre);
  return wrapper;
}

/** Render Markdown into a detached element. Never uses innerHTML. */
export function renderMarkdown(doc: Document, source: string, handlers: MarkdownHandlers = {}): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-markdown";
  for (const block of parseMarkdown(source)) {
    if (block.kind === "code") {
      root.appendChild(renderCodeBlock(doc, block, handlers));
      continue;
    }
    if (block.kind === "heading") {
      const heading = doc.createElement(`h${Math.min(Math.max(block.level, 1), 6)}`);
      heading.className = "assistant-heading";
      appendInline(doc, heading, block.lines[0] ?? "");
      root.appendChild(heading);
      continue;
    }
    if (block.kind === "quote") {
      const quote = doc.createElement("blockquote");
      quote.className = "assistant-quote";
      appendInline(doc, quote, block.lines[0] ?? "");
      root.appendChild(quote);
      continue;
    }
    if (block.kind === "list") {
      const list = doc.createElement(block.ordered ? "ol" : "ul");
      list.className = "assistant-list";
      for (const item of block.lines) {
        const entry = doc.createElement("li");
        appendInline(doc, entry, item);
        list.appendChild(entry);
      }
      root.appendChild(list);
      continue;
    }
    const paragraph = doc.createElement("p");
    paragraph.className = "assistant-paragraph";
    appendInline(doc, paragraph, block.lines[0] ?? "");
    root.appendChild(paragraph);
  }
  return root;
}
