/**
 * Content script controller: wires the observer, store, Bridge client and UI.
 *
 * Security invariants enforced here:
 *  - Captured actions are ALWAYS queued as pending; nothing auto-executes.
 *  - Approval calls the Bridge only after an explicit user click.
 *  - Reject never touches the filesystem, it only records the decision.
 *  - Invalid action blocks are logged as "ignored" and dropped.
 *  - Phase 34: every assistant-facing failure is rendered through
 *    `safeErrorMessage`, so no stack trace, path, key, header, provider body or
 *    exception object can reach the panel. Retry is a user click and is never
 *    scheduled automatically.
 */

import { BridgeClient } from "../bridge/client";
import { BridgeUnavailableError, type RecoveredApproval } from "../bridge/types";
import { isMutatingAction, type PendingAction } from "../models/action";
import type { ExtensionStore } from "../state/store";
import type { ParseResult } from "./action-parser";
import type { AssistantProviderEntry, AssistantToolCall, UiMode, WebContextBundle } from "../assistant/types";
import { SAFE_MESSAGES, isSafeMessage, safeErrorMessage } from "../assistant/errors";

export interface ControllerDeps {
  store: ExtensionStore;
  client: BridgeClient;
  /** Re-render the UI after every state transition. */
  render: () => void;
  /** Optional project list sink for the panel dropdown. */
  onProjects?: (projects: string[]) => void;
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `act_${Date.now().toString(36)}_${counter.toString(36)}`;
}

export class Controller {
  private readonly store: ExtensionStore;
  private readonly client: BridgeClient;
  private readonly render: () => void;
  private readonly onProjects?: (projects: string[]) => void;
  /** Live assistant stream, aborted by Stop. */
  private assistantAbort: AbortController | null = null;

  constructor(deps: ControllerDeps) {
    this.store = deps.store;
    this.client = deps.client;
    this.render = deps.render;
    this.onProjects = deps.onProjects;
  }

  /** Check Bridge health and load the project list. */
  async connect(): Promise<void> {
    try {
      await this.client.health();
      await this.store.setBridgeStatus("connected");

      const { projects } = await this.client.listProjects();
      const names = projects.map((project) => project.name);
      this.onProjects?.(names);

      const current = this.store.getState().currentProject;
      if (!current && names.length === 1) {
        await this.store.setProject(names[0]);
      }
      await this.refreshApprovals();
      await this.refreshContext();
      await this.store.appendLog({
        event: "bridge.connect",
        detail: `${names.length} project(s)`,
        approved: true,
        result: "success",
      });
    } catch (error) {
      const offline = error instanceof BridgeUnavailableError;
      await this.store.setBridgeStatus(offline ? "offline" : "error");
      await this.store.update({
        lastResult: offline ? "Local Bridge unavailable" : describe(error),
      });
      await this.store.appendLog({
        event: "bridge.connect",
        detail: describe(error),
        approved: false,
        result: "failed",
      });
    } finally {
      this.render();
    }
  }

  /** Refresh recovered approvals without approving or executing them. */
  async refreshApprovals(): Promise<void> {
    try {
      const response = await this.client.pendingApprovals();
      const recovered: RecoveredApproval[] = response.pending
        .filter(
          (item) =>
            typeof item.requestId === "string" &&
            typeof item.action === "string" &&
            typeof item.project === "string" &&
            typeof item.path === "string" &&
            typeof item.reason === "string" &&
            typeof item.preview === "string" &&
            (item.status === "recovered" || item.status === "reconfirmed"),
        )
        .map((item) => item as unknown as RecoveredApproval);
      await this.store.update({ recoveredApprovals: recovered });
    } catch (error) {
      await this.store.update({ lastResult: describe(error) });
    }
  }

  /** Refresh read-only project context for the Workflow Dashboard. */
  async refreshContext(): Promise<void> {
    const project = this.store.getState().currentProject;
    if (!project) {
      await this.store.update({ projectContext: null, devContext: null, devContextSelection: [], phase30Intelligence: null, llmProviders: [], llmModels: [], llmConversations: [], llmToolProposals: [], sessions: [], agents: [], modelSelection: null, runtimes: [], tasks: [], runtimeEvents: [], qualityReport: null, teams: [], dependencies: [], collaborationEvents: [], projectProfile: null, projectGraph: null, impactReport: null, projectMemoryHistory: null, intelligenceInsights: [], intelligenceProposals: [], intelligenceDecisions: [], intelligenceQuality: null, intelligenceObservations: [], intelligencePatterns: [], intelligencePredictions: [], intelligenceRecommendations: [], intelligenceOutcomes: [], intelligenceKnowledge: [], intelligenceEvidence: [], intelligenceQuality11: null, intelligenceTrends: [], intelligenceCorrelations: [], intelligenceImpactPredictions: [], intelligenceDependencyRisks: [], intelligenceEvaluations: [], intelligenceEvaluationMetrics: null, intelligenceRecommendationRanking: null, intelligenceEvidenceGraph: null, intelligenceValidation: null, intelligenceAccuracy: null, intelligenceEffectiveness: [], intelligenceEffectivenessSummary: null, intelligenceDecisionOutcomes: [], intelligenceDecisionSummary: null, intelligenceBenchmarks: [], intelligenceImprovements: [], intelligenceGovernance: null, simulation: null, simulationScenarios: [], simulationEvaluations: [],        simulationPlans: [], simulationQuality: null, planningMemoryHistory: null, executionTasks: [], executionProposals: [], executionResults: [], executionQuality7: null, executionMemoryHistory: null, executionLoops: [], executionLoopTimeline: [], executionLoopQuality8: null, executionDags: [], executionDagReady: null, engineeringMetrics: null, executionLoopContext: null, engineeringGraph: null, failurePatterns: [], evolutionTimeline: [], agentCapabilityMetrics: [], benchmarks: [], demoScenarios: [], demoFlow: [], replays: [], artifacts: [], governanceHealth: null, governanceDrift: null, governanceDebt: null, governancePolicies: null, governanceTimeline: null, governanceQuality9: null, organizationGraph: null, organizationHealth: null, organizationDashboard: null, organizationPatterns: null, organizationIncidents: null, organizationLearning: null, organizationQuality10: null, organizationStrategyImpact: null, organizationStrategyRisk: null, organizationStrategies: null, organizationRecommendations: null, organizationStrategyContext: null, lastContextRefresh: null });
      this.render();
      return;
    }
    // Spec §2: User Mode must not pull developer engineering data. Only the
    // assistant's own read-only status calls run in that mode.
    if (this.store.getState().uiMode === "user") {
      await this.refreshAssistant();
      this.render();
      return;
    }
    try {
      const context = await this.client.projectContext(project);
      const sessions = await this.client.sessionList(project).catch(() => ({ sessions: [] }));
      const runtime = await this.client.agentStatus(project, "review implementation and test results").catch(() => ({
        agents: [],
        messages: [],
        models: [],
        selectedModel: null,
      }));
      const runtimeStatus = await this.client.runtimeStatus().catch(() => ({ runtimes: [], states: [] }));
      const runtimeEvents = await this.client.runtimeEvents().catch(() => ({ events: [] }));
      const tasks = await this.client.taskList().catch(() => ({ tasks: [] }));
      const teams = await this.client.teamList(context.currentWorkflow?.id).catch(() => ({ teams: [] }));
      const collaboration = await this.client.collaborationEvents().catch(() => ({ events: [] }));
      const projectProfile = await this.client.projectProfile(project).catch(() => null);
      const projectGraph = await this.client.projectGraph(project).catch(() => null);
      const impactReport = await this.client.impactAnalysis(project).catch(() => null);
      const projectMemoryHistory = await this.client.projectMemoryHistory(project).catch(() => null);
      const intelligenceInsights = await this.client.intelligenceInsights(project).catch(() => ({ project, insights: [], readOnly: true as const }));
      const intelligenceProposals = await this.client.intelligenceProposals(project).catch(() => ({ project, proposals: [], readOnly: true as const }));
      const intelligenceDecisions = await this.client.intelligenceDecisions(project).catch(() => ({ project, decisions: [], readOnly: true as const }));
      const intelligenceQuality = context.currentWorkflow ? await this.client.intelligenceQuality(context.currentWorkflow.id).catch(() => null) : null;
      const intelligenceObservations = await this.client.intelligenceObservations(project).then((result) => result.observations).catch(() => []);
      const intelligencePatterns = await this.client.intelligencePatterns(project).then((result) => result.patterns).catch(() => []);
      const intelligencePredictions = await this.client.intelligencePredictions(project).then((result) => result.predictions).catch(() => []);
      const intelligenceRecommendations = await this.client.intelligenceRecommendations(project).then((result) => result.recommendations).catch(() => []);
      const intelligenceOutcomes = await this.client.intelligenceOutcomes(project).then((result) => result.outcomes).catch(() => []);
      const intelligenceKnowledge = await this.client.intelligenceKnowledge(project).then((result) => result.knowledge).catch(() => []);
      const intelligenceEvidence = await this.client.intelligenceEvidence(project).then((result) => result.evidence).catch(() => []);
      const intelligenceQuality11 = await this.client.intelligenceQuality11(project).catch(() => null);
      const intelligenceTrends = await this.client.intelligenceTrends(project).then((result) => result.trends).catch(() => []);
      const intelligenceCorrelations = await this.client.intelligenceCorrelations(project).then((result) => result.correlations).catch(() => []);
      const intelligenceImpactPredictions = await this.client.intelligenceImpact(project).then((result) => result.impact).catch(() => []);
      const intelligenceDependencyRisks = await this.client.intelligenceDependencies(project).then((result) => result.dependencies).catch(() => []);
      const intelligenceEvaluationResponse = await this.client.intelligenceEvaluations(project).catch(() => null);
      const intelligenceEvaluations = intelligenceEvaluationResponse?.evaluations ?? [];
      const intelligenceEvaluationMetrics = intelligenceEvaluationResponse?.metrics ?? null;
      const intelligenceRecommendationRanking = await this.client.intelligenceRecommendationRanking(project).catch(() => null);
      const intelligenceEvidenceGraph = await this.client.intelligenceEvidenceGraph(project).catch(() => null);
      const intelligenceValidation = await this.client.intelligenceValidation(project).catch(() => null);
      const intelligenceGovernance = await this.client.intelligenceGovernance(project).catch(() => null);
      const devContext = await this.client.devContextBundle(project).catch(() => null);
      const phase30Intelligence = await this.client.contextIntelligenceSnapshot(project).catch(() => null);
      const llmProviders = await this.client.llmProviders().then((result) => result.providers).catch(() => []);
      const llmModels = await this.client.llmModels().then((result) => result.models).catch(() => []);
      const llmConversations = await this.client.llmConversations(project).then((result) => result.conversations).catch(() => []);
      const llmToolProposals = await this.client.llmToolProposals(project).then((result) => result.proposals).catch(() => []);
      const simulation = await this.client.simulation(project).catch(() => null);
      const simulationScenarios = simulation ? await this.client.simulationScenarios(simulation.id).then((result) => result.scenarios).catch(() => []) : [];
      const simulationEvaluations = simulation ? await this.client.simulationEvaluation(simulation.id).then((result) => result.evaluations).catch(() => []) : [];
      const simulationQuality = context.currentWorkflow ? await this.client.simulationQuality(context.currentWorkflow.id).catch(() => null) : null;
      const planningMemoryHistory = await this.client.planningMemoryHistory(project).catch(() => null);
      const executionTasks = await this.client.executionTasks(project).then((result) => result.tasks).catch(() => []);
      const executionProposals = await this.client.executionProposals(project).then((result) => result.proposals).catch(() => []);
      const executionResults = await this.client.executionResults(project).then((result) => result.results).catch(() => []);
      const executionQuality7 = context.currentWorkflow ? await this.client.executionQuality7(context.currentWorkflow.id).catch(() => null) : null;
      const executionMemoryHistory = await this.client.executionMemoryHistory(project).catch(() => null);
      const executionLoops = await this.client.executionLoopList(project).then((result) => result.loops).catch(() => []);
      const executionLoopTimeline = executionLoops.length ? await this.client.executionLoopTimeline(executionLoops[0].id).then((result) => result.timeline).catch(() => []) : [];
      const executionLoopQuality8 = executionLoops[0]?.workflowId ? await this.client.executionLoopQuality8(executionLoops[0].workflowId).catch(() => null) : null;
      const executionDags = await this.client.executionDagList(project).then((result) => result.dags).catch(() => []);
      const executionDagReady = executionDags[0] ? await this.client.executionDagReady(executionDags[0].id).catch(() => null) : null;
      const engineeringMetrics = await this.client.engineeringMetrics(project).catch(() => null);
      const executionLoopContext = executionLoops[0] ? await this.client.executionLoopContext(executionLoops[0].id).catch(() => null) : null;
      const engineeringGraph = await this.client.engineeringGraph(project).catch(() => null);
      const failurePatterns = await this.client.failurePatterns(project).then((result) => result.patterns).catch(() => []);
      const evolutionTimeline = await this.client.evolutionTimeline(project).then((result) => result.timeline).catch(() => []);
      const agentCapabilityMetrics = await this.client.agentCapabilityMetrics().then((result) => result.metrics).catch(() => []);
      const benchmarks = await this.client.benchmarkList(project).then((result) => result.benchmarks).catch(() => []);
      const demoScenarios = await this.client.demoCatalog().then((result) => result.scenarios).catch(() => []);
      const demoFlow = await this.client.demoFlow().then((result) => result.flow).catch(() => []);
      const replays = await this.client.replayList(project).then((result) => result.replays).catch(() => []);
      const artifacts = await this.client.artifactList(project).then((result) => result.artifacts).catch(() => []);
      const governanceHealth = await this.client.governanceHealth(project).catch(() => null);
      const governanceDrift = await this.client.governanceDrift(project).catch(() => null);
      const governanceDebt = await this.client.governanceDebt(project).catch(() => null);
      const governancePolicies = await this.client.governancePolicies(project).catch(() => null);
      const governanceTimeline = await this.client.governanceTimeline(project).catch(() => null);
      const governanceQuality9 = context.currentWorkflow ? await this.client.governanceQuality9(context.currentWorkflow.id).catch(() => null) : null;
      const organizationGraph = await this.client.organizationGraph().catch(() => null);
      const organizationHealth = await this.client.organizationHealth().catch(() => null);
      const organizationDashboard = await this.client.organizationDashboard().catch(() => null);
      const organizationPatterns = await this.client.organizationPatterns().catch(() => null);
      const organizationIncidents = await this.client.organizationIncidents(project).catch(() => null);
      const organizationLearning = await this.client.organizationLearningSimilar(project).catch(() => null);
      const organizationQuality10 = await this.client.organizationQuality10("organization").catch(() => null);
      const strategyNodeId = organizationGraph?.services[0]?.id ?? organizationGraph?.projects[0]?.id ?? organizationGraph?.repositories[0]?.id ?? "";
      const organizationStrategyImpact = strategyNodeId ? await this.client.organizationImpact(strategyNodeId).catch(() => null) : null;
      const organizationStrategyRisk = strategyNodeId ? await this.client.organizationRisk(strategyNodeId).catch(() => null) : null;
      const organizationStrategies = await this.client.organizationStrategies(project).catch(() => null);
      const organizationRecommendations = await this.client.organizationRecommendations().catch(() => null);
      const organizationStrategyContext = await this.client.organizationContext().catch(() => null);
      const dependencyResults = await Promise.all(tasks.tasks.slice(0, 10).map((task) => this.client.taskDependencies(task.id).catch(() => ({ taskId: task.id, dependencies: [], hasCycle: false }))));
      const dependencies = dependencyResults.flatMap((result) => result.dependencies);
      const qualityReport = context.currentWorkflow
        ? await this.client.quality(context.currentWorkflow.id).catch(() => null)
        : null;
      await this.store.update({
        projectContext: context,
        sessions: sessions.sessions,
        agents: runtime.agents,
        modelSelection: runtime.selectedModel ?? null,
        runtimes: runtimeStatus.runtimes,
        tasks: tasks.tasks,
        runtimeEvents: runtimeEvents.events,
        qualityReport,
        teams: teams.teams,
        dependencies,
        collaborationEvents: collaboration.events,
        projectProfile,
        projectGraph,
        impactReport,
        projectMemoryHistory,
        intelligenceInsights: intelligenceInsights.insights,
        intelligenceProposals: intelligenceProposals.proposals,
        intelligenceDecisions: intelligenceDecisions.decisions,
        intelligenceQuality,
        intelligenceObservations,
        intelligencePatterns,
        intelligencePredictions,
        intelligenceRecommendations,
        intelligenceOutcomes,
        intelligenceKnowledge,
        intelligenceEvidence,
        intelligenceQuality11,
        intelligenceTrends,
        intelligenceCorrelations,
        intelligenceImpactPredictions,
        intelligenceDependencyRisks,
        intelligenceEvaluations,
        intelligenceEvaluationMetrics,
        intelligenceRecommendationRanking,
        intelligenceEvidenceGraph,
        intelligenceValidation,
        intelligenceAccuracy: intelligenceValidation?.accuracy ?? null,
        intelligenceEffectiveness: intelligenceValidation?.effectiveness ?? [],
        intelligenceEffectivenessSummary: intelligenceValidation?.effectivenessSummary ?? null,
        intelligenceDecisionOutcomes: intelligenceValidation?.decisionOutcomes ?? [],
        intelligenceDecisionSummary: intelligenceValidation?.decisionSummary ?? null,
        intelligenceBenchmarks: intelligenceValidation?.benchmarks ?? [],
        intelligenceImprovements: intelligenceValidation?.improvements ?? [],
        intelligenceGovernance,
        devContext,
        phase30Intelligence,
        llmProviders,
        llmModels,
        llmConversations,
        llmToolProposals,
        simulation,
        simulationScenarios,
        simulationEvaluations,
        simulationPlans: simulation?.plans ?? [],
        simulationQuality,
        planningMemoryHistory,
        executionTasks,
        executionProposals,
        executionResults,
        executionQuality7,
        executionMemoryHistory,
        executionLoops,
        executionLoopTimeline,
        executionLoopQuality8,
        executionDags,
        executionDagReady,
        engineeringMetrics,
        executionLoopContext,
        engineeringGraph,
        failurePatterns,
        evolutionTimeline,
        agentCapabilityMetrics,
        benchmarks,
        demoScenarios,
        demoFlow,
        replays,
        artifacts,
        governanceHealth,
        governanceDrift,
        governanceDebt,
        governancePolicies,
        governanceTimeline,
        governanceQuality9,
        organizationGraph,
        organizationHealth,
        organizationDashboard,
        organizationPatterns,
        organizationIncidents,
        organizationLearning,
        organizationQuality10,
        organizationStrategyImpact,
        organizationStrategyRisk,
        organizationStrategies,
        organizationRecommendations,
        organizationStrategyContext,
        lastContextRefresh: new Date().toISOString(),
      });
    } catch (error) {
      await this.store.update({ lastResult: describe(error) });
    }
    await this.refreshAssistant();
    this.render();
  }

  /**
   * Phase 32 · read-only assistant status: user settings, provider status and
   * context status. None of those responses carries an API key, and nothing
   * here writes to the workspace.
   */
  async refreshAssistant(): Promise<void> {
    const state = this.store.getState();
    try {
      const settings = await this.client.userSettings();
      const status = await this.client
        .providerStatus()
        .catch(() => ({ providers: [] as AssistantProviderEntry[] }));
      const contextStatus = await this.client
        .contextStatus(state.currentProject ?? "", state.uiMode)
        .catch(() => null);
      const entries = status.providers;
      const provider = state.assistantProvider || settings.provider || entries[0]?.provider || "local";
      const active = entries.find((item) => item.provider === provider) ?? null;
      await this.store.update({
        assistantSettings: settings,
        assistantProviders: entries,
        assistantContextStatus: contextStatus,
        assistantProvider: provider,
        assistantModel:
          state.assistantModel || active?.selectedModel || active?.models[0] || settings.model || "",
      });
    } catch (error) {
      await this.store.update({ assistantStatus: safeErrorMessage(error) });
    }
  }

  /** Mode is a local, non-sensitive preference (spec §17). */
  async setUiMode(mode: UiMode): Promise<void> {
    await this.store.setUiMode(mode);
    await this.refreshContext();
  }

  /** Provider and model names are preferences, not credentials. */
  async selectAssistantProvider(provider: string): Promise<void> {
    const entry = this.store.getState().assistantProviders.find((item) => item.provider === provider);
    await this.store.update({
      assistantProvider: provider,
      assistantModel: entry?.selectedModel || entry?.models[0] || "",
      assistantProviderTest: null,
    });
    this.render();
  }

  async selectAssistantModel(model: string): Promise<void> {
    await this.store.update({ assistantModel: model });
    this.render();
  }

  /**
   * Save provider settings.
   *
   * `input.apiKey` is the transient value of the Settings input. It is handed to
   * the Bridge (which encrypts it with AES-256-GCM) and never written to state,
   * never logged and never placed in a URL. The write itself is approval-gated,
   * so this only queues a request for a human to approve.
   */
  async saveProvider(input: { provider: string; model: string; baseUrl: string; apiKey: string }): Promise<void> {
    try {
      await this.client.providerConfig({
        provider: input.provider,
        model: input.model || undefined,
        base_url: input.baseUrl || undefined,
        api_key: input.apiKey || undefined,
        keep_existing_key: input.apiKey.length === 0,
        reason: "Provider settings update requested in the assistant panel",
      });
      await this.store.update({ assistantStatus: "Provider update waiting for approval." });
    } catch (error) {
      await this.store.update({ assistantStatus: safeErrorMessage(error) });
    }
    await this.refreshAssistant();
    this.render();
  }

  /** Test Connection. The Bridge answers with a fixed, safe vocabulary only. */
  async testProvider(input: { provider: string; model: string; apiKey: string }): Promise<void> {
    try {
      const result = await this.client.providerTest({
        provider: input.provider,
        model: input.model || undefined,
        api_key: input.apiKey || undefined,
      });
      await this.store.update({ assistantProviderTest: result, assistantStatus: result.message });
    } catch (error) {
      await this.store.update({ assistantStatus: safeErrorMessage(error) });
    }
    this.render();
  }

  async forgetProviderKey(provider: string): Promise<void> {
    try {
      await this.client.providerForget({ provider, reason: "Remove the stored provider key" });
      await this.store.update({ assistantStatus: "Key removal waiting for approval." });
    } catch (error) {
      await this.store.update({ assistantStatus: safeErrorMessage(error) });
    }
    await this.refreshAssistant();
    this.render();
  }

  /**
   * Ask AI: store the collected page snapshot for display.
   *
   * Collecting is not sending — the bundle travels to the Bridge only when the
   * user submits a message, and it is dropped straight afterwards.
   */
  async askAi(bundle: WebContextBundle): Promise<void> {
    await this.store.setAssistantWebContext(bundle);
    await this.store.update({
      assistantStatus: "Page context ready. It is sent only with your next message.",
    });
    this.render();
  }

  async clearWebContext(): Promise<void> {
    await this.store.setAssistantWebContext(null);
    this.render();
  }

  /** Stop streaming. Nothing is retried afterwards. */
  async stopAssistant(): Promise<void> {
    this.assistantAbort?.abort();
    this.assistantAbort = null;
    await this.store.stopAssistantStreaming();
    this.render();
  }

  /**
   * Send one chat message and stream the reply.
   *
   * Tool calls that come back are recorded on the turn as proposals only:
   * `toolCallsExecuted` is always false on the Bridge side and nothing here
   * executes, applies or approves anything.
   *
   * Phase 34 · the captured page is attached **only** when the user left the
   * include switch on, the composer text is handed back if the request fails,
   * and `appendUserTurn: false` lets Retry reuse the user turn that is already in
   * the transcript instead of sending the same message a second time.
   */
  async sendAssistantMessage(text: string, options: { appendUserTurn?: boolean } = {}): Promise<void> {
    const before = this.store.getState();
    // Excluding the bundle sends nothing while keeping the preview on screen.
    const webContext = before.assistantContextInclude ? before.assistantWebContext : null;
    const turnId = `turn_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    if (options.appendUserTurn !== false) {
      await this.store.appendAssistantTurn({
        id: `${turnId}_u`,
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
      });
    }
    await this.store.appendAssistantTurn({
      id: turnId,
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      streaming: true,
    });
    await this.store.setAssistantStreaming(true);
    // The composer is emptied on send; a failure below hands the text back.
    await this.store.setAssistantDraft("");
    this.render();

    const conversation = this.store.activeAssistantConversation;
    const messages = (conversation?.turns ?? [])
      .filter((turn) => turn.id !== turnId && turn.content)
      .map((turn) => ({ role: turn.role, content: turn.content }));

    const abort = new AbortController();
    this.assistantAbort = abort;
    const toolCalls: AssistantToolCall[] = [];
    let reply = "";
    let failed = false;
    // Phase 34 · a mid-stream `error` frame is a failure, not assistant text.
    let streamError = "";

    try {
      await this.client.assistantChatStream(
        {
          project: before.currentProject ?? "",
          messages,
          provider: before.assistantProvider || undefined,
          model: before.assistantModel || undefined,
          web_context: webContext,
        },
        {
          signal: abort.signal,
          onEvent: (event) => {
            if (event.type === "error") {
              // The Bridge only ever puts a fixed safe sentence here. Anything
              // outside the closed vocabulary is replaced, never displayed, so a
              // vendor payload cannot reach the panel through this path.
              streamError = isSafeMessage(event.content)
                ? event.content
                : SAFE_MESSAGES.providerUnavailable;
              return;
            }
            if (event.toolCall) toolCalls.push(event.toolCall);
            if (event.content) reply += event.content;
            void this.store.patchAssistantTurn(turnId, { content: reply, toolCalls: [...toolCalls] });
            this.render();
          },
        },
      );
      if (this.assistantAbort !== abort) return;
      if (streamError) {
        // Partial content is kept; the turn is marked failed so Retry appears
        // and the composer gets the question back. No automatic retry.
        failed = true;
        await this.store.patchAssistantTurn(turnId, {
          content: reply,
          toolCalls,
          streaming: false,
          failed: true,
        });
        await this.store.setAssistantDraft(text);
        await this.store.failAssistantStreaming(streamError);
      } else {
        await this.store.patchAssistantTurn(turnId, { content: reply, toolCalls, streaming: false });
        await this.store.setAssistantStreaming(
          false,
          toolCalls.length ? "Tool proposal waiting for approval." : "",
        );
      }
    } catch (error) {
      if (this.assistantAbort !== abort) return;
      failed = true;
      await this.store.patchAssistantTurn(turnId, {
        content: reply,
        toolCalls,
        streaming: false,
        failed: true,
      });
      // No automatic retry: the user decides whether to ask again, and the text
      // goes back to the composer instead of being dropped.
      await this.store.setAssistantDraft(text);
      await this.store.failAssistantStreaming(safeErrorMessage(error));
    } finally {
      if (this.assistantAbort === abort) this.assistantAbort = null;
      // The consented bundle is used once and then forgotten. A failed request
      // keeps it, so Retry reuses the context the user already approved instead
      // of asking for a second Ask AI click. Nothing re-captures it.
      if (webContext && !failed) await this.store.setAssistantWebContext(null);
      this.render();
    }
  }

  /**
   * Retry the last user message. Always a click, never a timer.
   *
   * The failed assistant placeholder is dropped and the existing user turn is
   * reused, so a retry cannot send the same message twice. There is no automatic
   * provider retry anywhere in the extension.
   */
  async retryAssistant(): Promise<void> {
    if (this.store.getState().assistantStreaming) return;
    const text = this.store.lastAssistantUserMessage;
    if (!text) return;
    await this.store.dropFailedAssistantTail();
    await this.store.setAssistantDraft("");
    await this.sendAssistantMessage(text, { appendUserTurn: false });
  }

  // -- Phase 34 · onboarding, conversations and context ---------------------
  //
  // Everything below writes extension display state and nothing else: no Bridge
  // call, no provider write, no key, no approval, no tool proposal, no LLM
  // request. The onboarding state is a plain non-sensitive marker.

  async onboardingNext(): Promise<void> {
    await this.store.advanceOnboarding();
    this.render();
  }

  async onboardingBack(): Promise<void> {
    await this.store.regressOnboarding();
    this.render();
  }

  async onboardingSkip(): Promise<void> {
    await this.store.skipOnboarding();
    this.render();
  }

  async onboardingLater(): Promise<void> {
    await this.store.deferOnboarding();
    this.render();
  }

  async onboardingFinish(): Promise<void> {
    await this.store.completeOnboarding();
    this.render();
  }

  async onboardingReopen(): Promise<void> {
    await this.store.reopenOnboarding();
    this.render();
  }

  async searchConversations(query: string): Promise<void> {
    await this.store.setAssistantConversationQuery(query);
    this.render();
  }

  async beginRenameConversation(id: string): Promise<void> {
    await this.store.beginRenameConversation(id);
    this.render();
  }

  async renameConversation(id: string, title: string): Promise<void> {
    await this.store.renameAssistantConversation(id, title);
    this.render();
  }

  async cancelRenameConversation(): Promise<void> {
    await this.store.cancelRenameConversation();
    this.render();
  }

  async toggleConversationPinned(id: string): Promise<void> {
    await this.store.toggleAssistantConversationPinned(id);
    this.render();
  }

  async newConversation(): Promise<void> {
    await this.store.newAssistantConversation();
    this.render();
  }

  async selectConversation(id: string): Promise<void> {
    await this.store.selectAssistantConversation(id);
    this.render();
  }

  /** Hides a conversation in this view. Bridge records are untouched. */
  async removeConversation(id: string): Promise<void> {
    await this.store.removeAssistantConversation(id);
    this.render();
  }

  /** Decide whether the captured page travels with the next message. */
  async toggleContextInclude(include: boolean): Promise<void> {
    await this.store.setAssistantContextInclude(include);
    this.render();
  }

  /** Handle parser output coming from the DOM observer. */
  async handleParseResults(results: ParseResult[]): Promise<void> {
    for (const result of results) {
      if (!result.ok) {
        await this.store.appendLog({
          event: "action.rejected_schema",
          detail: result.error,
          approved: false,
          result: "ignored",
        });
        continue;
      }

      const pending: PendingAction = {
        id: nextId(),
        action: result.action,
        state: "pending",
        createdAt: new Date().toISOString(),
        fingerprint: result.fingerprint,
      };
      await this.store.addPending(pending);
      await this.store.appendLog({
        event: "action.captured",
        detail: `${result.action.action} ${result.action.target.project}:${result.action.target.path}`,
        approved: false,
        result: "pending",
      });
    }
    this.render();
  }

  /** Explicitly reconfirm one recovered approval; this still does not execute it. */
  async reconfirm(requestId: string): Promise<void> {
    try {
      await this.client.reconfirm(requestId);
      await this.refreshApprovals();
      await this.store.update({ lastResult: "Recovered approval reconfirmed; execution still requires explicit approval" });
      await this.store.appendLog({
        event: "approval.reconfirmed",
        detail: requestId,
        approved: true,
        result: "pending",
      });
    } catch (error) {
      await this.store.update({ lastResult: describe(error) });
    }
    this.render();
  }

  /** Execute only after the recovered request has been explicitly reconfirmed. */
  async approveRecovered(requestId: string): Promise<void> {
    try {
      await this.client.approve(requestId);
      await this.refreshApprovals();
      await this.store.update({ lastResult: "Recovered approval executed after explicit confirmation" });
      await this.store.appendLog({
        event: "approval.recovered_executed",
        detail: requestId,
        approved: true,
        result: "success",
      });
    } catch (error) {
      await this.store.update({ lastResult: describe(error) });
    }
    this.render();
  }

  /** User clicked Approve. Stage on the Bridge, then approve it. */
  async approve(id: string): Promise<void> {
    const item = this.store.getState().pendingActions.find((entry) => entry.id === id);
    if (!item || item.state !== "pending") return;

    const label = `${item.action.action} ${item.action.target.project}:${item.action.target.path}`;

    if (!isMutatingAction(item.action.action)) {
      // Read actions are Level 0 on the Bridge; execute directly on approval.
      await this.store.patchPending(id, { state: "approving" });
      this.render();
      try {
        let preview: string;
        let message: string;
        if (item.action.action === "memory.read") {
          const file = await this.client.readMemory(
            item.action.target.project,
            item.action.target.document ?? "project.md",
          );
          preview = file.content.slice(0, 1200);
          message = `Read ${file.size} bytes`;
        } else if (item.action.action === "git.status") {
          const result = await this.client.gitStatus(item.action.target.project);
          preview = JSON.stringify(result, null, 2).slice(0, 1200);
          message = "Git status loaded";
        } else if (item.action.action === "git.diff") {
          const result = await this.client.gitDiff(
            item.action.target.project,
            item.action.payload.staged === true,
          );
          preview = String(result.diff ?? JSON.stringify(result, null, 2)).slice(0, 1200);
          message = "Git diff loaded";
        } else if (item.action.action === "workflow.status") {
          const result = await this.client.workflowStatus(item.action.workflow_id ?? "");
          preview = JSON.stringify(result, null, 2).slice(0, 1200);
          message = "Workflow status loaded";
        } else {
          const file = await this.client.readFile(
            item.action.target.project,
            item.action.target.path,
          );
          preview = file.content.slice(0, 1200);
          message = `Read ${file.size} bytes`;
        }
        await this.store.patchPending(id, {
          state: "approved",
          message,
          preview,
        });
        await this.store.update({ lastResult: `Read ${item.action.target.path}` });
        await this.store.appendLog({
          event: "action.read",
          detail: label,
          approved: true,
          result: "success",
        });
      } catch (error) {
        await this.failAction(id, label, error);
      }
      this.render();
      return;
    }

    await this.store.patchPending(id, { state: "approving" });
    this.render();

    try {
      // Step 1: stage on the Bridge -> returns a pending approval request.
      const staged = await this.client.stage(item.action);
      await this.store.patchPending(id, {
        bridgeRequestId: staged.requestId,
        preview: staged.preview,
      });
      this.render();

      // Step 2: explicit approval executes the write.
      const executed = await this.client.approve(staged.requestId);
      const size = Number(executed.result?.size ?? 0);
      await this.store.patchPending(id, {
        state: "approved",
        message: `Applied via Bridge (${size} bytes, ${executed.permissionLevel})`,
      });
      await this.store.update({ lastResult: `Applied ${item.action.target.path}` });
      await this.store.appendLog({
        event: "action.approved",
        detail: `${label} requestId=${staged.requestId}`,
        approved: true,
        result: "success",
      });
    } catch (error) {
      await this.failAction(id, label, error);
    }
    this.render();
  }

  /** User clicked Reject. Nothing is sent to the Bridge for execution. */
  async reject(id: string): Promise<void> {
    const item = this.store.getState().pendingActions.find((entry) => entry.id === id);
    if (!item || item.state !== "pending") return;

    await this.store.patchPending(id, { state: "rejected", message: "Rejected by user" });
    await this.store.update({ lastResult: `Rejected ${item.action.target.path}` });
    await this.store.appendLog({
      event: "action.rejected",
      detail: `${item.action.action} ${item.action.target.project}:${item.action.target.path}`,
      approved: false,
      result: "rejected",
    });
    this.render();
  }

  async selectProject(project: string): Promise<void> {
    await this.store.setProject(project);
    await this.refreshApprovals();
    await this.refreshContext();
    await this.store.appendLog({
      event: "project.selected",
      detail: project,
      approved: true,
      result: "success",
    });
    this.render();
  }

  private async failAction(id: string, label: string, error: unknown): Promise<void> {
    const offline = error instanceof BridgeUnavailableError;
    if (offline) await this.store.setBridgeStatus("offline");

    const message = offline ? "Local Bridge unavailable" : describe(error);
    await this.store.patchPending(id, { state: "failed", message });
    await this.store.update({ lastResult: message });
    await this.store.appendLog({
      event: "action.failed",
      detail: `${label}: ${message}`,
      approved: true,
      result: "failed",
    });
  }
}

function describe(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
