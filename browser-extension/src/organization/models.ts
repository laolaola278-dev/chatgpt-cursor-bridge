/** Organization Engineering Intelligence response models (Phase 22). Read-only. */

export interface OrgEntityRecord {
  id: string;
  type: string;
  name: string;
  parentId: string | null;
  metadata: Record<string, unknown>;
  createdAt: string;
  readOnly: true;
}

export interface OrgGraphResponse {
  company: OrgEntityRecord | null;
  teams: OrgEntityRecord[];
  projects: OrgEntityRecord[];
  services: OrgEntityRecord[];
  repositories: OrgEntityRecord[];
  decisions: OrgEntityRecord[];
  incidents: OrgEntityRecord[];
  readOnly: true;
}

export interface OrgIncidentRecord {
  id: string;
  project: string;
  service: string;
  title: string;
  summary: string;
  severity: string;
  signature: string;
  status: string;
  createdAt: string;
  readOnly: true;
}

export interface OrgIncidentsResponse {
  incidents: OrgIncidentRecord[];
  readOnly: true;
}

export interface OrgDecisionRecord {
  id: string;
  project: string;
  title: string;
  context: string;
  decision: string;
  consequence: string;
  status: string;
  createdAt: string;
  readOnly: true;
}

export interface OrgDecisionsResponse {
  decisions: OrgDecisionRecord[];
  readOnly: true;
}

export interface OrgPatternRecord {
  id: string;
  category: string;
  name: string;
  summary: string;
  project: string;
  tags: string[];
  createdAt: string;
  readOnly: true;
}

export interface OrgPatternsResponse {
  patterns: OrgPatternRecord[];
  readOnly: true;
}

export interface OrgHealthByProject {
  project: string;
  healthScore: number;
  riskLevel: "low" | "medium" | "high";
}

export interface OrgDebtRankingEntry {
  project: string;
  openDebt: number;
  estimatedCost: number;
}

export interface OrgRiskTrend {
  project: string;
  healthScore: number;
  delta: number;
  direction: "improving" | "declining" | "stable";
}

export interface OrgFailurePatternEntry {
  project: string;
  category: string;
  signature: string;
  occurrences: number;
  severity: string;
}

export interface OrgAgentEffectiveness {
  agentCount: number;
  completionRate: number;
  averageQuality: number;
  effectivenessScore: number;
}

export interface OrgHealthReport {
  org: string;
  orgHealthScore: number;
  projectCount: number;
  healthByProject: OrgHealthByProject[];
  debtRanking: OrgDebtRankingEntry[];
  riskTrends: OrgRiskTrend[];
  failurePatterns: OrgFailurePatternEntry[];
  agentEffectiveness: OrgAgentEffectiveness[];
  warnings: Array<{ code: string; severity: string; message: string }>;
  recommendations: Array<{ code: string; priority: string; suggestion: string }>;
  createdAt: string;
  readOnly: true;
}

export interface OrgDashboardResponse {
  graph: OrgGraphResponse;
  patterns: OrgPatternRecord[];
  incidents: OrgIncidentRecord[];
  decisions: OrgDecisionRecord[];
  categories: string[];
  readOnly: true;
}

export interface SimilarFailureMatch {
  sourceProject: string;
  targetProject: string;
  category: string;
  signature: string;
  matchScore: number;
  message: string;
  readOnly: true;
}

export interface OrgLearningResponse {
  project: string;
  matches: SimilarFailureMatch[];
  readOnly: true;
}

export interface QualityGate10Response {
  organization: string;
  orgHealthScore: number;
  projectCount: number;
  openIncidents: number;
  criticalProjects: number;
  recommendations: string[];
  blockingIssues: string[];
  quality: number;
  readOnly: true;
}

// --------------------------------------------------------------------------- #
// Phase 24 · Organization Engineering Strategy (read-only)
// --------------------------------------------------------------------------- #

export interface OrgImpactReport {
  id: string;
  source_node: string;
  affected_projects: string[];
  affected_teams: string[];
  affected_services: string[];
  dependency_paths: string[][];
  risk_level: "low" | "medium" | "high";
  impact_score: number;
  confidence: number;
  blocking_issues: string[];
  createdAt: string;
  readOnly: true;
}

export interface OrgRiskPropagationEntry {
  node: string;
  via: string;
  severity: string;
  path: string[];
}

export interface OrgRiskAffectedNode {
  id: string;
  name: string;
  type: string;
  severity: string;
}

export interface OrgRiskReport {
  risk_id: string;
  source: string;
  severity: string;
  likelihood: string;
  propagation_path: OrgRiskPropagationEntry[];
  affected_nodes: OrgRiskAffectedNode[];
  affected_projects: string[];
  affected_teams: string[];
  impact: string;
  confidence: number;
  recommendations: string[];
  readOnly: true;
}

export interface OrgStrategyRecord {
  strategy_id: string;
  strategy_type: string;
  title: string;
  problem: string;
  affected_projects: string[];
  affected_teams: string[];
  benefits: string[];
  risks: string[];
  estimated_effort: string;
  confidence: number;
  priority: string;
  alternatives: string[];
  evidence: string[];
  status: string;
  createdAt: string;
  readOnly: true;
}

export interface OrgStrategyListResponse {
  project: string;
  strategies: OrgStrategyRecord[];
  readOnly: true;
}

export interface OrgRecommendationRecord {
  recommendation_id: string;
  problem: string;
  evidence: string[];
  recommendation: string;
  expected_benefit: string;
  risk: string;
  confidence: number;
  affected_projects: string[];
  affected_teams: string[];
  alternatives: string[];
  readOnly: true;
}

export interface OrgRecommendationsResponse {
  recommendations: OrgRecommendationRecord[];
  readOnly: true;
}

export interface OrgDecisionDetail {
  decision_id: string;
  organization_id: string;
  title: string;
  source_graph_nodes: string[];
  selected_strategy: string;
  alternatives: string[];
  confidence: number;
  impact_report: Record<string, unknown>;
  risk_report: Record<string, unknown>;
  status: string;
  history: Array<{ from: string; to: string; at: string }>;
  createdAt: string;
  readOnly: true;
}

export interface OrgSimulationDetail {
  simulation_id: string;
  strategy_id: string;
  strategy_type: string;
  predictions: Record<string, number | string>;
  createdAt: string;
  readOnly: true;
}

export interface OrgStrategyContext {
  organization: string;
  graph: { nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>>; readOnly: true };
  organization_health: Array<{ project: string; healthScore: number; riskLevel: string }>;
  active_risks: OrgRiskReport[];
  cross_project_impacts: OrgImpactReport[];
  active_strategies: OrgStrategyRecord[];
  pending_decisions: OrgDecisionDetail[];
  technical_debt: Record<string, Array<Record<string, unknown>>>;
  architecture_drift: Record<string, Array<Record<string, unknown>>>;
  recommendations: OrgRecommendationRecord[];
  readOnly: true;
}
