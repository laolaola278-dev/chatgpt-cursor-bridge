export interface ExecutionTaskRecord {
  id: string;
  workflowId: string | null;
  planId: string | null;
  project: string;
  title: string;
  type: string;
  files: string[];
  dependencies: string[];
  risk: string;
  riskScore: number;
  status: string;
  createdAt: string;
  updatedAt: string;
  verification: Record<string, unknown>;
  readOnly: true;
  proposals?: ExecutionProposalRecord[];
}

export interface ExecutionOperation {
  type: string;
  path: string;
  reason: string;
}

export interface ExecutionProposalRecord {
  id: string;
  taskId: string;
  project: string;
  workflowId: string | null;
  operations: ExecutionOperation[];
  estimatedChanges: number;
  riskScore: number;
  status: string;
  approvalId: string | null;
  createdAt: string;
  readOnly: true;
}

export interface ExecutionResultRecord {
  id: string;
  proposalId: string;
  taskId: string;
  project: string;
  filesChanged: string[];
  diffSummary: Record<string, unknown>;
  durationMs: number;
  errors: string[];
  verification: VerificationReport;
  createdAt: string;
  readOnly: true;
}

export interface VerificationReport {
  status: string;
  checks: string[];
  project: string;
  files: string[];
  snapshotCaptured: boolean;
  approvalVerified: boolean;
  qualityScore: number | null;
  readOnly: true;
  autoFix: false;
}

export interface ExecutionQuality7 {
  quality: number;
  executionReady: boolean;
  blockingIssues: string[];
  implementationConfidence: number;
  executionRisk: number;
  risk: string;
  rollbackReadiness: number;
  verificationConfidence: number;
  readOnly: true;
}

export interface ExecutionTasksResponse { tasks: ExecutionTaskRecord[]; readOnly: true; }
export interface ExecutionProposalsResponse { proposals: ExecutionProposalRecord[]; readOnly: true; }
export interface ExecutionResultsResponse { results: ExecutionResultRecord[]; readOnly: true; }
export interface ExecutionVerifyResponse { executionId: string; status: string; checks: string[]; readOnly: true; }
export interface ExecutionMemoryHistoryResponse { project: string; history: Array<Record<string, unknown>>; readOnly: true; }
