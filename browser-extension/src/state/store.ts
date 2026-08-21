/**
 * Extension state, persisted through chrome.storage.local.
 *
 * Falls back to an in-memory map when the chrome API is unavailable (unit
 * tests, or an unsupported host).
 */

import type { PendingAction } from "../models/action";
import { DEFAULT_BRIDGE_ORIGIN, type AgentRecord, type BridgeStatus, type ModelRouteResponse, type RecoveredApproval } from "../bridge/types";
import type { DevContextResponse, Phase30Snapshot, ProjectContextResponse } from "../context/types";
import type { LlmConversation, LlmModel, LlmProviderInfo, LlmToolProposal } from "../llm/types";
import type {
  AssistantChatTurn,
  AssistantContextStatus,
  AssistantConversationView,
  AssistantProviderEntry,
  AssistantUserSettings,
  OnboardingState,
  ProviderTestResult,
  UiMode,
  WebContextBundle,
} from "../assistant/types";
import { ONBOARDING_STEP_COUNT } from "../assistant/types";
import type { QualityReport, RuntimeEvent, RuntimeRecord, TaskRecord } from "../runtime/models";
import type { AgentTeamRecord, CollaborationEventRecord, TaskDependencyRecord } from "../collaboration/models";
import type { ImpactReport, ProjectGraphResponse, ProjectMemoryHistoryResponse, ProjectProfile } from "../project-intelligence/models";
import type { EngineeringDecision, EngineeringInsight, EngineeringProposal, IntelligenceEvidenceBundle, IntelligenceKnowledgeRecord, IntelligencePattern, IntelligencePrediction, IntelligenceQuality11, IntelligenceQuality5, IntelligenceRecommendation, EngineeringObservation, StrategyOutcomeRecord, EngineeringTrend, EngineeringCorrelation, IntelligenceImpactPrediction, IntelligenceDependencyRisk, IntelligenceEvaluationMetrics, PredictionEvaluationRecord, RecommendationEvaluationRecord, RecommendationRanking, IntelligenceEvidenceGraph, AccuracyReport, BenchmarkRunRecord, DecisionOutcomeRecord, EffectivenessSummary, IntelligencePhase27Response, KnowledgeImprovementRecord, RecommendationEffectivenessRecord, IntelligencePhase28Response } from "../intelligence/models";
import type { EngineeringPlan, SimulationEvaluation, SimulationQuality6, SimulationRecord, SimulationScenario } from "../simulation/models";
import type { ExecutionProposalRecord, ExecutionQuality7, ExecutionResultRecord, ExecutionTaskRecord } from "../execution/models";
import type { EngineeringMetrics, ExecutionDagReadyResponse, ExecutionDagRecord, ExecutionLoopContext, ExecutionLoopHistoryEntry, ExecutionLoopQuality8, ExecutionLoopRecord } from "../execution-loop/models";
import type { AgentCapabilityMetric, EngineeringGraphResponse, EvolutionTimelineEntry, FailurePattern } from "../engineering-graph/models";
import type { BenchmarkRecord } from "../benchmark/models";
import type { DemoScenarioRecord } from "../demo/models";
import type { ArtifactRecord } from "../artifacts/models";
import type { ReplayRecord } from "../replay/models";
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
  OrgGraphResponse,
  OrgHealthReport,
  OrgImpactReport,
  OrgIncidentsResponse,
  OrgLearningResponse,
  OrgPatternsResponse,
  OrgRecommendationsResponse,
  OrgRiskReport,
  OrgStrategyContext,
  OrgStrategyListResponse,
  QualityGate10Response,
} from "../organization/models";

export interface ExtensionLogEntry {
  timestamp: string;
  event: string;
  detail: string;
  approved: boolean;
  result: "pending" | "success" | "rejected" | "failed" | "ignored";
}

export interface ExtensionState {
  bridgeStatus: BridgeStatus;
  bridgeOrigin: string;
  currentProject: string | null;
  /**
   * Phase 32 · which surfaces the panel renders. User Mode is the default and
   * hides every advanced/developer dashboard; Developer Mode adds them back
   * read-only. Hiding UI never removes a backend capability.
   */
  uiMode: UiMode;
  /** Allowed local preference (spec §16). Non-sensitive display state only. */
  onboardingState: string;
  /**
   * Phase 34 · which onboarding step is on screen (0-based). A display cursor:
   * it never unlocks a capability and is clamped to the step list.
   */
  onboardingStep: number;
  /** Allowed local preferences: the selected provider/model names only. */
  assistantProvider: string;
  assistantModel: string;
  assistantSettings: AssistantUserSettings | null;
  assistantProviders: AssistantProviderEntry[];
  assistantProviderTest: ProviderTestResult | null;
  assistantContextStatus: AssistantContextStatus | null;
  /**
   * The Ask AI page snapshot. Transient on purpose: it is never persisted, so a
   * page reload can never resurrect (let alone auto-send) an old bundle.
   */
  assistantWebContext: WebContextBundle | null;
  /** Extension-local chat history. Phase 31 backend storage is untouched. */
  assistantConversations: AssistantConversationView[];
  assistantActiveConversation: string | null;
  assistantStreaming: boolean;
  assistantStatus: string;
  /**
   * Phase 34 · conversation-management display state.
   *
   * `assistantConversationQuery` is the History search text and
   * `assistantRenaming` holds the id whose inline rename box is open. Both are
   * transient: a half-finished rename or a stale filter must never survive a
   * reload, and neither is ever sent to the Bridge.
   */
  assistantConversationQuery: string;
  assistantRenaming: string | null;
  /**
   * Phase 34 · the composer text kept after a **failed** send, so a provider or
   * network error never silently eats what the user typed. Transient, and never
   * a trigger: restoring a draft does not resend anything.
   */
  assistantDraft: string;
  /**
   * Phase 34 · whether the consented Ask AI bundle goes with the next message.
   * Capture never implies send; the user can keep the preview and still opt out.
   */
  assistantContextInclude: boolean;
  pendingActions: PendingAction[];
  lastResult: string | null;
  projectContext: ProjectContextResponse | null;
  devContext: DevContextResponse | null;
  devContextSelection: string[];
  phase30Intelligence: Phase30Snapshot | null;
  llmProviders: LlmProviderInfo[];
  llmModels: LlmModel[];
  llmConversations: LlmConversation[];
  llmToolProposals: LlmToolProposal[];
  recoveredApprovals: RecoveredApproval[];
  sessions: Array<Record<string, unknown>>;
  agents: AgentRecord[];
  modelSelection: ModelRouteResponse | null;
  runtimes: RuntimeRecord[];
  tasks: TaskRecord[];
  runtimeEvents: RuntimeEvent[];
  qualityReport: QualityReport | null;
  teams: AgentTeamRecord[];
  dependencies: TaskDependencyRecord[];
  collaborationEvents: CollaborationEventRecord[];
  projectProfile: ProjectProfile | null;
  projectGraph: ProjectGraphResponse | null;
  impactReport: ImpactReport | null;
  projectMemoryHistory: ProjectMemoryHistoryResponse | null;
  intelligenceInsights: EngineeringInsight[];
  intelligenceProposals: EngineeringProposal[];
  intelligenceDecisions: EngineeringDecision[];
  intelligenceQuality: IntelligenceQuality5 | null;
  intelligenceObservations: EngineeringObservation[];
  intelligencePatterns: IntelligencePattern[];
  intelligencePredictions: IntelligencePrediction[];
  intelligenceRecommendations: IntelligenceRecommendation[];
  intelligenceOutcomes: StrategyOutcomeRecord[];
  intelligenceKnowledge: IntelligenceKnowledgeRecord[];
  intelligenceEvidence: IntelligenceEvidenceBundle[];
  intelligenceQuality11: IntelligenceQuality11 | null;
  intelligenceTrends: EngineeringTrend[];
  intelligenceCorrelations: EngineeringCorrelation[];
  intelligenceImpactPredictions: IntelligenceImpactPrediction[];
  intelligenceDependencyRisks: IntelligenceDependencyRisk[];
  intelligenceEvaluations: Array<PredictionEvaluationRecord | RecommendationEvaluationRecord>;
  intelligenceEvaluationMetrics: IntelligenceEvaluationMetrics | null;
  intelligenceRecommendationRanking: RecommendationRanking | null;
  intelligenceEvidenceGraph: IntelligenceEvidenceGraph | null;
  intelligenceValidation: IntelligencePhase27Response | null;
  intelligenceAccuracy: AccuracyReport | null;
  intelligenceEffectiveness: RecommendationEffectivenessRecord[];
  intelligenceEffectivenessSummary: EffectivenessSummary | null;
  intelligenceDecisionOutcomes: DecisionOutcomeRecord[];
  intelligenceDecisionSummary: { overallSuccessRate: number; total: number; byType: Record<string, { total: number; successes: number; successRate: number }> } | null;
  intelligenceBenchmarks: BenchmarkRunRecord[];
  intelligenceImprovements: KnowledgeImprovementRecord[];
  intelligenceGovernance: IntelligencePhase28Response | null;
  simulation: SimulationRecord | null;
  simulationScenarios: SimulationScenario[];
  simulationEvaluations: SimulationEvaluation[];
  simulationPlans: EngineeringPlan[];
  simulationQuality: SimulationQuality6 | null;
  planningMemoryHistory: { project: string; history: Array<Record<string, unknown>>; readOnly: true } | null;
  executionTasks: ExecutionTaskRecord[];
  executionProposals: ExecutionProposalRecord[];
  executionResults: ExecutionResultRecord[];
  executionQuality7: ExecutionQuality7 | null;
  executionMemoryHistory: { project: string; history: Array<Record<string, unknown>>; readOnly: true } | null;
  executionLoops: ExecutionLoopRecord[];
  executionLoopTimeline: ExecutionLoopHistoryEntry[];
  executionLoopQuality8: ExecutionLoopQuality8 | null;
  executionDags: ExecutionDagRecord[];
  executionDagReady: ExecutionDagReadyResponse | null;
  engineeringMetrics: EngineeringMetrics | null;
  executionLoopContext: ExecutionLoopContext | null;
  engineeringGraph: EngineeringGraphResponse | null;
  failurePatterns: FailurePattern[];
  evolutionTimeline: EvolutionTimelineEntry[];
  agentCapabilityMetrics: AgentCapabilityMetric[];
  benchmarks: BenchmarkRecord[];
  demoScenarios: DemoScenarioRecord[];
  demoFlow: string[];
  replays: ReplayRecord[];
  artifacts: ArtifactRecord[];
  governanceHealth: GovernanceHealthReport | null;
  governanceDrift: GovernanceDriftReport | null;
  governanceDebt: GovernanceDebtResponse | null;
  governancePolicies: GovernancePoliciesResponse | null;
  governanceTimeline: GovernanceTimelineResponse | null;
  governanceQuality9: GovernanceQuality9Response | null;
  organizationGraph: OrgGraphResponse | null;
  organizationHealth: OrgHealthReport | null;
  organizationDashboard: OrgDashboardResponse | null;
  organizationPatterns: OrgPatternsResponse | null;
  organizationIncidents: OrgIncidentsResponse | null;
  organizationLearning: OrgLearningResponse | null;
  organizationQuality10: QualityGate10Response | null;
  organizationStrategyImpact: OrgImpactReport | null;
  organizationStrategyRisk: OrgRiskReport | null;
  organizationStrategies: OrgStrategyListResponse | null;
  organizationRecommendations: OrgRecommendationsResponse | null;
  organizationStrategyContext: OrgStrategyContext | null;
  lastContextRefresh: string | null;
  log: ExtensionLogEntry[];
}

export const STORAGE_KEY = "ccb_state_v1";
const MAX_LOG_ENTRIES = 200;
export const MAX_ASSISTANT_CONVERSATIONS = 20;
export const MAX_CONVERSATION_TITLE = 80;

/** A rename is display text: one line, bounded, no control characters. */
export function sanitizeConversationTitle(title: string): string {
  return title.replace(/[\r\n\t]+/g, " ").replace(/\s+/g, " ").trim().slice(0, MAX_CONVERSATION_TITLE);
}

/**
 * Keep the local list bounded, dropping the oldest **unpinned** entries first.
 * Pinning is the user saying "keep this one visible", so capping honours it.
 */
export function capConversations(list: AssistantConversationView[]): AssistantConversationView[] {
  if (list.length <= MAX_ASSISTANT_CONVERSATIONS) return list;
  const overflow = list.length - MAX_ASSISTANT_CONVERSATIONS;
  const dropped = new Set<string>();
  for (const item of list) {
    if (dropped.size >= overflow) break;
    if (!item.pinned) dropped.add(item.id);
  }
  for (const item of list) {
    if (dropped.size >= overflow) break;
    dropped.add(item.id);
  }
  return list.filter((item) => !dropped.has(item.id));
}

/**
 * Phase 34 · the History list as it is shown: newest first, pinned on top, and
 * filtered by the search box.
 *
 * A pure function over the local list. Searching and pinning are *display*
 * operations — nothing here removes a conversation, calls the Bridge or issues
 * an LLM request, so a filter that matches nothing hides rows without ever
 * destroying them.
 */
export function visibleAssistantConversations(
  list: AssistantConversationView[],
  query = "",
): AssistantConversationView[] {
  const needle = query.trim().toLowerCase();
  const matches = needle
    ? list.filter((item) => {
        if (item.title.toLowerCase().includes(needle)) return true;
        return item.turns.some((turn) => turn.content.toLowerCase().includes(needle));
      })
    : [...list];
  // `reverse()` keeps the Phase 32 newest-first order; pinning only lifts rows.
  matches.reverse();
  const pinned = matches.filter((item) => item.pinned);
  const rest = matches.filter((item) => !item.pinned);
  return [...pinned, ...rest];
}

/**
 * Phase 32 · state keys that may never be written or persisted.
 *
 * The API key travels `Settings input → Bridge → AES-256-GCM → encrypted
 * store`. Nothing key-shaped is allowed into `ExtensionState`, so nothing
 * key-shaped can reach `chrome.storage.local`. Any patch key matching one of
 * these fragments is dropped by `update()`.
 */
export const FORBIDDEN_STATE_KEY_FRAGMENTS = [
  "apikey",
  "api_key",
  "secret",
  "authorization",
  "credential",
  "bearer",
  "token",
  "password",
] as const;

/** Never written to storage: display-only, and unsafe to resurrect on reload. */
export const TRANSIENT_STATE_KEYS = [
  "assistantWebContext",
  "assistantProviderTest",
  "assistantStreaming",
  "assistantConversationQuery",
  "assistantRenaming",
  "assistantContextInclude",
  "assistantDraft",
] as const;

export function isForbiddenStateKey(key: string): boolean {
  const normalized = key.toLowerCase();
  return FORBIDDEN_STATE_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment));
}

/** Drop every credential-shaped key from a state patch or a stored blob. */
export function stripForbiddenKeys<T extends Record<string, unknown>>(value: T): T {
  const clean: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (isForbiddenStateKey(key)) continue;
    clean[key] = entry;
  }
  return clean as T;
}

export function createInitialState(): ExtensionState {
  return {
    bridgeStatus: "unknown",
    bridgeOrigin: DEFAULT_BRIDGE_ORIGIN,
    currentProject: null,
    uiMode: "user",
    onboardingState: "new",
    onboardingStep: 0,
    assistantProvider: "local",
    assistantModel: "",
    assistantSettings: null,
    assistantProviders: [],
    assistantProviderTest: null,
    assistantContextStatus: null,
    assistantWebContext: null,
    assistantConversations: [],
    assistantActiveConversation: null,
    assistantStreaming: false,
    assistantStatus: "",
    assistantConversationQuery: "",
    assistantRenaming: null,
    assistantContextInclude: true,
    assistantDraft: "",
    pendingActions: [],
    lastResult: null,
    projectContext: null,
    devContext: null,
    devContextSelection: [],
    phase30Intelligence: null,
    llmProviders: [],
    llmModels: [],
    llmConversations: [],
    llmToolProposals: [],
    recoveredApprovals: [],
    sessions: [],
    agents: [],
    modelSelection: null,
    runtimes: [],
    tasks: [],
    runtimeEvents: [],
    qualityReport: null,
    teams: [],
    dependencies: [],
    collaborationEvents: [],
    projectProfile: null,
    projectGraph: null,
    impactReport: null,
    projectMemoryHistory: null,
    intelligenceInsights: [],
    intelligenceProposals: [],
    intelligenceDecisions: [],
    intelligenceQuality: null,
    intelligenceObservations: [],
    intelligencePatterns: [],
    intelligencePredictions: [],
    intelligenceRecommendations: [],
    intelligenceOutcomes: [],
    intelligenceKnowledge: [],
    intelligenceEvidence: [],
    intelligenceQuality11: null,
    intelligenceTrends: [],
    intelligenceCorrelations: [],
    intelligenceImpactPredictions: [],
    intelligenceDependencyRisks: [],
    intelligenceEvaluations: [],
    intelligenceEvaluationMetrics: null,
    intelligenceRecommendationRanking: null,
    intelligenceEvidenceGraph: null,
    intelligenceValidation: null,
    intelligenceAccuracy: null,
    intelligenceEffectiveness: [],
    intelligenceEffectivenessSummary: null,
    intelligenceDecisionOutcomes: [],
    intelligenceDecisionSummary: null,
    intelligenceBenchmarks: [],
    intelligenceImprovements: [],
    intelligenceGovernance: null,
    simulation: null,
    simulationScenarios: [],
    simulationEvaluations: [],
    simulationPlans: [],
    simulationQuality: null,
    planningMemoryHistory: null,
    executionTasks: [],
    executionProposals: [],
    executionResults: [],
    executionQuality7: null,
    executionMemoryHistory: null,
    executionLoops: [],
    executionLoopTimeline: [],
    executionLoopQuality8: null,
    executionDags: [],
    executionDagReady: null,
    engineeringMetrics: null,
    executionLoopContext: null,
    engineeringGraph: null,
    failurePatterns: [],
    evolutionTimeline: [],
    agentCapabilityMetrics: [],
    benchmarks: [],
    demoScenarios: [],
    demoFlow: [],
    replays: [],
    artifacts: [],
    governanceHealth: null,
    governanceDrift: null,
    governanceDebt: null,
    governancePolicies: null,
    governanceTimeline: null,
    governanceQuality9: null,
    organizationGraph: null,
    organizationHealth: null,
    organizationDashboard: null,
    organizationPatterns: null,
    organizationIncidents: null,
    organizationLearning: null,
    organizationQuality10: null,
    organizationStrategyImpact: null,
    organizationStrategyRisk: null,
    organizationStrategies: null,
    organizationRecommendations: null,
    organizationStrategyContext: null,
    lastContextRefresh: null,
    log: [],
  };
}

interface StorageLike {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

function memoryStorage(): StorageLike {
  const data = new Map<string, unknown>();
  return {
    async get(key) {
      return data.has(key) ? { [key]: data.get(key) } : {};
    },
    async set(items) {
      for (const [key, value] of Object.entries(items)) data.set(key, value);
    },
  };
}

function resolveStorage(): StorageLike {
  const api = (globalThis as { chrome?: { storage?: { local?: StorageLike } } }).chrome;
  const local = api?.storage?.local;
  if (!local) return memoryStorage();
  return {
    get: (key) => Promise.resolve(local.get(key)),
    set: (items) => Promise.resolve(local.set(items)),
  };
}

type Listener = (state: ExtensionState) => void;

export class ExtensionStore {
  private state: ExtensionState = createInitialState();
  private readonly listeners = new Set<Listener>();
  private readonly storage: StorageLike;

  constructor(storage: StorageLike = resolveStorage()) {
    this.storage = storage;
  }

  getState(): ExtensionState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  async hydrate(): Promise<ExtensionState> {
    try {
      const stored = await this.storage.get(STORAGE_KEY);
      const value = stored[STORAGE_KEY];
      if (value && typeof value === "object") {
        // A blob written by an older build (or tampered with) is filtered the
        // same way a live patch is: no credential-shaped key survives.
        this.state = {
          ...createInitialState(),
          ...stripForbiddenKeys(value as Record<string, unknown>),
        } as ExtensionState;
      }
    } catch {
      this.state = createInitialState();
    }
    this.emit();
    return this.state;
  }

  private emit(): void {
    for (const listener of this.listeners) listener(this.state);
  }

  private async persist(): Promise<void> {
    try {
      const snapshot: Record<string, unknown> = { ...this.state };
      for (const key of TRANSIENT_STATE_KEYS) delete snapshot[key];
      await this.storage.set({ [STORAGE_KEY]: snapshot });
    } catch {
      // Storage quota or missing permission: keep working in memory.
    }
  }

  async update(patch: Partial<ExtensionState>): Promise<ExtensionState> {
    this.state = { ...this.state, ...stripForbiddenKeys(patch as Record<string, unknown>) };
    this.emit();
    await this.persist();
    return this.state;
  }

  setBridgeStatus(status: BridgeStatus): Promise<ExtensionState> {
    return this.update({ bridgeStatus: status });
  }

  setProject(project: string | null): Promise<ExtensionState> {
    return this.update({ currentProject: project });
  }

  toggleDevContextSelection(id: string): Promise<ExtensionState> {
    const selection = this.state.devContextSelection.includes(id)
      ? this.state.devContextSelection.filter((item) => item !== id)
      : [...this.state.devContextSelection, id];
    return this.update({ devContextSelection: selection });
  }

  clearDevContextSelection(): Promise<ExtensionState> {
    return this.update({ devContextSelection: [] });
  }

  addPending(action: PendingAction): Promise<ExtensionState> {
    const exists = this.state.pendingActions.some(
      (item) => item.fingerprint === action.fingerprint,
    );
    if (exists) return Promise.resolve(this.state);
    return this.update({ pendingActions: [...this.state.pendingActions, action] });
  }

  patchPending(id: string, patch: Partial<PendingAction>): Promise<ExtensionState> {
    return this.update({
      pendingActions: this.state.pendingActions.map((item) =>
        item.id === id ? { ...item, ...patch } : item,
      ),
    });
  }

  removePending(id: string): Promise<ExtensionState> {
    return this.update({
      pendingActions: this.state.pendingActions.filter((item) => item.id !== id),
    });
  }

  get pendingCount(): number {
    return this.state.pendingActions.filter((item) => item.state === "pending").length + this.state.recoveredApprovals.length;
  }

  appendLog(entry: Omit<ExtensionLogEntry, "timestamp">): Promise<ExtensionState> {
    const record: ExtensionLogEntry = { timestamp: new Date().toISOString(), ...entry };
    const log = [...this.state.log, record].slice(-MAX_LOG_ENTRIES);
    return this.update({ log });
  }

  // -- Phase 32 · AI Assistant -------------------------------------------

  /** Switch surfaces only. Backend capabilities are unaffected either way. */
  setUiMode(mode: UiMode): Promise<ExtensionState> {
    return this.update({ uiMode: mode });
  }

  // -- Phase 34 · first-run onboarding -----------------------------------
  //
  // Every method below writes display state only. None of them configures a
  // provider, stores a key, changes a permission level or touches the approval
  // queue: the guide *points at* Settings, it never acts for the user.

  /** Move from the automatic first-launch state into an explicit walkthrough. */
  startOnboarding(): Promise<ExtensionState> {
    return this.update({ onboardingState: "active" as OnboardingState, onboardingStep: 0 });
  }

  /** Next. Completing the last step finishes the guide and lands on Chat. */
  advanceOnboarding(): Promise<ExtensionState> {
    const next = this.state.onboardingStep + 1;
    if (next >= ONBOARDING_STEP_COUNT) return this.completeOnboarding();
    return this.update({ onboardingState: "active" as OnboardingState, onboardingStep: next });
  }

  /** Back, for a user who wants to re-read a step. Clamped at the first one. */
  regressOnboarding(): Promise<ExtensionState> {
    const previous = Math.max(0, this.state.onboardingStep - 1);
    return this.update({ onboardingState: "active" as OnboardingState, onboardingStep: previous });
  }

  /**
   * Skip. Chat is available immediately even with no Bridge and no provider —
   * an unconfigured user is allowed to look around.
   */
  skipOnboarding(): Promise<ExtensionState> {
    return this.update({ onboardingState: "skipped" as OnboardingState, onboardingStep: 0 });
  }

  /** Setup Later: dismissed for now, still offered as a hint. */
  deferOnboarding(): Promise<ExtensionState> {
    return this.update({ onboardingState: "later" as OnboardingState, onboardingStep: 0 });
  }

  /** All four steps done. Not shown again on the next launch. */
  completeOnboarding(): Promise<ExtensionState> {
    return this.update({ onboardingState: "done" as OnboardingState, onboardingStep: ONBOARDING_STEP_COUNT - 1 });
  }

  /** Re-open the guide from the hint. Explicit user action only. */
  reopenOnboarding(): Promise<ExtensionState> {
    return this.update({ onboardingState: "active" as OnboardingState, onboardingStep: 0 });
  }

  /** Store the Ask AI snapshot for display. Sending it stays a user action. */
  setAssistantWebContext(bundle: WebContextBundle | null): Promise<ExtensionState> {
    // A freshly captured bundle starts included; clearing resets the flag so the
    // next capture is not silently governed by an old choice.
    return this.update({ assistantWebContext: bundle, assistantContextInclude: bundle !== null });
  }

  /**
   * Phase 34 · decide whether the captured bundle is injected.
   *
   * Only ever called from a click. Setting it to `true` does not send anything:
   * the bundle still travels with the user's next message and nothing else.
   */
  setAssistantContextInclude(include: boolean): Promise<ExtensionState> {
    return this.update({ assistantContextInclude: include });
  }

  /** New Chat: an extension-view-only conversation, never a backend write. */
  newAssistantConversation(title = "New chat"): Promise<ExtensionState> {
    const conversation: AssistantConversationView = {
      id: `local_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      title,
      createdAt: new Date().toISOString(),
      turns: [],
      localOnly: true,
    };
    return this.update({
      assistantConversations: capConversations([...this.state.assistantConversations, conversation]),
      assistantActiveConversation: conversation.id,
      assistantStatus: "",
      assistantRenaming: null,
    });
  }

  selectAssistantConversation(id: string): Promise<ExtensionState> {
    if (!this.state.assistantConversations.some((item) => item.id === id)) {
      return Promise.resolve(this.state);
    }
    return this.update({ assistantActiveConversation: id });
  }

  /**
   * Remove a conversation from the extension view.
   *
   * Display state only: no Bridge call, so Phase 31 conversation storage keeps
   * every record it had.
   */
  removeAssistantConversation(id: string): Promise<ExtensionState> {
    const conversations = this.state.assistantConversations.filter((item) => item.id !== id);
    const active = this.state.assistantActiveConversation === id
      ? conversations[conversations.length - 1]?.id ?? null
      : this.state.assistantActiveConversation;
    return this.update({
      assistantConversations: conversations,
      assistantActiveConversation: active,
      // A rename box open on the removed row would otherwise be orphaned.
      assistantRenaming: this.state.assistantRenaming === id ? null : this.state.assistantRenaming,
      // Removing the conversation on screen must not leave a dead status line.
      assistantStatus: this.state.assistantActiveConversation === id ? "" : this.state.assistantStatus,
    });
  }

  // -- Phase 34 · conversation management (extension view only) -----------
  //
  // Search / Rename / Pin / Unpin / Remove all rewrite the local list. None of
  // them calls the Bridge, so backend conversation storage cannot be deleted or
  // modified from here, no provider key is touched, no tool proposal is created
  // and no LLM request is issued.

  /** Filter text for the local history list. Transient, never persisted. */
  setAssistantConversationQuery(query: string): Promise<ExtensionState> {
    return this.update({ assistantConversationQuery: query.slice(0, 120) });
  }

  /** Open the inline rename box. Unknown ids are ignored. */
  beginRenameConversation(id: string): Promise<ExtensionState> {
    if (!this.state.assistantConversations.some((item) => item.id === id)) {
      return Promise.resolve(this.state);
    }
    return this.update({ assistantRenaming: id });
  }

  cancelRenameConversation(): Promise<ExtensionState> {
    return this.update({ assistantRenaming: null });
  }

  /**
   * Rename a conversation in the extension view.
   *
   * An empty or whitespace-only title keeps the previous one, so the list can
   * never end up with an unclickable blank row.
   */
  renameAssistantConversation(id: string, title: string): Promise<ExtensionState> {
    if (!this.state.assistantConversations.some((item) => item.id === id)) {
      return Promise.resolve(this.state);
    }
    const clean = sanitizeConversationTitle(title);
    return this.update({
      assistantConversations: this.state.assistantConversations.map((item) =>
        item.id === id
          ? { ...item, title: clean || item.title || "Untitled chat", renamed: clean.length > 0 || item.renamed }
          : item,
      ),
      assistantRenaming: null,
    });
  }

  /** Pin / Unpin. Pinned conversations sort first and survive list capping. */
  setAssistantConversationPinned(id: string, pinned: boolean): Promise<ExtensionState> {
    if (!this.state.assistantConversations.some((item) => item.id === id)) {
      return Promise.resolve(this.state);
    }
    return this.update({
      assistantConversations: this.state.assistantConversations.map((item) =>
        item.id === id ? { ...item, pinned } : item,
      ),
    });
  }

  toggleAssistantConversationPinned(id: string): Promise<ExtensionState> {
    const found = this.state.assistantConversations.find((item) => item.id === id);
    if (!found) return Promise.resolve(this.state);
    return this.setAssistantConversationPinned(id, !found.pinned);
  }

  private async ensureConversation(): Promise<string> {
    const active = this.state.assistantActiveConversation;
    if (active && this.state.assistantConversations.some((item) => item.id === active)) return active;
    const state = await this.newAssistantConversation();
    return state.assistantActiveConversation as string;
  }

  async appendAssistantTurn(turn: AssistantChatTurn): Promise<ExtensionState> {
    const id = await this.ensureConversation();
    return this.update({
      assistantConversations: this.state.assistantConversations.map((item) =>
        item.id === id
          ? {
              ...item,
              // A user-chosen name wins over the automatic first-message title.
              title:
                item.turns.length === 0 && turn.role === "user" && !item.renamed
                  ? sanitizeConversationTitle(turn.content).slice(0, 60) || item.title
                  : item.title,
              turns: [...item.turns, turn],
            }
          : item,
      ),
    });
  }

  patchAssistantTurn(turnId: string, patch: Partial<AssistantChatTurn>): Promise<ExtensionState> {
    return this.update({
      assistantConversations: this.state.assistantConversations.map((conversation) => ({
        ...conversation,
        turns: conversation.turns.map((turn) => (turn.id === turnId ? { ...turn, ...patch } : turn)),
      })),
    });
  }

  setAssistantStreaming(streaming: boolean, status = ""): Promise<ExtensionState> {
    return this.update({ assistantStreaming: streaming, assistantStatus: status });
  }

  /**
   * Stop streaming on the user's request.
   *
   * The partial reply is kept and marked stopped. Nothing is retried: a Stop
   * must never trigger an automatic new request.
   */
  stopAssistantStreaming(): Promise<ExtensionState> {
    const conversations = this.state.assistantConversations.map((conversation) => ({
      ...conversation,
      turns: conversation.turns.map((turn) =>
        turn.streaming ? { ...turn, streaming: false, stopped: true } : turn,
      ),
    }));
    return this.update({
      assistantConversations: conversations,
      assistantStreaming: false,
      assistantStatus: "Streaming stopped",
    });
  }

  /**
   * Phase 34 · keep (or clear) the composer text.
   *
   * Called with the typed text when a send fails, and with `""` once it has been
   * handed back to the composer. Purely display state — it never resends.
   */
  setAssistantDraft(draft: string): Promise<ExtensionState> {
    return this.update({ assistantDraft: draft.slice(0, 8000) });
  }

  /**
   * Phase 34 · mark the turns of a failed request.
   *
   * The user turn stays in the transcript exactly once, so Retry can reuse it
   * instead of appending a duplicate; a half-streamed assistant turn stops
   * streaming and is marked failed. No retry is scheduled here.
   */
  failAssistantStreaming(message: string): Promise<ExtensionState> {
    const conversations = this.state.assistantConversations.map((conversation) => ({
      ...conversation,
      turns: conversation.turns.map((turn) =>
        turn.streaming ? { ...turn, streaming: false, failed: true } : turn,
      ),
    }));
    return this.update({
      assistantConversations: conversations,
      assistantStreaming: false,
      assistantStatus: message,
    });
  }

  /**
   * Phase 34 · drop the failed assistant placeholder at the end of the active
   * conversation, so Retry replaces it instead of stacking another one.
   *
   * Only trailing **assistant** turns marked `failed` are removed: the user turn
   * is left exactly where it is, which is what lets Retry reuse it rather than
   * sending the same message twice. Nothing is requested from here.
   */
  dropFailedAssistantTail(): Promise<ExtensionState> {
    const id = this.state.assistantActiveConversation;
    if (!id) return Promise.resolve(this.state);
    return this.update({
      assistantConversations: this.state.assistantConversations.map((conversation) => {
        if (conversation.id !== id) return conversation;
        const turns = [...conversation.turns];
        while (turns.length) {
          const last = turns[turns.length - 1];
          if (last.role !== "assistant" || !last.failed) break;
          turns.pop();
        }
        return { ...conversation, turns };
      }),
    });
  }

  get activeAssistantConversation(): AssistantConversationView | null {
    const id = this.state.assistantActiveConversation;
    return this.state.assistantConversations.find((item) => item.id === id) ?? null;
  }

  /**
   * The text Retry would resend: the most recent user turn of the conversation
   * on screen. `null` when there is nothing to retry, which is why Retry can
   * never invent a request of its own.
   */
  get lastAssistantUserMessage(): string | null {
    const conversation = this.activeAssistantConversation;
    if (!conversation) return null;
    for (let index = conversation.turns.length - 1; index >= 0; index -= 1) {
      const turn = conversation.turns[index];
      if (turn.role === "user" && turn.content.trim()) return turn.content;
    }
    return null;
  }
}
