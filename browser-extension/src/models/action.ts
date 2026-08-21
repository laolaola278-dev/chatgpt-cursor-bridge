/**
 * CCB Action protocol model.
 *
 * Only actions that fully satisfy this schema are ever forwarded to the Local
 * Bridge. Anything else is ignored, never executed.
 */

export const CCB_PROTOCOL_VERSION = "1.0";

export const ACTION_TYPES = [
  "file.read",
  "file.create",
  "file.write",
  "file.patch",
  "memory.read",
  "memory.append",
  "memory.decision",
  "git.status",
  "git.diff",
  "test.run",
  "workflow.status",
] as const;

export type ActionType = (typeof ACTION_TYPES)[number];

/** Whitelisted memory documents, mirrored from the Local Bridge. */
export const MEMORY_DOCUMENTS = [
  "project.md",
  "architecture.md",
  "decisions.md",
  "tasks.md",
  "changelog.md",
] as const;

export type MemoryDocumentName = (typeof MEMORY_DOCUMENTS)[number];

export const RISK_LEVELS = ["low", "medium", "high"] as const;

export type RiskLevel = (typeof RISK_LEVELS)[number];

export interface ActionTarget {
  project: string;
  /** Project-relative file path. Empty for memory actions. */
  path: string;
  /** Whitelisted memory document name, for memory.* actions. */
  document?: MemoryDocumentName;
}

export interface ActionPayload {
  /** Full file content for file.create / file.write, or memory.append body. */
  content?: string;
  /** Unified diff for file.patch. */
  patch?: string;
  /** ADR fields for memory.decision. */
  title?: string;
  context?: string;
  decision?: string;
  consequence?: string;
  /** Exact command alias for test.run. */
  command?: "pytest" | "npm test" | "cmake build";
  /** Whether git.diff should show the staged diff. */
  staged?: boolean;
}

export interface CCBAction {
  version: string;
  action: ActionType;
  target: ActionTarget;
  reason: string;
  risk: RiskLevel;
  payload: ActionPayload;
  /** Workflow binding for engineering tool actions. */
  workflow_id?: string;
  stage_id?: string;
  /** Always true in the extension, including read-only tool actions. */
  requiresApproval: boolean;
}

export type ApprovalState =
  | "pending"
  | "approving"
  | "approved"
  | "rejected"
  | "failed";

export interface PendingAction {
  /** Extension-side id, distinct from the Bridge requestId. */
  id: string;
  action: CCBAction;
  state: ApprovalState;
  /** Bridge approval request id, available once the Bridge accepted it. */
  bridgeRequestId?: string;
  /** Diff preview returned by the Bridge. */
  preview?: string;
  message?: string;
  createdAt: string;
  /** Hash of the raw block, used to de-duplicate re-rendered DOM nodes. */
  fingerprint: string;
}

/** Human readable label shown on the approval card. */
export const ACTION_LABELS: Record<ActionType, string> = {
  "file.read": "Read File",
  "file.create": "Create File",
  "file.write": "Modify File",
  "file.patch": "Patch File",
  "memory.read": "Read Memory",
  "memory.append": "Append Memory",
  "memory.decision": "Record Decision (ADR)",
  "git.status": "Git Status",
  "git.diff": "Git Diff",
  "test.run": "Run Tests",
  "workflow.status": "Workflow Status",
};

/** Actions that mutate the workspace/memory and therefore always need approval. */
export const MUTATING_ACTIONS: ReadonlySet<string> = new Set<ActionType>([
  "file.create",
  "file.write",
  "file.patch",
  "memory.append",
  "memory.decision",
  "test.run",
]);

/** Memory actions target a document instead of a project file path. */
export const MEMORY_ACTIONS: ReadonlySet<string> = new Set<ActionType>([
  "memory.read",
  "memory.append",
  "memory.decision",
]);

export function isMemoryAction(action: ActionType): boolean {
  return MEMORY_ACTIONS.has(action);
}

export function isMutatingAction(action: ActionType): boolean {
  return MUTATING_ACTIONS.has(action);
}
