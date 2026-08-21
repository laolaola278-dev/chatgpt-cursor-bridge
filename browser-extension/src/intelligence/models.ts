export interface EngineeringInsight {
  id: string;
  project: string;
  type: string;
  severity: string;
  title: string;
  location: string;
  evidence: string[];
  suggestion: string;
  createdAt: string;
}

export interface EngineeringProposal {
  id: string;
  project: string;
  insightId: string;
  type: string;
  target: Record<string, string>;
  reason: string[];
  expectedGain: string[];
  risk: string;
  riskScore: number;
  status: string;
  createdAt: string;
}

export interface EngineeringDecision {
  id: string;
  project: string;
  proposalId: string;
  title: string;
  context: string;
  options: Array<{ name: string; risk: string }>;
  recommendation: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  history: Array<{ status: string; at: string }>;
}

export interface IntelligenceQuality5 {
  quality: number;
  risk: string;
  architectureScore: number;
  maintainabilityScore: number;
  riskScore: number;
  decisionConfidence: number;
  technicalDebt: { score: number; items: number };
  recommendations: Array<Record<string, unknown>>;
  readOnly: true;
}

export interface IntelligenceInsightsResponse {
  project: string | null;
  insights: EngineeringInsight[];
  readOnly: true;
}

export interface IntelligenceProposalsResponse {
  project: string | null;
  proposals: EngineeringProposal[];
  readOnly: true;
}

export interface IntelligenceDecisionsResponse {
  project: string;
  decisions: EngineeringDecision[];
  readOnly: true;
}

// ---------------------------------------------------------------------------
// Phase 25 · Engineering Intelligence Evolution (read-only UI contracts)
// ---------------------------------------------------------------------------

export type IntelligenceObservationType =
  | "code_change"
  | "test_result"
  | "build_result"
  | "git_diff"
  | "dependency_change"
  | "error_event"
  | "performance_event"
  | "architecture_event"
  | string;

export interface EngineeringObservation {
  id: string;
  project_id: string;
  projectId?: string;
  timestamp: string;
  type: IntelligenceObservationType;
  source: string;
  summary: string;
  metadata: Record<string, unknown>;
  risk_level: string;
  riskLevel?: string;
  readOnly: true;
}

export interface IntelligencePattern {
  pattern_id: string;
  patternId?: string;
  project_id: string;
  pattern_type: string;
  patternType?: string;
  evidence: string[];
  similar_history: Array<Record<string, unknown>>;
  similarHistory?: Array<Record<string, unknown>>;
  confidence: number;
  summary: string;
  created_at: string;
  createdAt?: string;
  readOnly: true;
}

export interface IntelligencePrediction {
  prediction_id: string;
  predictionId?: string;
  project_id: string;
  prediction_type: string;
  predictionType?: string;
  prediction: string;
  confidence: number;
  evidence: string[];
  observations: string[];
  risk_level: string;
  riskLevel?: string;
  created_at: string;
  createdAt?: string;
  readOnly: true;
}

export interface IntelligenceRecommendation {
  recommendation_id: string;
  recommendationId?: string;
  project_id: string;
  prediction_id: string;
  recommendation: string;
  rationale: string;
  evidence: string[];
  confidence: number;
  risk_level: string;
  readOnly: true;
}

export interface StrategyOutcomeRecord {
  outcome_id: string;
  outcomeId?: string;
  project_id: string;
  strategy_id: string;
  decision_id?: string | null;
  status: "SUCCESS" | "PARTIAL_SUCCESS" | "FAILURE" | "CANCELLED" | string;
  expected_outcome: string;
  actual_outcome: string;
  difference: string;
  evidence: string[];
  source: string;
  confidence: number;
  created_at: string;
  readOnly: true;
}

export interface IntelligenceEvidenceBundle {
  bundle_id: string;
  bundleId?: string;
  project_id: string;
  decision_id?: string | null;
  observation_ids: string[];
  pattern_ids: string[];
  prediction_ids: string[];
  risk_ids: string[];
  strategy_ids: string[];
  recommendation_ids: string[];
  historical_evidence: string[];
  provenance: string[];
  confidence: number;
  created_at: string;
  readOnly: true;
}

export interface IntelligenceKnowledgeRecord {
  id: string;
  project_id: string;
  category: "patterns" | "predictions" | "strategies" | "outcomes" | string;
  content: string;
  source: string;
  evidence: string[];
  confidence: number;
  created_at: string;
  metadata: Record<string, unknown>;
  readOnly: true;
}

export interface IntelligenceQuality11 {
  project?: string;
  gate: "11.0";
  status: "PASS" | "WARN" | "BLOCK" | string;
  quality: number;
  checks: Record<string, boolean | number>;
  observationCount: number;
  patternCount: number;
  predictionCount: number;
  recommendationCount: number;
  decisionCount: number;
  outcomeCount: number;
  knowledgeCount: number;
  blockingIssues: string[];
  warnings: string[];
  readOnly: true;
}

export interface IntelligenceEvolutionResponse {
  project: string;
  observations: EngineeringObservation[];
  patterns: IntelligencePattern[];
  predictions: IntelligencePrediction[];
  recommendations: IntelligenceRecommendation[];
  outcomes: StrategyOutcomeRecord[];
  knowledge: IntelligenceKnowledgeRecord[];
  evidence?: IntelligenceEvidenceBundle[];
  quality: IntelligenceQuality11 | null;
  readOnly: true;
}

export type ObservationRecord = EngineeringObservation;
export type PatternResult = IntelligencePattern;
export type PredictionResult = IntelligencePrediction;
export type RecommendationResult = IntelligenceRecommendation;
export type OutcomeRecord = StrategyOutcomeRecord;

// ---------------------------------------------------------------------------
// Phase 26 · Engineering Intelligence 2.0 (read-only UI contracts)
// ---------------------------------------------------------------------------

export interface EngineeringTrend {
  trend_id: string;
  trendId?: string;
  project_id: string;
  metric: string;
  period: string;
  direction: "increasing" | "decreasing" | "stable" | "volatile" | string;
  change_rate: number;
  changeRate?: number;
  confidence: number;
  evidence: string[];
  sample_count?: number;
  sampleCount?: number;
  confidence_sources?: Record<string, unknown>;
  confidenceSources?: Record<string, unknown>;
  confidence_explanation?: string;
  confidenceExplanation?: string;
  readOnly: true;
}

export interface EngineeringCorrelation {
  correlation_id: string;
  correlationId?: string;
  project_id: string;
  events: string[];
  relationship: string;
  confidence: number;
  evidence: string[];
  interpretation: "correlation_only" | string;
  causation_claim?: false;
  causationClaim?: false;
  readOnly: true;
}

export interface IntelligenceImpactPrediction {
  prediction_id: string;
  predictionId?: string;
  project_id: string;
  affected_files: string[];
  affectedFiles?: string[];
  affected_modules: string[];
  affectedModules?: string[];
  affected_tests: string[];
  affectedTests?: string[];
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  riskLevel?: string;
  confidence: number;
  evidence: string[];
  why_risky: string[];
  whyRisky?: string[];
  confidence_sources?: Record<string, unknown>;
  confidenceSources?: Record<string, unknown>;
  confidence_explanation?: string;
  confidenceExplanation?: string;
  readOnly: true;
}

export interface IntelligenceDependencyRisk {
  risk_id: string;
  riskId?: string;
  project_id: string;
  dependency: string;
  risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  reason: string;
  historical_evidence: string[];
  historicalEvidence?: string[];
  affected_components: string[];
  affectedComponents?: string[];
  confidence: number;
  readOnly: true;
}

export interface PredictionEvaluationRecord {
  evaluation_id: string;
  evaluationId?: string;
  project_id: string;
  prediction_id: string;
  predicted: boolean;
  actual: boolean;
  correct: boolean;
  confidence: number;
  evaluated_at: string;
  evidence: string[];
  readOnly: true;
}

export interface RecommendationEvaluationRecord {
  evaluation_id: string;
  evaluationId?: string;
  project_id: string;
  recommendation_id: string;
  decision: string;
  expected_result: string;
  actual_result: string;
  success: boolean;
  evidence: string[];
  evaluated_at: string;
  readOnly: true;
}

export interface RankedRecommendation {
  recommendation_id: string;
  recommendationId?: string;
  project_id: string;
  rank: number;
  priority: number;
  confidence: number;
  risk_reduction: number;
  riskReduction?: number;
  effort_estimate: string;
  effortEstimate?: string;
  evidence_strength: number;
  evidenceStrength?: number;
  recommendation: string;
  reason: string;
  evidence: string[];
  risk_level: string;
  readOnly: true;
}

export interface RecommendationRanking {
  project_id: string;
  projectId?: string;
  ranked: RankedRecommendation[];
  recommendations?: RankedRecommendation[];
  recommended_action?: string | null;
  recommendedAction?: string | null;
  alternative_actions: string[];
  alternativeActions?: string[];
  reason: string;
  evidence: string[];
  confidence: number;
  humanDecisionRequired?: true;
  readOnly: true;
}

export interface IntelligenceEvaluationMetrics {
  project_id: string;
  predictions: number;
  correct: number;
  incorrect: number;
  accuracy: number;
  precision: number;
  recall: number;
  false_positive_rate: number;
  falsePositiveRate?: number;
  false_negative_rate: number;
  falseNegativeRate?: number;
  recommendation_count: number;
  recommendation_successes: number;
  recommendation_success_rate: number;
  readOnly: true;
}

export interface IntelligenceEvidenceGraphNode {
  node_id: string;
  nodeId?: string;
  node_type: string;
  nodeType?: string;
  project_id: string;
  label: string;
  metadata: Record<string, unknown>;
  readOnly: true;
}

export interface IntelligenceEvidenceGraphEdge {
  edge_id: string;
  edgeId?: string;
  source_id: string;
  sourceId?: string;
  target_id: string;
  targetId?: string;
  relation: string;
  relationship?: string;
  evidence: string[];
  readOnly: true;
}

export interface IntelligenceEvidenceGraph {
  project_id: string;
  nodes: IntelligenceEvidenceGraphNode[];
  edges: IntelligenceEvidenceGraphEdge[];
  nodeCount?: number;
  edgeCount?: number;
  readOnly: true;
}

export interface IntelligencePhase26Response {
  project: string;
  trends: EngineeringTrend[];
  correlations: EngineeringCorrelation[];
  impact: IntelligenceImpactPrediction[];
  dependencies: IntelligenceDependencyRisk[];
  ranking: RecommendationRanking | null;
  evaluations: Array<PredictionEvaluationRecord | RecommendationEvaluationRecord>;
  metrics: IntelligenceEvaluationMetrics | null;
  evidenceGraph: IntelligenceEvidenceGraph | null;
  readOnly: true;
}

// ---------------------------------------------------------------------------
// Phase 27 · Engineering Intelligence Validation Layer (read-only UI contracts)
// ---------------------------------------------------------------------------

export interface ValidationEvaluationRecord {
  evaluation_id: string;
  evaluationId?: string;
  project_id: string;
  projectId?: string;
  prediction_id: string;
  predictionId?: string;
  evaluation_kind: string;
  evaluationKind?: string;
  input_context: string;
  inputContext?: string;
  prediction_result: string;
  predictionResult?: string;
  expected_outcome: string;
  expectedOutcome?: string;
  actual_outcome: string;
  actualOutcome?: string;
  evaluation_result: string;
  evaluationResult?: string;
  correct: boolean;
  confidence: number;
  evaluated_at: string;
  evaluatedAt?: string;
  agent_id?: string;
  agentId?: string;
  model_id?: string;
  modelId?: string;
  decision_id?: string | null;
  decisionId?: string | null;
  recommendation_id?: string | null;
  recommendationId?: string | null;
  evidence: string[];
  readOnly: true;
}

export interface AccuracyCalibrationBin {
  lower: number;
  upper: number;
  count: number;
  correct: number;
  binAccuracy: number;
  binMeanConfidence: number;
}

export interface AccuracyReport {
  projectId: string;
  predictions: number;
  counted: number;
  correct: number;
  incorrect: number;
  partial: number;
  unknown: number;
  accuracy: number;
  precision: number;
  recall: number;
  falsePositive: number;
  falseNegative: number;
  falsePositiveRate: number;
  falseNegativeRate: number;
  successRate: number;
  calibrationError: number;
  calibration: AccuracyCalibrationBin[];
  byKind: Record<string, { counted: number; correct: number; accuracy: number }>;
  filters: Record<string, string>;
  readOnly: true;
}

export interface RecommendationEffectivenessRecord {
  effectiveness_id: string;
  effectivenessId?: string;
  project_id: string;
  recommendation_id: string;
  content: string;
  confidence: number;
  user_decision: "accepted" | "rejected" | "partial" | string;
  actual_result: string;
  effectiveness_score: number;
  classification: "correct" | "incorrect" | "partially_useful" | "rejected" | string;
  failure_reason: string;
  evaluated_at: string;
  readOnly: true;
}

export interface EffectivenessSummary {
  projectId: string;
  total: number;
  correct: number;
  partiallyUseful: number;
  incorrect: number;
  rejected: number;
  effectivenessRate: number;
  meanEffectivenessScore: number;
  readOnly: true;
}

export interface DecisionOutcomeRecord {
  outcome_id: string;
  outcomeId?: string;
  project_id: string;
  decision_id: string;
  decision_type: string;
  title: string;
  expected_outcome: string;
  actual_outcome: string;
  status: "SUCCESS" | "FAILURE" | "PARTIAL" | string;
  evaluated_at: string;
  agent_id?: string;
  model_id?: string;
  readOnly: true;
}

export interface DecisionOutcomeSummary {
  projectId: string;
  total: number;
  byType: Record<string, { total: number; successes: number; successRate: number }>;
  overallSuccessRate: number;
  readOnly: true;
}

export interface BenchmarkCaseRecord {
  case_id: string;
  category: string;
  input: string;
  expected: string;
}

export interface BenchmarkDatasetRecord {
  dataset_id: string;
  name: string;
  project_id: string;
  category: string;
  cases: BenchmarkCaseRecord[];
  readOnly: true;
}

export interface BenchmarkRunRecord {
  benchmark_id: string;
  benchmarkId?: string;
  dataset_id: string;
  dataset_name: string;
  datasetName?: string;
  project_id: string;
  category: string;
  model_id: string;
  score: number;
  accuracy: number;
  determinism_hash: string;
  created_at: string;
  createdAt?: string;
  cases: Array<{ case: BenchmarkCaseRecord; predicted: string; correct: boolean; score: number }>;
  readOnly: true;
}

export interface KnowledgeImprovementRecord {
  improvement_id: string;
  improvementId?: string;
  project_id: string;
  evaluation_id: string;
  prediction_id: string;
  category: string;
  content: string;
  source: string;
  evidence: string[];
  confidence: number;
  status: "proposed" | "validated" | "rejected" | "pending" | "approved" | string;
  created_at: string;
  validated_at?: string;
  approval_request_id?: string;
  readOnly: true;
}

export interface IntelligenceQuality13 {
  project?: string;
  gate: "13.0";
  status: "PASS" | "WARN" | "BLOCK" | string;
  quality: number;
  checks: Record<string, boolean>;
  predictionCount: number;
  evaluationCount: number;
  outcomeCount: number;
  accuracyCount: number;
  effectivenessCount: number;
  benchmarkCount: number;
  improvementCount: number;
  blockingIssues: string[];
  warnings: string[];
  readOnly: true;
}

export interface IntelligencePhase27Response {
  project: string;
  evaluations: ValidationEvaluationRecord[];
  accuracy: AccuracyReport | null;
  failedPredictions: ValidationEvaluationRecord[];
  effectiveness: RecommendationEffectivenessRecord[];
  effectivenessSummary: EffectivenessSummary | null;
  decisionOutcomes: DecisionOutcomeRecord[];
  decisionSummary: DecisionOutcomeSummary | null;
  benchmarks: BenchmarkRunRecord[];
  builtinDatasets: BenchmarkDatasetRecord[];
  improvements: KnowledgeImprovementRecord[];
  quality13: IntelligenceQuality13 | null;
  readOnly: true;
}

// ---------------------------------------------------------------------------
// Phase 28 · Engineering Intelligence Governance Layer (read-only UI contracts)
// ---------------------------------------------------------------------------

export type GovernanceSourceKind =
  | "prediction"
  | "recommendation"
  | "decision"
  | "risk"
  | "model"
  | "context"
  | string;

export interface GovernanceRecord {
  governance_id: string;
  governanceId?: string;
  project_id: string;
  projectId?: string;
  source_kind: GovernanceSourceKind;
  sourceKind?: GovernanceSourceKind;
  source_id: string;
  sourceId?: string;
  agent_id?: string;
  agentId?: string;
  model_id?: string;
  modelId?: string;
  policy_ids: string[];
  policyIds?: string[];
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  riskLevel?: string;
  risk_score: number;
  riskScore?: number;
  confidence: number;
  evaluation_result?: string;
  evaluationResult?: string;
  governance_result: "PASS" | "WARNING" | "REVIEW_REQUIRED" | "BLOCKED" | string;
  governanceResult?: string;
  reason: string;
  evidence: string[];
  created_at: string;
  createdAt?: string;
  audit_request_id?: string;
  auditRequestId?: string;
  readOnly: true;
}

export interface RiskFinding {
  risk_id: string;
  riskId?: string;
  project_id: string;
  source_kind: GovernanceSourceKind;
  source_id: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  riskLevel?: string;
  risk_score: number;
  riskScore?: number;
  confidence: number;
  risk_factors: string[];
  riskFactors?: string[];
  reason: string;
  agent_id?: string;
  model_id?: string;
  similar_cases?: string[];
  created_at: string;
  readOnly: true;
}

export interface GovernancePolicy {
  policy_id: string;
  policyId?: string;
  name: string;
  description: string;
  rule_key: string;
  ruleKey?: string;
  severity: "info" | "warning" | "blocking" | string;
  threshold: number;
  scope: string;
  scope_value: string;
  scopeValue?: string;
  enabled: boolean;
  version: number;
  created_at?: string;
  updated_at?: string;
  readOnly: true;
}

export interface PolicyViolation {
  violation_id: string;
  violationId?: string;
  policy_id: string;
  policyId?: string;
  project_id: string;
  source_id: string;
  source_kind: string;
  severity: string;
  reason: string;
  confidence: number;
  created_at: string;
  readOnly: true;
}

export interface GovernanceReviewProposal {
  proposal_id: string;
  proposalId?: string;
  project_id: string;
  source_id: string;
  source_kind: string;
  risk_level: string;
  riskLevel?: string;
  reason: string;
  recommended_action: string;
  recommendedAction?: string;
  confidence: number;
  evidence: string[];
  status: "proposed" | "approved" | "rejected" | "executed" | string;
  created_at: string;
  resolved_at?: string;
  audit_request_id?: string;
  reviewer_note?: string;
  readOnly: true;
}

export interface GovernanceMemoryRecord {
  memory_id: string;
  memoryId?: string;
  project_id: string;
  category: "finding" | "risk" | "quality" | "policy_violation" | "review" | "history" | string;
  content: string;
  source: string;
  confidence: number;
  evidence: string[];
  created_at: string;
  approval_request_id?: string;
  readOnly: true;
}

export interface GovernanceTrend {
  trend_id: string;
  trendId?: string;
  project_id: string;
  metric: string;
  period: string;
  direction: "improving" | "declining" | "stable" | "increasing" | "decreasing" | string;
  change_rate: number;
  changeRate?: number;
  confidence: number;
  evidence: string[];
  sample_count: number;
  sampleCount?: number;
  readOnly: true;
}

export interface GovernanceSignal {
  signal: string;
  metric: string;
  detail: string;
}

export interface GovernanceGraphNode {
  node_id: string;
  node_type: string;
  project: string;
  label: string;
  readOnly: true;
}

export interface GovernanceGraphEdge {
  edge_id: string;
  source: string;
  target: string;
  relation: string;
  readOnly: true;
}

export interface GovernanceGraph {
  project: string;
  nodes: GovernanceGraphNode[];
  edges: GovernanceGraphEdge[];
  nodeCount: number;
  edgeCount: number;
  readOnly: true;
}

export interface IntelligenceQuality14 {
  project?: string;
  gate: "14.0";
  status: "PASS" | "WARNING" | "REVIEW_REQUIRED" | "BLOCKED" | string;
  quality: number;
  checks: Record<string, boolean>;
  predictionQuality: number | null;
  predictionCount: number;
  evaluationCount: number;
  effectivenessCount: number;
  decisionCount: number;
  maxRiskLevel: string;
  maxRiskScore: number;
  confidenceCalibration: number | null;
  regressionRate: number | null;
  benchmarkScore: number | null;
  benchmarkCount: number;
  violationCount: number;
  blockingIssues: string[];
  warnings: string[];
  readOnly: true;
}

export interface IntelligencePhase28Response {
  project: string;
  records: GovernanceRecord[];
  risks: RiskFinding[];
  violations: PolicyViolation[];
  reviews: GovernanceReviewProposal[];
  memory: GovernanceMemoryRecord[];
  trends: GovernanceTrend[];
  signals: GovernanceSignal[];
  policies: GovernancePolicy[];
  graph: GovernanceGraph;
  quality14: IntelligenceQuality14;
  reviewRequired: boolean;
  readOnly: true;
}
