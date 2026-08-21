export interface BenchmarkRecord {
  id: string;
  project: string;
  repository: string;
  createdAt: string;
  status: string;
  readOnly: true;
}

export interface BenchmarkListResponse {
  benchmarks: BenchmarkRecord[];
  readOnly: true;
}

export interface BenchmarkResultRecord {
  id: string;
  runId: string;
  success: boolean;
  qualityScore: number;
  rollbackTriggered: boolean;
  verificationResult: Record<string, unknown>;
  humanRating: number | null;
  readOnly: true;
}

export interface BenchmarkResultsResponse {
  benchmarkId: string;
  results: BenchmarkResultRecord[];
  readOnly: true;
}

export interface BenchmarkDashboardData {
  benchmarks: BenchmarkRecord[];
  results: BenchmarkResultRecord[];
  failurePatterns: Array<{ category: string; severity: string; occurrences: number }>;
  capabilities: Array<{ agentId: string; successRate: number; averageQuality: number; rollbackRate: number }>;
}
