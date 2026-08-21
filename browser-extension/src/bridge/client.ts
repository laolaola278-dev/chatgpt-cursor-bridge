/**
 * Local Bridge HTTP client.
 *
 * The client never auto-approves anything: write actions only ever create a
 * pending approval request, and execution requires an explicit
 * `/permission/approve` call triggered by the user.
 */

import type { CCBAction } from "../models/action";
import type {
  CodeReviewResult,
  DevContextResponse,
  DevDependency,
  DevFileEntry,
  DevGitContext,
  DevProjectContext,
  DevStatusResponse,
  DevSymbol,
  DevTestStatus,
  ErrorContextBundle,
  GitDiffAnalysis,
  InjectionReport,
  Phase30Snapshot,
  RelationshipReport,
  SuggestedContextResponse,
  TestFailureContext,
} from "../context/types";
import {
  BridgeRequestError,
  BridgeUnavailableError,
  DEFAULT_BRIDGE_ORIGIN,
  type AgentStatusResponse,
  type ApprovalPendingResponse,
  type BridgeErrorBody,
  type FileReadResponse,
  type HealthResponse,
  type MemoryReadResponse,
  type MemoryStatusResponse,
  type OperationResultResponse,
  type PendingApprovalsResponse,
  type RecoveredApproval,
  type SystemHealthResponse,
  type WorkspaceListResponse,
  type RuntimeStatusResponse,
  type RuntimeEventsResponse,
  type TaskListResponse,
  type QualityReport,
} from "./types";
import type { CollaborationEventsResponse, TaskDependenciesResponse, TeamListResponse } from "../collaboration/models";
import type { ImpactReport, ProjectGraphResponse, ProjectMemoryHistoryResponse, ProjectProfile } from "../project-intelligence/models";
import type { IntelligenceDecisionsResponse, IntelligenceInsightsResponse, IntelligenceProposalsResponse, IntelligenceQuality5, EngineeringObservation, IntelligencePattern, IntelligencePrediction, IntelligenceRecommendation, StrategyOutcomeRecord, IntelligenceKnowledgeRecord, IntelligenceEvidenceBundle, IntelligenceQuality11, EngineeringTrend, EngineeringCorrelation, IntelligenceImpactPrediction, IntelligenceDependencyRisk, IntelligenceEvaluationMetrics, PredictionEvaluationRecord, RecommendationEvaluationRecord, RecommendationRanking, IntelligenceEvidenceGraph, AccuracyReport, BenchmarkRunRecord, DecisionOutcomeRecord, EffectivenessSummary, IntelligencePhase27Response, KnowledgeImprovementRecord, RecommendationEffectivenessRecord, IntelligencePhase28Response, RiskFinding, GovernanceReviewProposal, GovernancePolicy, PolicyViolation, GovernanceTrend, GovernanceGraph, IntelligenceQuality14 } from "../intelligence/models";
import type { SimulationEvaluationResponse, SimulationPlansResponse, SimulationRecord, SimulationQuality6, SimulationScenariosResponse } from "../simulation/models";
import type { ExecutionMemoryHistoryResponse, ExecutionProposalsResponse, ExecutionQuality7, ExecutionResultsResponse, ExecutionTasksResponse, ExecutionVerifyResponse } from "../execution/models";
import type { EngineeringMetrics, ExecutionDagListResponse, ExecutionDagReadyResponse, ExecutionDagRecord, ExecutionLoopContext, ExecutionLoopListResponse, ExecutionLoopQuality8Response, ExecutionLoopRecord, ExecutionLoopTimelineResponse } from "../execution-loop/models";
import type { AgentCapabilityMetricsResponse, EngineeringGraphResponse, EvolutionTimelineResponse, FailurePatternsResponse } from "../engineering-graph/models";
import type { BenchmarkListResponse } from "../benchmark/models";
import type { DemoCatalogResponse, DemoFlowResponse } from "../demo/models";
import type {
  GovernanceDebtResponse,
  GovernanceDriftReport,
  GovernanceHealthReport,
  GovernancePoliciesResponse,
  GovernanceQuality9Response,
  GovernanceTimelineResponse,
} from "../governance/models";
import type {
  OrgDashboardResponse,
  OrgDecisionsResponse,
  OrgDecisionDetail,
  OrgGraphResponse,
  OrgHealthReport,
  OrgImpactReport,
  OrgIncidentsResponse,
  OrgLearningResponse,
  OrgPatternsResponse,
  OrgRecommendationsResponse,
  OrgRiskReport,
  OrgSimulationDetail,
  OrgStrategyContext,
  OrgStrategyListResponse,
  OrgStrategyRecord,
  QualityGate10Response,
} from "../organization/models";
import type { ArtifactListResponse } from "../artifacts/models";
import type { LlmChatResult, LlmConversation, LlmConversationMessage, LlmModel, LlmProviderInfo, LlmToolProposal } from "../llm/types";
import type {
  AssistantChatResult,
  AssistantContextStatus,
  AssistantProviderEntry,
  AssistantStreamEvent,
  AssistantUserSettings,
  ProviderTestResult,
  WebContextBundle,
} from "../assistant/types";
import type { ReplayListResponse } from "../replay/models";

export interface BridgeClientOptions {
  origin?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

const DEFAULT_TIMEOUT_MS = 8000;

export class BridgeClient {
  private readonly origin: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: BridgeClientOptions = {}) {
    this.origin = (options.origin ?? DEFAULT_BRIDGE_ORIGIN).replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  get baseUrl(): string {
    return this.origin;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.origin}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          ...(init.headers ?? {}),
        },
      });
    } catch {
      // Connection refused, DNS failure, timeout or blocked request.
      throw new BridgeUnavailableError(
        "Local Bridge unavailable. Start it with: uvicorn app.main:app --port 8765",
      );
    } finally {
      clearTimeout(timer);
    }

    const text = await response.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = null;
      }
    }

    if (!response.ok) {
      const errorBody = (body ?? {}) as Partial<BridgeErrorBody>;
      throw new BridgeRequestError(
        response.status,
        errorBody.error ?? "bridge_error",
        errorBody.message ?? `Bridge returned HTTP ${response.status}`,
      );
    }

    return body as T;
  }

  health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health");
  }

  listProjects(): Promise<WorkspaceListResponse> {
    return this.request<WorkspaceListResponse>("/workspace/list");
  }

  readFile(project: string, path: string): Promise<FileReadResponse> {
    const query = `?project=${encodeURIComponent(project)}&path=${encodeURIComponent(path)}`;
    return this.request<FileReadResponse>(`/file/read${query}`);
  }

  createFile(body: {
    project: string;
    path: string;
    content: string;
    reason: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/file/create", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  writeFile(body: {
    project: string;
    path: string;
    content: string;
    reason: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/file/write", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  applyPatch(body: {
    project: string;
    path: string;
    patch: string;
    reason: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/patch/apply", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  approve(requestId: string): Promise<OperationResultResponse> {
    return this.request<OperationResultResponse>("/permission/approve", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId }),
    });
  }

  reconfirm(requestId: string): Promise<RecoveredApproval> {
    return this.request<RecoveredApproval>("/permission/reconfirm", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId }),
    });
  }

  rejectApproval(requestId: string, reason = "Rejected by user"): Promise<RecoveredApproval> {
    return this.request<RecoveredApproval>("/permission/reject", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, reason }),
    });
  }

  // -- Memory (Phase 3) ------------------------------------------------

  readMemory(project: string, document: string): Promise<MemoryReadResponse> {
    const query = `?project=${encodeURIComponent(project)}&document=${encodeURIComponent(document)}`;
    return this.request<MemoryReadResponse>(`/memory/read${query}`);
  }

  memoryStatus(project: string): Promise<MemoryStatusResponse> {
    return this.request<MemoryStatusResponse>(
      `/memory/status?project=${encodeURIComponent(project)}`,
    );
  }

  gitStatus(project: string): Promise<Record<string, unknown>> {
    return this.request(`/git/status?project=${encodeURIComponent(project)}`);
  }

  gitDiff(project: string, staged = false): Promise<Record<string, unknown>> {
    return this.request(
      `/git/diff?project=${encodeURIComponent(project)}&staged=${String(staged)}`,
    );
  }

  workflowStatus(workflowId: string): Promise<Record<string, unknown>> {
    return this.request(`/workflow/${encodeURIComponent(workflowId)}`);
  }

  systemHealth(): Promise<SystemHealthResponse> {
    return this.request<SystemHealthResponse>("/system/health");
  }

  projectContext(project: string): Promise<import("../context/types").ProjectContextResponse> {
    return this.request(`/context/project?project=${encodeURIComponent(project)}`);
  }

  pendingApprovals(): Promise<PendingApprovalsResponse> {
    return this.request<PendingApprovalsResponse>("/permission/pending");
  }

  contextSearch(query = "", options: { project?: string; from?: string; to?: string } = {}): Promise<Record<string, unknown>> {
    const params = new URLSearchParams({ q: query });
    if (options.project) params.set("project", options.project);
    if (options.from) params.set("from", options.from);
    if (options.to) params.set("to", options.to);
    return this.request(`/context/search?${params.toString()}`);
  }

  sessionList(project?: string): Promise<{ sessions: Array<Record<string, unknown>> }> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request(`/session/list${query}`);
  }

  agentStatus(project?: string, task?: string): Promise<AgentStatusResponse> {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    if (task) params.set("task", task);
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<AgentStatusResponse>(`/agent/status${query}`);
  }

  modelRoute(task: string): Promise<import("./types").ModelRouteResponse> {
    return this.request(`/model-router/route?task=${encodeURIComponent(task)}`);
  }

  runtimeStatus(): Promise<RuntimeStatusResponse> {
    return this.request<RuntimeStatusResponse>("/runtime/status");
  }

  runtimeEvents(limit = 100): Promise<RuntimeEventsResponse> {
    return this.request<RuntimeEventsResponse>(`/runtime/events?limit=${encodeURIComponent(String(limit))}`);
  }

  taskList(status?: string): Promise<TaskListResponse> {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.request<TaskListResponse>(`/task/list${query}`);
  }

  quality(workflowId: string): Promise<QualityReport> {
    return this.request<QualityReport>(`/quality/${encodeURIComponent(workflowId)}`);
  }

  teamList(workflowId?: string): Promise<TeamListResponse> {
    const query = workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : "";
    return this.request<TeamListResponse>(`/team/list${query}`);
  }

  taskDependencies(taskId: string): Promise<TaskDependenciesResponse> {
    return this.request<TaskDependenciesResponse>(`/task/${encodeURIComponent(taskId)}/dependencies`);
  }

  collaborationEvents(limit = 100): Promise<CollaborationEventsResponse> {
    return this.request<CollaborationEventsResponse>(`/collaboration/events?limit=${encodeURIComponent(String(limit))}`);
  }

  projectProfile(project: string): Promise<ProjectProfile> {
    return this.request<ProjectProfile>(`/project/profile?project=${encodeURIComponent(project)}`);
  }

  projectGraph(project: string): Promise<ProjectGraphResponse> {
    return this.request<ProjectGraphResponse>(`/project/graph?project=${encodeURIComponent(project)}`);
  }

  impactAnalysis(project: string, changedFiles: string[] = []): Promise<ImpactReport> {
    const params = new URLSearchParams({ project });
    for (const file of changedFiles) params.append("changed_file", file);
    return this.request<ImpactReport>(`/impact/analyze?${params.toString()}`);
  }

  projectMemoryHistory(project: string): Promise<ProjectMemoryHistoryResponse> {
    return this.request<ProjectMemoryHistoryResponse>(`/memory/project/history?project=${encodeURIComponent(project)}`);
  }

  intelligenceInsights(project?: string): Promise<IntelligenceInsightsResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<IntelligenceInsightsResponse>(`/intelligence/insights${query}`);
  }

  intelligenceProposals(project?: string): Promise<IntelligenceProposalsResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<IntelligenceProposalsResponse>(`/intelligence/proposals${query}`);
  }

  intelligenceDecisions(project: string): Promise<IntelligenceDecisionsResponse> {
    return this.request<IntelligenceDecisionsResponse>(`/intelligence/decisions?project=${encodeURIComponent(project)}`);
  }

  intelligenceQuality(workflowId: string): Promise<IntelligenceQuality5> {
    return this.request<IntelligenceQuality5>(`/quality/v5/${encodeURIComponent(workflowId)}`);
  }

  // -- Phase 25 Engineering Intelligence Evolution (GET only) ----------

  intelligenceObservations(project: string): Promise<{ project: string; observations: EngineeringObservation[]; readOnly: true }> {
    return this.request(`/intelligence/observations?project=${encodeURIComponent(project)}`);
  }

  intelligencePatterns(project: string): Promise<{ project: string; patterns: IntelligencePattern[]; readOnly: true }> {
    return this.request(`/intelligence/patterns?project=${encodeURIComponent(project)}`);
  }

  intelligencePredictions(project: string): Promise<{ project: string; predictions: IntelligencePrediction[]; readOnly: true }> {
    return this.request(`/intelligence/predictions?project=${encodeURIComponent(project)}`);
  }

  intelligenceRecommendations(project: string): Promise<{ project: string; recommendations: IntelligenceRecommendation[]; readOnly: true }> {
    return this.request(`/intelligence/recommendations?project=${encodeURIComponent(project)}`);
  }

  intelligenceOutcomes(project: string): Promise<{ project: string; outcomes: StrategyOutcomeRecord[]; readOnly: true }> {
    return this.request(`/intelligence/outcomes?project=${encodeURIComponent(project)}`);
  }

  intelligenceKnowledge(project: string): Promise<{ project: string; knowledge: IntelligenceKnowledgeRecord[]; readOnly: true }> {
    return this.request(`/intelligence/knowledge?project=${encodeURIComponent(project)}`);
  }

  intelligenceEvidence(project: string): Promise<{ project: string; evidence: IntelligenceEvidenceBundle[]; readOnly: true }> {
    return this.request(`/intelligence/evidence?project=${encodeURIComponent(project)}`);
  }

  intelligenceQuality11(project: string): Promise<IntelligenceQuality11> {
    return this.request(`/intelligence/quality?project=${encodeURIComponent(project)}`);
  }

  // -- Phase 26 Engineering Intelligence 2.0 (GET only) ----------------

  intelligenceTrends(project: string, metric?: string, period = "daily"): Promise<{ project: string; trends: EngineeringTrend[]; readOnly: true }> {
    const params = new URLSearchParams({ project, period });
    if (metric) params.set("metric", metric);
    return this.request(`/intelligence/trends?${params.toString()}`);
  }

  intelligenceCorrelations(project: string): Promise<{ project: string; correlations: EngineeringCorrelation[]; readOnly: true }> {
    return this.request(`/intelligence/correlations?project=${encodeURIComponent(project)}`);
  }

  intelligenceImpact(project: string, changedFiles: string[] = [], changedSymbols: string[] = []): Promise<{ project: string; impact: IntelligenceImpactPrediction[]; predictions: IntelligenceImpactPrediction[]; readOnly: true }> {
    const params = new URLSearchParams({ project });
    for (const file of changedFiles) params.append("changed_file", file);
    for (const symbol of changedSymbols) params.append("changed_symbol", symbol);
    return this.request(`/intelligence/impact?${params.toString()}`);
  }

  intelligenceDependencies(project: string): Promise<{ project: string; dependencies: IntelligenceDependencyRisk[]; risks: IntelligenceDependencyRisk[]; readOnly: true }> {
    return this.request(`/intelligence/dependencies?project=${encodeURIComponent(project)}`);
  }

  intelligenceEvaluations(project: string): Promise<{ project: string; evaluations: Array<PredictionEvaluationRecord | RecommendationEvaluationRecord>; metrics: IntelligenceEvaluationMetrics; readOnly: true }> {
    return this.request(`/intelligence/evaluations?project=${encodeURIComponent(project)}`);
  }

  intelligenceRecommendationRanking(project: string): Promise<RecommendationRanking> {
    return this.request(`/intelligence/recommendations/ranking?project=${encodeURIComponent(project)}`);
  }

  intelligenceEvidenceGraph(project: string): Promise<IntelligenceEvidenceGraph> {
    return this.request(`/intelligence/evidence/graph?project=${encodeURIComponent(project)}`);
  }

  // -- Phase 27 Engineering Intelligence Validation (GET only) ----------

  intelligenceValidation(project: string): Promise<IntelligencePhase27Response> {
    return this.request(`/intelligence/validation?project=${encodeURIComponent(project)}`);
  }

  intelligenceAccuracy(project: string, filters: { agentId?: string; modelId?: string; kind?: string } = {}): Promise<AccuracyReport> {
    const params = new URLSearchParams({ project });
    if (filters.agentId) params.set("agent_id", filters.agentId);
    if (filters.modelId) params.set("model_id", filters.modelId);
    if (filters.kind) params.set("kind", filters.kind);
    return this.request(`/intelligence/accuracy?${params.toString()}`);
  }

  intelligenceEffectiveness(project: string): Promise<{ project: string; effectiveness: RecommendationEffectivenessRecord[]; summary: EffectivenessSummary; readOnly: true }> {
    return this.request(`/intelligence/effectiveness?project=${encodeURIComponent(project)}`);
  }

  intelligenceDecisionOutcomes(project: string): Promise<{ project: string; decisionOutcomes: DecisionOutcomeRecord[]; summary: { overallSuccessRate: number; total: number; byType: Record<string, { total: number; successes: number; successRate: number }> }; readOnly: true }> {
    return this.request(`/intelligence/decision-outcomes?project=${encodeURIComponent(project)}`);
  }

  intelligenceBenchmarks(project: string): Promise<{ project: string; benchmarks: BenchmarkRunRecord[]; datasets: Array<{ dataset_id: string; name: string; cases: unknown[] }>; readOnly: true }> {
    return this.request(`/intelligence/benchmarks?project=${encodeURIComponent(project)}`);
  }

  intelligenceKnowledgeImprovements(project: string, status?: string): Promise<{ project: string; improvements: KnowledgeImprovementRecord[]; readOnly: true }> {
    const params = new URLSearchParams({ project });
    if (status) params.set("status", status);
    return this.request(`/intelligence/knowledge/improvements?${params.toString()}`);
  }

  // -- Phase 28 Engineering Intelligence Governance (GET only) ------------

  intelligenceGovernance(project: string): Promise<IntelligencePhase28Response> {
    return this.request(`/intelligence/governance?project=${encodeURIComponent(project)}`);
  }

  intelligenceGovernanceRisks(project: string, filters: { riskLevel?: string; sourceKind?: string; agentId?: string } = {}): Promise<{ project: string; risks: RiskFinding[]; readOnly: true }> {
    const params = new URLSearchParams({ project });
    if (filters.riskLevel) params.set("risk_level", filters.riskLevel);
    if (filters.sourceKind) params.set("source_kind", filters.sourceKind);
    if (filters.agentId) params.set("agent_id", filters.agentId);
    return this.request(`/intelligence/governance/risk?${params.toString()}`);
  }

  intelligenceGovernanceTrends(project: string, period = "weekly"): Promise<{ project: string; trends: GovernanceTrend[]; signals: Array<{ signal: string; metric: string; detail: string }>; readOnly: true }> {
    const params = new URLSearchParams({ project, period });
    return this.request(`/intelligence/governance/trends?${params.toString()}`);
  }

  intelligenceGovernancePolicies(project: string, scope?: string): Promise<{ project: string; policies: GovernancePolicy[]; readOnly: true }> {
    const params = new URLSearchParams({ project });
    if (scope) params.set("scope", scope);
    return this.request(`/intelligence/governance/policies?${params.toString()}`);
  }

  intelligenceGovernanceViolations(project: string, severity?: string): Promise<{ project: string; violations: PolicyViolation[]; readOnly: true }> {
    const params = new URLSearchParams({ project });
    if (severity) params.set("severity", severity);
    return this.request(`/intelligence/governance/violations?${params.toString()}`);
  }

  intelligenceGovernanceReviews(project: string, status?: string): Promise<{ project: string; reviews: GovernanceReviewProposal[]; readOnly: true }> {
    const params = new URLSearchParams({ project });
    if (status) params.set("status", status);
    return this.request(`/intelligence/governance/reviews?${params.toString()}`);
  }

  intelligenceGovernanceQualityGate(project: string): Promise<IntelligenceQuality14> {
    return this.request(`/intelligence/governance/quality-gate?project=${encodeURIComponent(project)}`);
  }

  intelligenceGovernanceGraph(project: string): Promise<GovernanceGraph> {
    return this.request(`/intelligence/governance/graph?project=${encodeURIComponent(project)}`);
  }

  // -- Phase 29 Advanced Developer Context (GET only) ----------------------

  devContextBundle(project: string, agent = "ASSISTANT"): Promise<DevContextResponse> {
    const params = new URLSearchParams({ project, agent });
    return this.request(`/context/dev/bundle?${params.toString()}`);
  }

  devProjectContext(project: string): Promise<{ source: "context/dev"; project: string; contextType: "project"; securityFiltering: true; data: DevProjectContext }> {
    return this.request(`/context/dev/project?project=${encodeURIComponent(project)}`);
  }

  devFiles(project: string, limit = 200): Promise<{ source: "context/dev"; project: string; contextType: "files"; securityFiltering: true; files: DevFileEntry[]; total: number; truncated: boolean }> {
    return this.request(`/context/dev/files?project=${encodeURIComponent(project)}&limit=${limit}`);
  }

  devFile(project: string, path: string, maxFileKb = 256): Promise<{ source: "context/dev"; project: string; contextType: "file"; securityFiltering: true; data: { path: string; language: string; size: number; lines: number; content: string; truncated: boolean; symbols: DevSymbol[]; imports: string[]; exported: boolean } }> {
    const params = new URLSearchParams({ project, max_file_kb: String(maxFileKb) });
    return this.request(`/context/dev/file/${encodeURIComponent(path)}?${params.toString()}`);
  }

  devSymbols(project: string, q = "", limit = 200): Promise<{ source: "context/dev"; project: string; contextType: "symbols"; securityFiltering: true; data: { symbols: DevSymbol[]; total: number; truncated: boolean } }> {
    const params = new URLSearchParams({ project, limit: String(limit) });
    if (q) params.set("q", q);
    return this.request(`/context/dev/symbols?${params.toString()}`);
  }

  devSymbol(project: string, symbolId: string): Promise<{ source: "context/dev"; project: string; contextType: "symbol"; securityFiltering: true; data: DevSymbol }> {
    return this.request(`/context/dev/symbol/${symbolId}?project=${encodeURIComponent(project)}`);
  }

  devDependencies(project: string, limit = 200): Promise<{ source: "context/dev"; project: string; contextType: "dependencies"; securityFiltering: true; data: { dependencies: DevDependency[]; total: number; truncated: boolean } }> {
    return this.request(`/context/dev/dependencies?project=${encodeURIComponent(project)}&limit=${limit}`);
  }

  devGit(project: string): Promise<{ source: "context/dev"; project: string; contextType: "git"; securityFiltering: true; data: DevGitContext }> {
    return this.request(`/context/dev/git?project=${encodeURIComponent(project)}`);
  }

  devTests(project: string): Promise<{ source: "context/dev"; project: string; contextType: "tests"; securityFiltering: true; data: { testStatus: DevTestStatus | null; buildStatus: DevTestStatus | null } }> {
    return this.request(`/context/dev/tests?project=${encodeURIComponent(project)}`);
  }

  devContextStatus(project: string): Promise<DevStatusResponse> {
    return this.request(`/context/dev/status?project=${encodeURIComponent(project)}`);
  }

  // -- Phase 30 Context Intelligence (GET only) ----------------------------

  contextIntelligenceSuggest(project: string, query = "", options: { agent?: string; selectedPath?: string; selectedText?: string; error?: string; testFailure?: string; limit?: number } = {}): Promise<SuggestedContextResponse> {
    const params = new URLSearchParams({ project });
    if (query) params.set("query", query);
    if (options.agent) params.set("agent", options.agent);
    if (options.selectedPath) params.set("selected_path", options.selectedPath);
    if (options.selectedText) params.set("selected_text", options.selectedText);
    if (options.error) params.set("error", options.error);
    if (options.testFailure) params.set("test_failure", options.testFailure);
    if (options.limit) params.set("limit", String(options.limit));
    return this.request(`/context/dev/intelligence/suggest?${params.toString()}`);
  }

  contextIntelligenceRelationships(project: string, file?: string, symbol?: string): Promise<RelationshipReport> {
    const params = new URLSearchParams({ project });
    if (file) params.set("file", file);
    if (symbol) params.set("symbol", symbol);
    return this.request(`/context/dev/intelligence/relationships?${params.toString()}`);
  }

  contextIntelligenceError(project: string, error: string, options: { stackTrace?: string; testFailure?: string; file?: string } = {}): Promise<ErrorContextBundle> {
    const params = new URLSearchParams({ project, error });
    if (options.stackTrace) params.set("stack_trace", options.stackTrace);
    if (options.testFailure) params.set("test_failure", options.testFailure);
    if (options.file) params.set("file", options.file);
    return this.request(`/context/dev/intelligence/error?${params.toString()}`);
  }

  contextIntelligenceTestFailure(project: string, test: string, options: { failure?: string; expected?: string; actual?: string; traceback?: string } = {}): Promise<TestFailureContext> {
    const params = new URLSearchParams({ project, test });
    if (options.failure) params.set("failure", options.failure);
    if (options.expected) params.set("expected", options.expected);
    if (options.actual) params.set("actual", options.actual);
    if (options.traceback) params.set("traceback", options.traceback);
    return this.request(`/context/dev/intelligence/test-failure?${params.toString()}`);
  }

  contextIntelligenceGit(project: string): Promise<GitDiffAnalysis> {
    return this.request(`/context/dev/intelligence/git?project=${encodeURIComponent(project)}`);
  }

  contextIntelligenceReview(project: string, options: { file?: string; symbol?: string; selection?: string; diff?: string } = {}): Promise<CodeReviewResult> {
    const params = new URLSearchParams({ project });
    if (options.file) params.set("file", options.file);
    if (options.symbol) params.set("symbol", options.symbol);
    if (options.selection) params.set("selection", options.selection);
    if (options.diff) params.set("diff", options.diff);
    return this.request(`/context/dev/intelligence/review?${params.toString()}`);
  }

  contextIntelligenceInjection(project: string, text: string, source = "project_content"): Promise<InjectionReport> {
    const params = new URLSearchParams({ project, text, source });
    return this.request(`/context/dev/intelligence/injection?${params.toString()}`);
  }

  contextIntelligenceBudget(project: string, query = ""): Promise<{ source: "context/dev/intelligence"; project: string; budget: Array<{ bucket: string; used: number; limit: number; remaining: number; items: number }>; dedup: { totalCandidates: number; unique: number; dropped: number }; truncated: boolean; globalLimit: number; readOnly: true }> {
    const params = new URLSearchParams({ project });
    if (query) params.set("query", query);
    return this.request(`/context/dev/intelligence/budget?${params.toString()}`);
  }

  contextIntelligenceSnapshot(project: string): Promise<Phase30Snapshot> {
    return this.request(`/context/dev/intelligence/snapshot?project=${encodeURIComponent(project)}`);
  }

  stagePatchProposal(body: {
    project: string;
    agent?: string;
    target_file: string;
    target_symbol?: string;
    proposed_change: string;
    reason: string;
    expected_impact?: string;
    risk?: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/context/dev/intelligence/patch-proposal", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  // -- Phase 31 LLM Gateway (stateless chat + read-only registry) --------

  llmProviders(): Promise<{ providers: LlmProviderInfo[]; readOnly: true }> {
    return this.request(`/llm/providers`);
  }

  llmModels(provider = ""): Promise<{ models: LlmModel[]; readOnly: true }> {
    const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
    return this.request(`/llm/models${query}`);
  }

  llmConversations(project: string): Promise<{ project: string; conversations: LlmConversation[]; readOnly: true }> {
    return this.request(`/llm/conversations?project=${encodeURIComponent(project)}`);
  }

  llmConversationDetail(conversationId: string, project: string): Promise<{ conversation: LlmConversation; messages: LlmConversationMessage[]; readOnly: true }> {
    return this.request(`/llm/conversations/${encodeURIComponent(conversationId)}?project=${encodeURIComponent(project)}`);
  }

  llmToolProposals(project: string): Promise<{ project: string; proposals: LlmToolProposal[]; readOnly: true }> {
    return this.request(`/llm/tool-proposals?project=${encodeURIComponent(project)}`);
  }

  llmChat(body: {
    project: string;
    messages: Array<{ role: string; content: string; name?: string; tool_calls?: unknown[] }>;
    model?: string;
    provider?: string;
    agent?: string;
    temperature?: number;
    max_tokens?: number;
  }): Promise<LlmChatResult> {
    return this.request<LlmChatResult>("/llm/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  llmConversationCreate(body: {
    project: string;
    provider?: string;
    model?: string;
    title: string;
    agent?: string;
    reason?: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/llm/conversations", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  llmConversationMessage(body: {
    project: string;
    content: string;
    agent?: string;
    model?: string;
    provider?: string;
    reason?: string;
  }, conversationId: string): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>(`/llm/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  llmToolProposal(body: {
    project: string;
    message_id: string;
    tool_name: string;
    arguments?: string;
    reason: string;
  }, conversationId: string): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>(`/llm/conversations/${encodeURIComponent(conversationId)}/tool-proposal`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  // -- Phase 32 AI Assistant (settings, providers, context, chat) ---------
  //
  // `providerConfig` is the only method that carries an API key. The key is a
  // transient argument taken straight from the Settings input: it is posted to
  // the Bridge (which encrypts it with AES-256-GCM), never stored in extension
  // state, never logged and never placed in a URL or query parameter.

  userSettings(): Promise<AssistantUserSettings> {
    return this.request<AssistantUserSettings>("/user/settings");
  }

  providerStatus(): Promise<{ providers: AssistantProviderEntry[]; readOnly: true }> {
    return this.request("/provider/status");
  }

  providerTest(body: { provider: string; model?: string; api_key?: string }): Promise<ProviderTestResult> {
    return this.request<ProviderTestResult>("/provider/test", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Approval-gated: returns a pending request; activation needs a human. */
  providerConfig(body: {
    provider: string;
    model?: string;
    base_url?: string;
    api_key?: string;
    keep_existing_key?: boolean;
    reason?: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/provider/config", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Approval-gated: deletes the stored (encrypted) credential once approved. */
  providerForget(body: { provider: string; reason?: string }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/provider/forget", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Approval-gated: non-sensitive preferences only (mode, provider, model…). */
  userSettingsUpdate(body: {
    mode?: string;
    selected_provider?: string;
    selected_model?: string;
    onboarding_state?: string;
    theme?: string;
    language?: string;
    reason?: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/user/settings", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  contextStatus(project = "", scope: "user" | "developer" = "user"): Promise<AssistantContextStatus> {
    const query = new URLSearchParams();
    if (project) query.set("project", project);
    query.set("scope", scope);
    return this.request<AssistantContextStatus>(`/context/status?${query.toString()}`);
  }

  /**
   * Stateless assistant chat. `web_context` is only ever populated from a
   * bundle the user produced by clicking Ask AI; the Bridge rejects any bundle
   * without that explicit trigger.
   */
  assistantChat(body: {
    project: string;
    messages: Array<{ role: string; content: string }>;
    provider?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number;
    web_context?: WebContextBundle | null;
  }): Promise<AssistantChatResult> {
    return this.request<AssistantChatResult>("/assistant/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /**
   * Streams assistant tokens over SSE. `signal` is the Stop button: aborting
   * ends the stream and never schedules a retry.
   */
  async assistantChatStream(
    body: {
      project: string;
      messages: Array<{ role: string; content: string }>;
      provider?: string;
      model?: string;
      temperature?: number;
      max_tokens?: number;
      web_context?: WebContextBundle | null;
    },
    options: { onEvent: (event: AssistantStreamEvent) => void; signal?: AbortSignal },
  ): Promise<void> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.origin}/assistant/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: options.signal,
      });
    } catch {
      throw new BridgeUnavailableError(
        "Local Bridge unavailable. Start it with: uvicorn app.main:app --port 8765",
      );
    }
    if (!response.ok) {
      // Phase 34 · carry the Bridge's own error code so the panel can name the
      // failure ("LLM provider is not configured" rather than a generic
      // rejection). The body text itself is never displayed: only `code` is
      // read, and the message below is a fixed sentence with a status number.
      let code = "stream_failed";
      try {
        const raw = await response.text();
        const parsed = raw ? (JSON.parse(raw) as Partial<BridgeErrorBody> & { code?: string }) : null;
        const reported = parsed?.error ?? parsed?.code;
        if (typeof reported === "string" && reported) code = reported;
      } catch {
        // An unreadable or non-JSON body leaves the generic code in place.
      }
      throw new BridgeRequestError(response.status, code, `Assistant stream failed (${response.status})`);
    }

    const emit = (frame: string) => {
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          options.onEvent(JSON.parse(payload) as AssistantStreamEvent);
        } catch {
          // A truncated frame is dropped rather than shown as garbage.
        }
      }
    };

    const reader = response.body?.getReader();
    if (!reader) {
      emit(await response.text());
      return;
    }
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) emit(frame);
    }
    if (buffer.trim()) emit(buffer);
  }

  // -- Phase 27 staging helpers (approval-gated POST; never auto-execute) --

  stageEvaluation(body: {
    project_id: string;
    prediction_id: string;
    evaluation_kind: string;
    input_context?: string;
    prediction_result: string;
    expected_outcome: string;
    actual_outcome: string;
    evaluation_result: string;
    confidence?: number;
    agent_id?: string;
    model_id?: string;
    evidence?: string[];
    reason?: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/intelligence/evaluation", { method: "POST", body: JSON.stringify(body) });
  }

  stageBenchmarkRun(body: {
    project_id: string;
    dataset_id: string;
    model_id?: string;
    predictions?: string[];
    reason?: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/intelligence/benchmark/run", { method: "POST", body: JSON.stringify(body) });
  }

  stageKnowledgeImprovement(body: {
    project_id: string;
    evaluation_id: string;
    prediction_id: string;
    category: string;
    content: string;
    source?: string;
    evidence?: string[];
    confidence?: number;
    reason?: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/intelligence/knowledge/improvements/propose", { method: "POST", body: JSON.stringify(body) });
  }

  simulation(simulationId: string): Promise<SimulationRecord> {
    return this.request<SimulationRecord>(`/simulation/${encodeURIComponent(simulationId)}`);
  }

  simulationScenarios(simulationId: string): Promise<SimulationScenariosResponse> {
    return this.request<SimulationScenariosResponse>(`/simulation/${encodeURIComponent(simulationId)}/scenarios`);
  }

  simulationEvaluation(simulationId: string): Promise<SimulationEvaluationResponse> {
    return this.request<SimulationEvaluationResponse>(`/simulation/${encodeURIComponent(simulationId)}/evaluation`);
  }

  simulationPlans(simulationId: string): Promise<SimulationPlansResponse> {
    return this.request<SimulationPlansResponse>(`/simulation/${encodeURIComponent(simulationId)}`).then((result) => ({ simulationId, plans: result.plans ?? [], readOnly: true as const }));
  }

  simulationQuality(workflowId: string): Promise<SimulationQuality6> {
    return this.request<SimulationQuality6>(`/quality/v6/${encodeURIComponent(workflowId)}`);
  }

  planningMemoryHistory(project: string): Promise<{ project: string; history: Array<Record<string, unknown>>; readOnly: true }> {
    return this.request(`/memory/planning/history?project=${encodeURIComponent(project)}`);
  }

  executionTasks(project?: string): Promise<ExecutionTasksResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<ExecutionTasksResponse>(`/execution/tasks${query}`);
  }

  executionProposals(project?: string): Promise<ExecutionProposalsResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<ExecutionProposalsResponse>(`/execution/proposals${query}`);
  }

  executionResults(project?: string): Promise<ExecutionResultsResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<ExecutionResultsResponse>(`/execution/results${query}`);
  }

  executionVerify(executionId: string): Promise<ExecutionVerifyResponse> {
    return this.request<ExecutionVerifyResponse>(`/execution/${encodeURIComponent(executionId)}/verify`);
  }

  executionQuality7(workflowId: string): Promise<ExecutionQuality7> {
    return this.request<ExecutionQuality7>(`/quality/v7/${encodeURIComponent(workflowId)}`);
  }

  executionMemoryHistory(project: string): Promise<ExecutionMemoryHistoryResponse> {
    return this.request<ExecutionMemoryHistoryResponse>(`/memory/execution/history?project=${encodeURIComponent(project)}`);
  }

  executionLoopList(project?: string): Promise<ExecutionLoopListResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<ExecutionLoopListResponse>(`/execution-loop/list${query}`);
  }

  executionDagList(project?: string): Promise<ExecutionDagListResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<ExecutionDagListResponse>(`/execution-dag/list${query}`);
  }

  executionDag(dagId: string): Promise<ExecutionDagRecord> {
    return this.request<ExecutionDagRecord>(`/execution-dag/${encodeURIComponent(dagId)}`);
  }

  executionDagReady(dagId: string): Promise<ExecutionDagReadyResponse> {
    return this.request<ExecutionDagReadyResponse>(`/execution-dag/${encodeURIComponent(dagId)}/ready`);
  }

  engineeringMetrics(project?: string): Promise<EngineeringMetrics> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<EngineeringMetrics>(`/engineering/metrics${query}`);
  }

  executionLoopContext(loopId: string): Promise<ExecutionLoopContext> {
    return this.request<ExecutionLoopContext>(`/execution-loop/${encodeURIComponent(loopId)}/context`);
  }

  engineeringGraph(project: string): Promise<EngineeringGraphResponse> {
    return this.request<EngineeringGraphResponse>(`/engineering-graph/${encodeURIComponent(project)}`);
  }

  failurePatterns(project: string): Promise<FailurePatternsResponse> {
    return this.request<FailurePatternsResponse>(`/failure-intelligence/patterns?project=${encodeURIComponent(project)}`);
  }

  evolutionTimeline(project: string): Promise<EvolutionTimelineResponse> {
    return this.request<EvolutionTimelineResponse>(`/memory/evolution/history?project=${encodeURIComponent(project)}`);
  }

  agentCapabilityMetrics(): Promise<AgentCapabilityMetricsResponse> {
    return this.request<AgentCapabilityMetricsResponse>("/engineering/agent-metrics");
  }

  benchmarkList(project?: string): Promise<BenchmarkListResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<BenchmarkListResponse>(`/benchmark/list${query}`);
  }

  demoCatalog(): Promise<DemoCatalogResponse> {
    return this.request<DemoCatalogResponse>("/demo/catalog");
  }

  demoFlow(): Promise<DemoFlowResponse> {
    return this.request<DemoFlowResponse>("/demo/flow");
  }

  replayList(project?: string): Promise<ReplayListResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<ReplayListResponse>(`/replay/list${query}`);
  }

  artifactList(project?: string): Promise<ArtifactListResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<ArtifactListResponse>(`/artifacts${query}`);
  }

  governanceHealth(project: string): Promise<GovernanceHealthReport> {
    return this.request<GovernanceHealthReport>(`/governance/health/${encodeURIComponent(project)}`);
  }

  governanceDrift(project: string): Promise<GovernanceDriftReport> {
    return this.request<GovernanceDriftReport>(`/governance/drift/${encodeURIComponent(project)}`);
  }

  governanceDebt(project: string, status?: string): Promise<GovernanceDebtResponse> {
    const query = status ? `?status=${encodeURIComponent(status)}` : "";
    return this.request<GovernanceDebtResponse>(`/governance/debt/${encodeURIComponent(project)}${query}`);
  }

  governancePolicies(project?: string): Promise<GovernancePoliciesResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<GovernancePoliciesResponse>(`/governance/policies${query}`);
  }

  governanceTimeline(project: string): Promise<GovernanceTimelineResponse> {
    return this.request<GovernanceTimelineResponse>(`/governance/timeline?project=${encodeURIComponent(project)}`);
  }

  governanceQuality9(workflowId: string): Promise<GovernanceQuality9Response> {
    return this.request<GovernanceQuality9Response>(`/quality/v9/${encodeURIComponent(workflowId)}`);
  }

  organizationGraph(): Promise<OrgGraphResponse> {
    return this.request<OrgGraphResponse>("/organization/graph");
  }

  organizationHealth(): Promise<OrgHealthReport> {
    return this.request<OrgHealthReport>("/organization/health");
  }

  organizationDashboard(): Promise<OrgDashboardResponse> {
    return this.request<OrgDashboardResponse>("/organization/dashboard");
  }

  organizationPatterns(category?: string): Promise<OrgPatternsResponse> {
    const query = category ? `?category=${encodeURIComponent(category)}` : "";
    return this.request<OrgPatternsResponse>(`/organization/patterns${query}`);
  }

  organizationIncidents(project?: string): Promise<OrgIncidentsResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<OrgIncidentsResponse>(`/organization/incidents${query}`);
  }

  organizationDecisions(project?: string): Promise<OrgDecisionsResponse> {
    const query = project ? `?project=${encodeURIComponent(project)}` : "";
    return this.request<OrgDecisionsResponse>(`/organization/decisions${query}`);
  }

  organizationLearningSimilar(project: string, signature?: string, category?: string): Promise<OrgLearningResponse> {
    let query = `project=${encodeURIComponent(project)}`;
    if (signature) query += `&signature=${encodeURIComponent(signature)}`;
    if (category) query += `&category=${encodeURIComponent(category)}`;
    return this.request<OrgLearningResponse>(`/organization/learning/similar?${query}`);
  }

  organizationQuality10(org: string): Promise<QualityGate10Response> {
    return this.request<QualityGate10Response>(`/quality/v10/${encodeURIComponent(org)}`);
  }

  organizationImpact(nodeId: string): Promise<OrgImpactReport> {
    return this.request<OrgImpactReport>(`/organization/impact/${encodeURIComponent(nodeId)}`);
  }

  organizationRisk(nodeId: string, severity = "medium", likelihood = "medium"): Promise<OrgRiskReport> {
    const query = `?severity=${encodeURIComponent(severity)}&likelihood=${encodeURIComponent(likelihood)}`;
    return this.request<OrgRiskReport>(`/organization/risk/${encodeURIComponent(nodeId)}${query}`);
  }

  organizationStrategies(project: string): Promise<OrgStrategyListResponse> {
    return this.request<OrgStrategyListResponse>(`/organization/strategies/${encodeURIComponent(project)}`);
  }

  organizationRecommendations(): Promise<OrgRecommendationsResponse> {
    return this.request<OrgRecommendationsResponse>("/organization/recommendations");
  }

  organizationStrategyDetail(strategyId: string): Promise<OrgStrategyRecord> {
    return this.request<OrgStrategyRecord>(`/organization/strategy/${encodeURIComponent(strategyId)}`);
  }

  organizationDecisionDetail(decisionId: string): Promise<OrgDecisionDetail> {
    return this.request<OrgDecisionDetail>(`/organization/decision/${encodeURIComponent(decisionId)}`);
  }

  organizationSimulationDetail(simulationId: string): Promise<OrgSimulationDetail> {
    return this.request<OrgSimulationDetail>(`/organization/simulation/${encodeURIComponent(simulationId)}`);
  }

  organizationContext(): Promise<OrgStrategyContext> {
    return this.request<OrgStrategyContext>("/organization/context");
  }

  executionLoop(loopId: string): Promise<ExecutionLoopRecord> {
    return this.request<ExecutionLoopRecord>(`/execution-loop/${encodeURIComponent(loopId)}`);
  }

  executionLoopTimeline(loopId: string): Promise<ExecutionLoopTimelineResponse> {
    return this.request<ExecutionLoopTimelineResponse>(`/execution-loop/${encodeURIComponent(loopId)}/timeline`);
  }

  executionLoopQuality8(workflowId: string): Promise<ExecutionLoopQuality8Response> {
    return this.request<ExecutionLoopQuality8Response>(`/quality/v8/${encodeURIComponent(workflowId)}`);
  }

  runTest(body: {
    project: string;
    workflow_id: string;
    stage_id: string;
    command: string;
    reason: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/test/run", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  appendMemory(body: {
    project: string;
    document: string;
    content: string;
    reason: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/memory/append", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  recordDecision(body: {
    project: string;
    title: string;
    context: string;
    decision: string;
    consequence: string;
    reason: string;
  }): Promise<ApprovalPendingResponse> {
    return this.request<ApprovalPendingResponse>("/memory/decision", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /**
   * Stage a mutating action on the Bridge. Returns the pending approval
   * request; nothing is written to disk until `approve()` is called.
   */
  stage(action: CCBAction): Promise<ApprovalPendingResponse> {
    const { project, path } = action.target;
    const reason = action.reason;

    switch (action.action) {
      case "file.create":
        return this.createFile({ project, path, content: action.payload.content ?? "", reason });
      case "file.write":
        return this.writeFile({ project, path, content: action.payload.content ?? "", reason });
      case "file.patch":
        return this.applyPatch({ project, path, patch: action.payload.patch ?? "", reason });
      case "memory.append":
        return this.appendMemory({
          project,
          document: action.target.document ?? "tasks.md",
          content: action.payload.content ?? "",
          reason,
        });
      case "memory.decision":
        return this.recordDecision({
          project,
          title: action.payload.title ?? "",
          context: action.payload.context ?? "",
          decision: action.payload.decision ?? "",
          consequence: action.payload.consequence ?? "",
          reason,
        });
      case "test.run":
        return this.runTest({
          project,
          workflow_id: action.workflow_id ?? "",
          stage_id: action.stage_id ?? "",
          command: action.payload.command ?? "",
          reason,
        });
      default:
        return Promise.reject(
          new BridgeRequestError(400, "unsupported_action", `Cannot stage ${action.action}`),
        );
    }
  }
}
