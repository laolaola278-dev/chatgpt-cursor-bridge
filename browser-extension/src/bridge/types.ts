/** Types mirroring the Local Bridge HTTP contract. */

import type { ProjectContextResponse } from "../context/types";
import type { AgentTeamRecord, CollaborationEventRecord, CollaborationEventsResponse, TaskDependenciesResponse, TaskDependencyRecord, TeamListResponse } from "../collaboration/models";
import type { QualityReport, RuntimeEvent, RuntimeEventsResponse, RuntimeRecord, RuntimeStatusResponse, TaskListResponse, TaskRecord } from "../runtime/models";

export type { QualityReport, RuntimeEvent, RuntimeRecord, RuntimeEventsResponse, RuntimeStatusResponse, TaskListResponse, TaskRecord };

export type { ProjectContextResponse, AgentTeamRecord, CollaborationEventRecord, CollaborationEventsResponse, TaskDependenciesResponse, TaskDependencyRecord, TeamListResponse };

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  phase: string;
  workspaceRoot: string;
  logPath: string;
  memoryRoot?: string;
  workflowRoot?: string;
}

export interface ProjectInfo {
  name: string;
  path: string;
}

export interface WorkspaceListResponse {
  projects: ProjectInfo[];
}

export interface AgentRecord {
  id: string;
  project: string;
  sessionId: string;
  role: string;
  modelId: string;
  memoryScope: string;
  permissions: string[];
  status: string;
  workflowId?: string | null;
  stageId?: string | null;
  updatedAt: string;
}

export interface ModelDescriptor {
  id: string;
  provider: string;
  displayName: string;
  capabilities: string[];
  contextWindow: number;
  enabled: boolean;
}

export interface ModelRouteResponse {
  classification: { taskType: string; confidence: number; signals: string[] };
  model: ModelDescriptor;
}

export interface AgentStatusResponse {
  agents: AgentRecord[];
  messages: Array<Record<string, unknown>>;
  models: ModelDescriptor[];
  selectedModel?: ModelRouteResponse | null;
}

export interface FileReadResponse {
  file: string;
  size: number;
  content: string;
}

/** 202 response returned by /file/create, /file/write and /patch/apply. */
export interface ApprovalPendingResponse {
  allowed: false;
  requireApproval: true;
  permissionLevel: string;
  risk: string;
  reason: string;
  status: string;
  requestId: string;
  action: string;
  project: string;
  path: string;
  preview: string;
  createdAt: string;
  expiresAt?: string;
  recoveredAt?: string | null;
  workflowId?: string | null;
  stageId?: string | null;
  sessionId?: string | null;
}

export interface RecoveredApproval {
  requestId: string;
  action: string;
  project: string;
  path: string;
  reason: string;
  preview: string;
  status: "recovered" | "reconfirmed" | "pending" | string;
  createdAt: string;
  expiresAt?: string;
  recoveredAt?: string | null;
  workflowId?: string | null;
  stageId?: string | null;
  sessionId?: string | null;
}

/** 200 response returned by /permission/approve. */
export interface OperationResultResponse {
  allowed: true;
  requireApproval: false;
  permissionLevel: string;
  requestId: string;
  action: string;
  status: string;
  project: string;
  path: string;
  result: Record<string, unknown>;
}

export interface MemoryReadResponse {
  project: string;
  document: string;
  size: number;
  content: string;
}

export interface MemoryDocumentRecord {
  id: string;
  project: string;
  type: string;
  path: string;
  createdAt: string;
  updatedAt: string;
}

export interface MemoryDecisionRecord {
  id: string;
  title: string;
  createdAt: string;
}

export interface PendingApprovalsResponse {
  pending: Array<Record<string, unknown>>;
}

export interface SystemHealthResponse {
  status: "ok" | "degraded";
  service: string;
  version: string;
  phase: string;
  checks: Record<string, { status: string; [key: string]: unknown }>;
  latestBackup?: string | null;
}

export interface MemoryStatusResponse {
  project: string;
  memoryDir: string;
  documents: MemoryDocumentRecord[];
  decisions: MemoryDecisionRecord[];
}

export interface BridgeErrorBody {
  error: string;
  message: string;
}

export type BridgeStatus = "unknown" | "connected" | "offline" | "error";

export class BridgeUnavailableError extends Error {
  readonly code = "bridge_unavailable";

  constructor(message = "Local Bridge unavailable") {
    super(message);
    this.name = "BridgeUnavailableError";
  }
}

export class BridgeRequestError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "BridgeRequestError";
    this.status = status;
    this.code = code;
  }
}

export const DEFAULT_BRIDGE_ORIGIN = "http://127.0.0.1:8765";
