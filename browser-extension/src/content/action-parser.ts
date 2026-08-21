/**
 * CCB Action parser.
 *
 * Security rules:
 *  - Only `<ccb_action>...</ccb_action>` blocks are considered.
 *  - The block body must be a single JSON object.
 *  - Every field is schema validated; unknown action types are rejected.
 *  - Plain chat text is never interpreted as a command.
 *  - Invalid blocks are ignored (reported as errors, never executed).
 */

import {
  ACTION_TYPES,
  CCB_PROTOCOL_VERSION,
  MEMORY_DOCUMENTS,
  RISK_LEVELS,
  isMemoryAction,
  type ActionPayload,
  type ActionType,
  type CCBAction,
  type MemoryDocumentName,
  type RiskLevel,
} from "../models/action";

const BLOCK_PATTERN = /<ccb_action>([\s\S]*?)<\/ccb_action>/gi;

const MAX_BLOCK_LENGTH = 512 * 1024;
const MAX_REASON_LENGTH = 500;
const MAX_PATH_LENGTH = 1024;
const PROJECT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;
const WORKFLOW_PATTERN = /^wf_[0-9a-f]{12,32}$/;
const STAGE_PATTERN = /^stg_[0-9a-f]{12,32}$/;
const TOOL_ACTIONS = new Set<ActionType>(["git.status", "git.diff", "test.run", "workflow.status"]);

export interface ParseSuccess {
  ok: true;
  action: CCBAction;
  raw: string;
  fingerprint: string;
}

export interface ParseFailure {
  ok: false;
  error: string;
  raw: string;
  fingerprint: string;
}

export type ParseResult = ParseSuccess | ParseFailure;

/** Stable, dependency-free 32-bit hash used to de-duplicate blocks. */
export function fingerprint(input: string): string {
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `ccb_${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" ? value : null;
}

/** Reject traversal, absolute paths and other unsafe relative paths early. */
export function isSafeRelativePath(path: string): boolean {
  if (!path || path.length > MAX_PATH_LENGTH) return false;
  if (path.includes("\0")) return false;
  const normalized = path.replace(/\\/g, "/");
  if (normalized.startsWith("/")) return false;
  if (/^[A-Za-z]:/.test(normalized)) return false;
  return !normalized
    .split("/")
    .some((segment) => segment === ".." || segment.trim() === "..");
}

function validatePayload(
  action: ActionType,
  rawPayload: unknown,
): { ok: true; payload: ActionPayload } | { ok: false; error: string } {
  if (rawPayload !== undefined && !isPlainObject(rawPayload)) {
    return { ok: false, error: "payload must be an object" };
  }
  const source = isPlainObject(rawPayload) ? rawPayload : {};

  if (action === "file.patch") {
    const patch = readString(source, "patch");
    if (!patch || !patch.trim()) {
      return { ok: false, error: "file.patch requires payload.patch" };
    }
    if (!patch.includes("@@")) {
      return { ok: false, error: "payload.patch must be a unified diff" };
    }
    return { ok: true, payload: { patch } };
  }

  if (action === "file.create" || action === "file.write") {
    const content = readString(source, "content");
    if (content === null) {
      return { ok: false, error: `${action} requires payload.content` };
    }
    return { ok: true, payload: { content } };
  }

  if (action === "memory.append") {
    const content = readString(source, "content");
    if (!content || !content.trim()) {
      return { ok: false, error: "memory.append requires payload.content" };
    }
    return { ok: true, payload: { content: content.trim() } };
  }

  if (action === "memory.decision") {
    const adr: ActionPayload = {};
    for (const key of ["title", "context", "decision", "consequence"] as const) {
      const value = readString(source, key);
      if (!value || !value.trim()) {
        return { ok: false, error: `memory.decision requires payload.${key}` };
      }
      adr[key] = value.trim();
    }
    return { ok: true, payload: adr };
  }

  if (action === "test.run") {
    const command = readString(source, "command");
    if (!command || !["pytest", "npm test", "cmake build"].includes(command)) {
      return { ok: false, error: "test.run requires an allowed payload.command" };
    }
    return { ok: true, payload: { command: command as ActionPayload["command"] } };
  }

  if (action === "git.diff") {
    if (source.staged !== undefined && typeof source.staged !== "boolean") {
      return { ok: false, error: "git.diff payload.staged must be boolean" };
    }
    return { ok: true, payload: { staged: source.staged === true } };
  }

  return { ok: true, payload: {} };
}

function validateMemoryTarget(
  target: Record<string, unknown>,
): { ok: true; document: MemoryDocumentName } | { ok: false; error: string } {
  const raw = (readString(target, "document") ?? "").trim().toLowerCase();
  if (!raw) {
    return { ok: false, error: "memory actions require target.document" };
  }
  const normalized = raw.endsWith(".md") ? raw : `${raw}.md`;
  if (!(MEMORY_DOCUMENTS as readonly string[]).includes(normalized)) {
    return { ok: false, error: `unknown memory document: ${raw}` };
  }
  return { ok: true, document: normalized as MemoryDocumentName };
}

/** Validate one already-parsed JSON value against the CCB action schema. */
export function validateAction(
  value: unknown,
): { ok: true; action: CCBAction } | { ok: false; error: string } {
  if (!isPlainObject(value)) {
    return { ok: false, error: "action block must be a JSON object" };
  }

  const version = readString(value, "version");
  if (version !== CCB_PROTOCOL_VERSION) {
    return { ok: false, error: `unsupported protocol version: ${String(value.version)}` };
  }

  const actionName = readString(value, "action");
  if (!actionName || !(ACTION_TYPES as readonly string[]).includes(actionName)) {
    return { ok: false, error: `unsupported action: ${String(value.action)}` };
  }
  const action = actionName as ActionType;

  const target = value.target;
  if (!isPlainObject(target)) {
    return { ok: false, error: "target must be an object" };
  }
  const project = readString(target, "project")?.trim() ?? "";
  if (!PROJECT_PATTERN.test(project)) {
    return { ok: false, error: `invalid project name: ${project || "(empty)"}` };
  }

  let path = readString(target, "path")?.trim() ?? "";
  let document: MemoryDocumentName | undefined;

  if (isMemoryAction(action)) {
    const memoryTarget = validateMemoryTarget(target);
    if (!memoryTarget.ok) return memoryTarget;
    document = memoryTarget.document;
    path = `memory/${document}`;
  } else if (TOOL_ACTIONS.has(action)) {
    path = action.replace(".", "/");
  } else if (!isSafeRelativePath(path)) {
    return { ok: false, error: `unsafe or invalid path: ${path || "(empty)"}` };
  }

  const reason = (readString(value, "reason") ?? "").trim();
  if (!reason) {
    return { ok: false, error: "reason is required" };
  }
  if (reason.length > MAX_REASON_LENGTH) {
    return { ok: false, error: "reason exceeds 500 characters" };
  }

  const riskName = readString(value, "risk");
  if (!riskName || !(RISK_LEVELS as readonly string[]).includes(riskName)) {
    return { ok: false, error: `invalid risk level: ${String(value.risk)}` };
  }
  const risk = riskName as RiskLevel;

  const payloadResult = validatePayload(action, value.payload);
  if (!payloadResult.ok) {
    return payloadResult;
  }

  const workflowId = readString(value, "workflow_id") ?? undefined;
  const stageId = readString(value, "stage_id") ?? undefined;
  if ((workflowId && !WORKFLOW_PATTERN.test(workflowId)) || (stageId && !STAGE_PATTERN.test(stageId))) {
    return { ok: false, error: "invalid workflow_id or stage_id" };
  }
  if (action === "test.run" && (!workflowId || !stageId)) {
    return { ok: false, error: "test.run requires workflow_id and stage_id" };
  }
  if (action === "workflow.status" && !workflowId) {
    return { ok: false, error: "workflow.status requires workflow_id" };
  }

  // The extension never trusts a model-supplied `requiresApproval: false`.
  return {
    ok: true,
    action: {
      version: CCB_PROTOCOL_VERSION,
      action,
      target: document ? { project, path, document } : { project, path },
      reason,
      risk,
      payload: payloadResult.payload,
      workflow_id: workflowId,
      stage_id: stageId,
      requiresApproval: true,
    },
  };
}

/** Extract and validate every CCB action block inside a text chunk. */
export function parseActions(text: string): ParseResult[] {
  if (!text || !text.includes("<ccb_action>")) {
    return [];
  }

  const results: ParseResult[] = [];
  BLOCK_PATTERN.lastIndex = 0;

  let match: RegExpExecArray | null = BLOCK_PATTERN.exec(text);
  while (match !== null) {
    const raw = match[1].trim();
    const id = fingerprint(raw);

    if (!raw) {
      results.push({ ok: false, error: "empty action block", raw, fingerprint: id });
    } else if (raw.length > MAX_BLOCK_LENGTH) {
      results.push({ ok: false, error: "action block too large", raw, fingerprint: id });
    } else {
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        results.push({ ok: false, error: "action block is not valid JSON", raw, fingerprint: id });
        match = BLOCK_PATTERN.exec(text);
        continue;
      }

      const validated = validateAction(parsed);
      if (validated.ok) {
        results.push({ ok: true, action: validated.action, raw, fingerprint: id });
      } else {
        results.push({ ok: false, error: validated.error, raw, fingerprint: id });
      }
    }

    match = BLOCK_PATTERN.exec(text);
  }

  return results;
}
