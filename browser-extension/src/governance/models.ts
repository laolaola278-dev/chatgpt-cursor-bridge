/** Governance Layer response models (Phase 21). All dashboard reads are read-only. */

export interface GovernanceTrend {
  dimension: string;
  delta: number;
  direction: "improving" | "declining" | "stable";
}

export interface GovernanceWarning {
  code: string;
  severity: string;
  message: string;
}

export interface GovernanceRecommendation {
  code: string;
  priority: string;
  suggestion: string;
}

export interface GovernanceHealthReport {
  project: string;
  healthScore: number;
  riskLevel: "low" | "medium" | "high";
  components: Record<string, number | Record<string, number>>;
  trends: GovernanceTrend[];
  warnings: GovernanceWarning[];
  recommendations: GovernanceRecommendation[];
  createdAt: string;
  readOnly: true;
}

export interface GovernanceDriftIssue {
  type: string;
  severity: string;
  location: string;
  evidence: string[];
  recommendation: string;
}

export interface GovernanceDriftReport {
  project: string;
  driftScore: number;
  riskLevel: "low" | "medium" | "high";
  issues: GovernanceDriftIssue[];
  createdAt: string;
  readOnly: true;
}

export interface GovernanceDebtItem {
  id: string;
  project: string;
  category: string;
  severity: string;
  source: string;
  affectedComponents: string[];
  estimatedCost: number;
  risk: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  readOnly: true;
}

export interface GovernanceDebtResponse {
  project: string;
  debt: GovernanceDebtItem[];
  readOnly: true;
}

export interface GovernancePolicyEvent {
  project: string;
  policy: string;
  result: "pass" | "warning" | "approval_required";
  severity: string;
  message: string;
  context: Record<string, unknown>;
  createdAt: string;
  readOnly: true;
}

export interface GovernancePoliciesResponse {
  policies: string[];
  events: GovernancePolicyEvent[];
  readOnly: true;
}

export interface GovernanceMemoryRecord {
  project: string;
  category: string;
  document: string;
  path: string;
  updatedAt: string;
  size: number;
}

export interface GovernanceTimelineResponse {
  project: string;
  healthSnapshots: Array<Record<string, unknown>>;
  driftSnapshots: Array<Record<string, unknown>>;
  memory: GovernanceMemoryRecord[];
  readOnly: true;
}

export interface GovernanceQuality9Response {
  workflowId: string;
  healthScore: number;
  architectureRisk: "low" | "medium" | "high";
  debtScore: number;
  policyViolations: number;
  recommendations: string[];
  blockingIssues: string[];
  quality: number;
  readOnly: true;
}
