export type ExecutionLoopStatus =
  | "CREATED"
  | "PLANNING"
  | "PROPOSAL_READY"
  | "WAITING_APPROVAL"
  | "EXECUTING"
  | "VERIFYING"
  | "COMPLETED"
  | "FAILED"
  | "ROLLED_BACK"
  | "CANCELLED"
  | "RECOVERED";

export interface ExecutionLoopHistoryEntry {
  status: string;
  at: string;
  detail: string;
}

export interface ExecutionLoopQuality8 {
  quality: number;
  executionReady: boolean;
  confidence: number;
  riskLevel: string;
  blockingIssues: string[];
  rollbackCapability: boolean;
  testResult: string | null;
  recommendation: string;
  readOnly: true;
}

export interface ExecutionLoopRecord {
  id: string;
  project: string;
  planId: string;
  workflowId: string | null;
  taskIds: string[];
  proposalId: string | null;
  resultId: string | null;
  approvalId: string | null;
  status: ExecutionLoopStatus;
  verification: Record<string, unknown>;
  quality: ExecutionLoopQuality8 | Record<string, unknown>;
  rollback: Record<string, unknown>;
  memoryProposalId: string | null;
  createdAt: string;
  updatedAt: string;
  history: ExecutionLoopHistoryEntry[];
  readOnly: true;
}

export interface ExecutionLoopListResponse {
  loops: ExecutionLoopRecord[];
  readOnly: true;
}

export interface ExecutionLoopTimelineResponse {
  loopId: string;
  timeline: ExecutionLoopHistoryEntry[];
  readOnly: true;
}

export interface ExecutionLoopQuality8Response {
  workflowId: string;
  quality: number;
  executionReady: boolean;
  confidence: number;
  riskLevel: string;
  blockingIssues: string[];
  rollbackCapability: boolean;
  testResult: string | null;
  recommendation: string;
  readOnly: true;
}

export interface ExecutionDagEdge {
  sourceLoop: string;
  targetLoop: string;
  dependencyType: string;
}

export interface ExecutionDagRecord {
  id: string;
  project: string;
  loopIds: string[];
  edges: ExecutionDagEdge[];
  status: string;
  createdAt: string;
  updatedAt: string;
  history: Array<Record<string, string>>;
  loopStatuses: Record<string, string>;
  readOnly: true;
}

export interface ExecutionDagListResponse {
  dags: ExecutionDagRecord[];
  readOnly: true;
}

export interface ExecutionDagReadyResponse {
  dagId: string;
  readyLoops: string[];
  loopStatuses: Record<string, string>;
  readOnly: true;
}

export interface EngineeringMetrics {
  project: string;
  totalLoops: number;
  statusCounts: Record<string, number>;
  completed: number;
  failed: number;
  rolledBack: number;
  recovered: number;
  cancelled: number;
  successRate: number;
  rollbackRate: number;
  averageQuality: number;
  averageDurationMs: number;
  riskDistribution: Record<string, number>;
  generatedAt: string;
  readOnly: true;
}

export interface ExecutionLoopContext {
  loop: ExecutionLoopRecord;
  tasks: Array<Record<string, unknown>>;
  proposal: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  verification: Record<string, unknown>;
  quality: Record<string, unknown>;
  timeline: ExecutionLoopHistoryEntry[];
  dagRelations: {
    incoming: Array<ExecutionDagEdge & { dagId: string }>;
    outgoing: Array<ExecutionDagEdge & { dagId: string }>;
  };
  relatedLoops: ExecutionLoopRecord[];
  readOnly: true;
}
