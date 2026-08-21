export type RuntimeState = "CREATED" | "READY" | "RUNNING" | "WAITING_APPROVAL" | "WAITING_FEEDBACK" | "COMPLETED" | "FAILED" | "RECOVERED";
export type TaskStatus = "PENDING" | "RUNNING" | "WAITING_APPROVAL" | "BLOCKED" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface RuntimeRecord {
  id: string;
  agentId: string;
  sessionId: string;
  workflowId: string;
  stageId: string;
  state: RuntimeState;
  createdAt: string;
  updatedAt: string;
  history: Array<Record<string, string>>;
}

export interface TaskRecord {
  id: string;
  workflowId: string;
  stageId: string;
  agentId: string;
  priority: number;
  status: TaskStatus;
  context: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface RuntimeEvent {
  eventId: string;
  timestamp: string;
  type: string;
  source: string;
  payload: Record<string, unknown>;
  auditId: string;
  checksum: string;
}

export interface QualityReport {
  workflowId: string;
  qualityScore: number;
  risk: string;
  blockingIssues: string[];
  checks: Record<string, unknown>;
}

export interface RuntimeStatusResponse { runtimes: RuntimeRecord[]; states: string[] }
export interface RuntimeEventsResponse { events: RuntimeEvent[] }
export interface TaskListResponse { tasks: TaskRecord[] }
