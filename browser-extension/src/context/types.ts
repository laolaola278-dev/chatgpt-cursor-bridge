export interface ContextStage {
  id: string;
  workflowId: string;
  stageType: string;
  status: string;
  reportTitle?: string | null;
  report?: string | null;
  approvalRequestId?: string | null;
  approvedAt?: string | null;
  approvedBy?: string | null;
  actionIds: string[];
  agentIds?: string[];
  qualityGate?: Record<string, unknown> | null;
  createdAt: string;
  updatedAt: string;
}

export interface ContextWorkflow {
  id: string;
  project: string;
  name: string;
  description: string;
  currentStage: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
  cancelledReason?: string | null;
  stages: ContextStage[];
}

export interface ContextTestResult {
  status: string;
  stageId: string;
  report: string;
  updatedAt: string;
}

export interface ProjectContextResponse {
  project: string;
  currentWorkflow: ContextWorkflow | null;
  currentStage: ContextStage | null;
  recentDecisions: Array<Record<string, unknown>>;
  openTasks: string[];
  documents?: Array<Record<string, unknown>>;
  activeSessions?: Array<Record<string, unknown>>;
  summary?: string;
  lastTestResult: ContextTestResult | null;
  gitStatus: Record<string, unknown>;
  pendingApprovals: Array<Record<string, unknown>>;
  recentChanges: Array<Record<string, unknown>>;
  snapshot: { path: string; updatedAt: string };
}

// -- Phase 29 · Advanced Developer Context & Read-only Code Intelligence ---

export interface DevGitContext {
  branch: string;
  clean: boolean;
  changedFiles: string[];
  untracked: string[];
  staged: string[];
  diff: string;
  diffTruncated: boolean;
  commits: Array<{ hash: string; subject: string; author: string; authoredAt: string }>;
  securityFiltered: boolean;
  notAGitRepository?: boolean;
}

export interface DevTestStatus {
  status: string;
  stageId?: string;
  command?: string;
  updatedAt?: string;
  excerpt?: string;
}

export interface DevProjectContext {
  project: string;
  workspaceRoot: string;
  languages: Record<string, number>;
  fileCount: number;
  packageManagers: string[];
  git: DevGitContext;
  testStatus: DevTestStatus | null;
  buildStatus: DevTestStatus | null;
  truncated: boolean;
}

export interface DevSymbol {
  id: string;
  name: string;
  type: string;
  file: string;
  line: number;
  endLine: number;
  signature: string;
  parent: string | null;
  exported: boolean;
}

export interface DevDependency {
  name: string;
  version: string;
  type: string;
  sourceFile: string;
}

export interface DevFileEntry {
  path: string;
  language: string;
  size: number;
}

export interface DevContextResponse {
  source: "context/dev";
  project: string;
  agent: string;
  contextType: string;
  generatedAt: string;
  size: number;
  truncated: boolean;
  securityFiltering: true;
  projectContext?: DevProjectContext;
  files?: DevFileEntry[];
  symbols?: { symbols: DevSymbol[]; total: number; truncated: boolean };
  dependencies?: { dependencies: DevDependency[]; total: number; truncated: boolean };
  git?: DevGitContext;
  tests?: { testStatus: DevTestStatus | null; buildStatus: DevTestStatus | null };
}

export interface DevStatusResponse {
  project: string;
  available: Record<string, boolean>;
  git: { branch: string; clean: boolean };
  testStatus: DevTestStatus | null;
  buildStatus: DevTestStatus | null;
  securityFiltering: true;
}

// -- Phase 30 · Context Intelligence & Developer Workflow Preparation ------

export interface RankedContextItem {
  id: string;
  kind: string;
  path: string;
  name: string;
  score: number;
  reason: string;
  source: string;
  size: number;
  included: boolean;
  exclusion: string;
  truncated: boolean;
  securityFiltered: true;
}

export interface BudgetUsage {
  bucket: string;
  used: number;
  limit: number;
  remaining: number;
  items: number;
}

export interface SuggestedContextResponse {
  source: "context/dev/intelligence";
  project: string;
  agent: string;
  query: string;
  items: RankedContextItem[];
  budget: BudgetUsage[];
  dedup: { totalCandidates: number; unique: number; dropped: number };
  truncated: boolean;
  securityFiltering: true;
  readOnly: true;
}

export interface RelationshipReport {
  source: "context/dev/intelligence";
  project: string;
  target: string;
  imports: Array<{ name: string; kind: string; file: string; line: number; direction: string }>;
  importers: Array<{ name: string; kind: string; file: string; line: number; direction: string }>;
  callers: Array<{ name: string; kind: string; file: string; line: number; direction: string }>;
  callees: Array<{ name: string; kind: string; file: string; line: number; direction: string }>;
  references: Array<{ name: string; kind: string; file: string; line: number; direction: string }>;
  relatedFiles: string[];
  readOnly: true;
  graphNotModified: true;
}

export interface ErrorContextBundle {
  source: "context/dev/intelligence";
  project: string;
  error: string;
  kind: string;
  sourceLocation: { path: string; line: number | null } | null;
  relatedFiles: string[];
  relatedSymbols: Array<Record<string, unknown>>;
  dependencies: Array<Record<string, unknown>>;
  recentDiff: string[];
  relevantTests: string[];
  sanitized: boolean;
  absolutePathsRemoved: boolean;
  secretsRedacted: boolean;
  readOnly: true;
}

export interface TestFailureContext {
  source: "context/dev/intelligence";
  project: string;
  test: string;
  failure: string;
  expected: string;
  actual: string;
  testFile: string | null;
  relatedSource: string[];
  relatedSymbols: Array<Record<string, unknown>>;
  suggestedInvestigation: string[];
  patchProposalOnly: boolean;
  readOnly: true;
}

export interface GitDiffAnalysis {
  source: "context/dev/intelligence";
  project: string;
  changeSummary: string[];
  changedFiles: Array<{ path: string; added: number; removed: number }>;
  changedSymbols: Array<{ name: string; type: string; file: string; line: number }>;
  affectedTests: string[];
  affectedDependencies: string[];
  riskIndicators: Array<{ severity: string; label: string; matches: number }>;
  reviewPoints: string[];
  stats: { files: number; added: number; removed: number; symbols: number; tests: number };
  readOnly: true;
  noGitMutation: true;
}

export interface CodeReviewFinding {
  id: string;
  severity: string;
  category: string;
  location: string;
  title: string;
  explanation: string;
  recommendation: string;
}

export interface CodeReviewResult {
  source: "context/dev/intelligence";
  project: string;
  target: string;
  summary: string;
  findings: CodeReviewFinding[];
  patchProposalOnly: boolean;
  readOnly: true;
}

export interface InjectionReport {
  source: "context/dev/intelligence";
  project: string;
  trusted: string;
  untrusted: string[];
  signals: Array<{ pattern: string; severity: string; snippet: string }>;
  verdict: string;
  readOnly: true;
}

export interface PatchProposalRecord {
  id: string;
  project: string;
  agent: string;
  targetFile: string;
  targetSymbol: string;
  proposedChange: string;
  reason: string;
  expectedImpact: string;
  risk: string;
  status: string;
  applied: boolean;
  approvalRequestId?: string;
  createdAt?: string;
}

export interface Phase30Snapshot {
  source: "context/dev/intelligence";
  project: string;
  suggested: SuggestedContextResponse | null;
  relationships: RelationshipReport | null;
  errorBundle: ErrorContextBundle | null;
  testFailure: TestFailureContext | null;
  gitAnalysis: GitDiffAnalysis | null;
  review: CodeReviewResult | null;
  injection: InjectionReport | null;
  budget: BudgetUsage[];
  proposals: PatchProposalRecord[];
  readOnly: true;
  securityFiltering: true;
}
