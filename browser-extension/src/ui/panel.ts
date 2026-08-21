/**
 * Floating panel rendered inside the shadow root.
 *
 * Shows: Bridge status, current project, pending action count, and the
 * approval cards. It is pure presentation plus user intent callbacks.
 */

import type { ExtensionState } from "../state/store";
import { renderWorkflowDashboard } from "../dashboard/workflow-dashboard";
import { renderRuntimeDashboard } from "../runtime/runtime-dashboard";
import { renderCollaborationDashboard } from "../collaboration/collaboration-dashboard";
import { renderProjectIntelligenceDashboard } from "../project-intelligence/project-intelligence-dashboard";
import { renderIntelligenceDashboard } from "../intelligence/intelligence-dashboard";
import { renderSimulationDashboard } from "../simulation/simulation-dashboard";
import { renderExecutionDashboard } from "../execution/execution-dashboard";
import { renderExecutionLoopDashboard, renderExecutionLoopTimeline } from "../execution-loop/execution-loop-dashboard";
import { renderEngineeringGraphDashboard } from "../engineering-graph/engineering-graph-dashboard";
import { renderBenchmarkDashboard } from "../benchmark/benchmark-dashboard";
import { renderDemoDashboard } from "../demo/demo-dashboard";
import { renderGovernanceDashboard } from "../governance/governance-dashboard";
import { renderOrganizationDashboard } from "../organization/organization-dashboard";
import { renderContextDashboard } from "../context/context-dashboard";
import { renderIntelligenceDashboard as renderPhase30Dashboard } from "../context/intelligence-dashboard";
import { renderLlmGatewayDashboard } from "../llm/llm-dashboard";
import { renderApprovalCard, renderRecoveredApprovalCard, type ApprovalCardHandlers } from "./approval-card";
import { renderAssistantChat, type AssistantChatHandlers } from "../assistant/chat-view";
import {
  renderModelSelector,
  renderModeToggle,
  renderProviderSettings,
  type AssistantSettingsHandlers,
} from "../assistant/settings-view";
import { renderAskAiButton } from "../assistant/web-context";
import { renderContextBundlePanel } from "../assistant/context-panel";
import {
  isOnboardingDeferred,
  isOnboardingVisible,
  renderOnboarding,
  renderOnboardingHint,
  type OnboardingHandlers,
} from "../assistant/onboarding";
import { renderDeveloperContext } from "../assistant/dev-context-view";
import type { WebContextBundle } from "../assistant/types";

export interface PanelHandlers
  extends ApprovalCardHandlers,
    AssistantSettingsHandlers,
    Partial<AssistantChatHandlers>,
    OnboardingHandlers {
  onReconfirm?: (requestId: string) => void;
  onApproveRecovered?: (requestId: string) => void;
  onConnect: () => void;
  onSelectProject: (project: string) => void;
  onToggleContextSelection?: (id: string) => void;
  /** Receives the bundle collected by the Ask AI click. Must not send it. */
  onAskAi?: (bundle: WebContextBundle) => void;
  onClearContext?: () => void;
  /** Phase 34 · decide whether the captured page goes with the next message. */
  onToggleContextInclude?: (include: boolean) => void;
}

const STATUS_TEXT: Record<string, string> = {
  unknown: "Not connected",
  connected: "Connected",
  offline: "Local Bridge unavailable",
  error: "Error",
};

export class Panel {
  private readonly doc: Document;
  private readonly handlers: PanelHandlers;
  private readonly root: HTMLElement;
  private projects: string[] = [];
  private collapsed = false;

  constructor(doc: Document, container: HTMLElement, handlers: PanelHandlers) {
    this.doc = doc;
    this.handlers = handlers;
    this.root = doc.createElement("div");
    this.root.className = "panel";
    container.appendChild(this.root);
  }

  setProjects(projects: string[]): void {
    this.projects = projects;
  }

  render(state: ExtensionState): void {
    this.root.className = `panel${this.collapsed ? " collapsed" : ""}`;
    this.root.textContent = "";
    this.root.append(
      this.renderHeader(state),
      this.renderStatus(state),
      this.renderToolbar(state),
      this.renderBody(state),
      this.renderFooter(state),
    );
  }

  private renderHeader(state: ExtensionState): HTMLElement {
    const header = this.doc.createElement("div");
    header.className = "header";

    const title = this.doc.createElement("span");
    title.className = "title";
    title.textContent = "ChatGPT Cursor Bridge";

    const toggle = this.doc.createElement("button");
    toggle.className = "icon-button";
    toggle.dataset.role = "toggle";
    toggle.textContent = this.collapsed ? "+" : "–";
    toggle.title = this.collapsed ? "Expand" : "Collapse";
    toggle.addEventListener("click", () => {
      this.collapsed = !this.collapsed;
      this.render(state);
    });

    header.append(title, toggle);
    return header;
  }

  private renderStatus(state: ExtensionState): HTMLElement {
    const grid = this.doc.createElement("div");
    grid.className = "status-grid";

    const addRow = (key: string, valueNode: Node) => {
      const k = this.doc.createElement("span");
      k.className = "status-key";
      k.textContent = key;
      const v = this.doc.createElement("span");
      v.className = "status-value";
      v.appendChild(valueNode);
      grid.append(k, v);
    };

    const bridge = this.doc.createElement("span");
    const dot = this.doc.createElement("span");
    dot.className = `dot ${state.bridgeStatus}`;
    bridge.append(dot, this.doc.createTextNode(STATUS_TEXT[state.bridgeStatus] ?? state.bridgeStatus));
    addRow("Bridge:", bridge);

    addRow("Project:", this.doc.createTextNode(state.currentProject ?? "none"));

    const pending = state.pendingActions.filter((item) => item.state === "pending").length;
    addRow("Pending Actions:", this.doc.createTextNode(String(pending + state.recoveredApprovals.length)));
    // Session counts are engineering telemetry: Developer Mode only (spec §2).
    if (state.uiMode === "developer") {
      addRow("Sessions:", this.doc.createTextNode(String(state.sessions.length)));
    }

    return grid;
  }

  private renderToolbar(state: ExtensionState): HTMLElement {
    const bar = this.doc.createElement("div");
    bar.className = "toolbar";

    const select = this.doc.createElement("select");
    select.dataset.role = "project-select";
    const placeholder = this.doc.createElement("option");
    placeholder.value = "";
    placeholder.textContent = this.projects.length ? "Select project" : "No projects";
    select.appendChild(placeholder);
    for (const name of this.projects) {
      const option = this.doc.createElement("option");
      option.value = name;
      option.textContent = name;
      option.selected = name === state.currentProject;
      select.appendChild(option);
    }
    select.addEventListener("change", () => {
      if (select.value) this.handlers.onSelectProject(select.value);
    });

    const connect = this.doc.createElement("button");
    connect.dataset.role = "connect";
    connect.textContent = state.bridgeStatus === "connected" ? "Refresh" : "Connect";
    connect.addEventListener("click", () => this.handlers.onConnect());

    bar.append(select, connect);
    return bar;
  }

  private renderBody(state: ExtensionState): HTMLElement {
    const body = this.doc.createElement("div");
    body.className = "body";

    // User Mode (the default) renders the assistant surfaces only. Developer
    // Mode adds the existing dashboards — read-only, exactly as before.
    body.appendChild(this.renderAssistantSurface(state));
    if (state.uiMode === "developer") body.appendChild(this.renderDeveloperSurface(state));

    if (state.bridgeStatus === "offline") {
      const warn = this.doc.createElement("div");
      warn.className = "empty";
      warn.textContent =
        "Local Bridge unavailable. Start it with: uvicorn app.main:app --port 8765";
      body.appendChild(warn);
    }

    // Approval controls are a Developer Mode surface (spec §2/§20: User Mode
    // renders no Approve/Apply control). The capability itself is untouched —
    // User Mode only points at it, and the queue keeps waiting for a human.
    if (state.uiMode === "user") {
      const waiting = state.pendingActions.filter((item) => item.state === "pending").length
        + state.recoveredApprovals.length;
      if (waiting > 0) {
        const hint = this.doc.createElement("div");
        hint.className = "empty";
        hint.dataset.role = "approval-hint";
        hint.textContent =
          `${waiting} action(s) waiting for approval. Switch to Developer Mode to review them.`;
        body.appendChild(hint);
      }
      return body;
    }

    for (const approval of state.recoveredApprovals) {
      body.appendChild(renderRecoveredApprovalCard(
        this.doc,
        approval,
        this.handlers.onReconfirm ?? (() => {}),
        this.handlers.onApproveRecovered ?? (() => {}),
      ));
    }

    if (state.pendingActions.length === 0 && state.recoveredApprovals.length === 0) {
      const empty = this.doc.createElement("div");
      empty.className = "empty";
      empty.textContent = "No actions captured yet.";
      body.appendChild(empty);
      return body;
    }

    const ordered = [...state.pendingActions].reverse();
    for (const item of ordered) {
      body.appendChild(
        renderApprovalCard(this.doc, item, {
          onApprove: this.handlers.onApprove,
          onReject: this.handlers.onReject,
        }),
      );
    }
    return body;
  }

  /**
   * The User Mode surface set (spec §2): chat, model selector, context,
   * history and settings. Nothing here executes, approves, applies or auto-fixes.
   *
   * Phase 34 renders the first-run guide **above** Chat rather than instead of
   * it, so the first surface a new user sees is still the chat panel and Skip is
   * always reachable.
   */
  private renderAssistantSurface(state: ExtensionState): HTMLElement {
    const surface = this.doc.createElement("div");
    surface.className = "assistant-surface";
    surface.dataset.role = "assistant-surface";
    surface.dataset.mode = state.uiMode;

    surface.appendChild(renderModeToggle(this.doc, state.uiMode, this.handlers));

    // Display state only: the guide unlocks nothing and stores no key.
    if (isOnboardingVisible(state.onboardingState)) {
      surface.appendChild(
        renderOnboarding(
          this.doc,
          {
            onboardingState: state.onboardingState,
            onboardingStep: state.onboardingStep,
            bridgeReachable: state.bridgeStatus === "connected",
            providerConfigured: state.assistantProviders.some((entry) => entry.status === "connected"),
          },
          this.handlers,
        ),
      );
    } else if (isOnboardingDeferred(state.onboardingState)) {
      surface.appendChild(renderOnboardingHint(this.doc, this.handlers));
    }

    const settingsState = {
      uiMode: state.uiMode,
      provider: state.assistantProvider,
      model: state.assistantModel,
      providers: state.assistantProviders,
      settings: state.assistantSettings,
      test: state.assistantProviderTest,
    };
    surface.appendChild(renderModelSelector(this.doc, settingsState, this.handlers));

    const context = this.doc.createElement("div");
    context.className = "assistant-context-block";
    // Collecting happens in this click handler and nowhere else.
    context.appendChild(renderAskAiButton(this.doc, { onAskAi: (bundle) => this.handlers.onAskAi?.(bundle) }));
    context.appendChild(
      renderContextBundlePanel(
        this.doc,
        {
          bundle: state.assistantWebContext,
          include: state.assistantContextInclude,
          project: state.currentProject,
          provider: state.assistantProvider,
          model: state.assistantModel,
          uiMode: state.uiMode,
          contextStatus: state.assistantContextStatus,
        },
        {
          onClearContext: () => this.handlers.onClearContext?.(),
          onToggleContextInclude: (include) => this.handlers.onToggleContextInclude?.(include),
        },
      ),
    );
    surface.appendChild(context);

    const active = state.assistantConversations.find((item) => item.id === state.assistantActiveConversation) ?? null;
    const lastTurn = active?.turns[active.turns.length - 1] ?? null;
    surface.appendChild(
      renderAssistantChat(
        this.doc,
        {
          uiMode: state.uiMode,
          conversations: state.assistantConversations,
          activeConversation: state.assistantActiveConversation,
          streaming: state.assistantStreaming,
          status: state.assistantStatus,
          query: state.assistantConversationQuery,
          renaming: state.assistantRenaming,
          draft: state.assistantDraft,
          // Retry is offered only after a failure, and only as a button.
          canRetry: lastTurn?.failed === true,
        },
        { ...this.handlers, onSend: this.handlers.onSend ?? (() => {}) },
      ),
    );

    surface.appendChild(renderProviderSettings(this.doc, settingsState, this.handlers));
    return surface;
  }

  /** Developer Mode extras. Every dashboard below is read-only. */
  private renderDeveloperSurface(state: ExtensionState): HTMLElement {
    const body = this.doc.createElement("div");
    body.className = "developer-surface";
    body.dataset.role = "developer-surface";

    body.appendChild(renderDeveloperContext(this.doc, state.assistantContextStatus));
    body.appendChild(renderWorkflowDashboard(this.doc, state.projectContext, {
      agents: state.agents,
      modelSelection: state.modelSelection,
    }));
    body.appendChild(renderRuntimeDashboard(this.doc, state.runtimes, state.tasks, state.runtimeEvents, state.qualityReport));
    body.appendChild(renderCollaborationDashboard(this.doc, state.teams, state.agents, state.dependencies, state.collaborationEvents));
    body.appendChild(renderProjectIntelligenceDashboard(this.doc, state.projectProfile, state.projectGraph, state.impactReport, state.projectMemoryHistory));
    body.appendChild(renderContextDashboard(this.doc, state.devContext, state.devContextSelection, (id) => {
      this.handlers.onToggleContextSelection?.(id);
    }));
    body.appendChild(renderPhase30Dashboard(this.doc, state.phase30Intelligence));
    body.appendChild(
      renderLlmGatewayDashboard(this.doc, {
        providers: state.llmProviders,
        models: state.llmModels,
        conversations: state.llmConversations,
        toolProposals: state.llmToolProposals,
        readOnly: true,
      }),
    );
    body.appendChild(renderIntelligenceDashboard(this.doc, state.intelligenceInsights, state.intelligenceProposals, state.intelligenceDecisions, state.intelligenceQuality, {
      project: state.currentProject ?? "",
      observations: state.intelligenceObservations,
      patterns: state.intelligencePatterns,
      predictions: state.intelligencePredictions,
      recommendations: state.intelligenceRecommendations,
      outcomes: state.intelligenceOutcomes,
      knowledge: state.intelligenceKnowledge,
      evidence: state.intelligenceEvidence,
      quality: state.intelligenceQuality11,
      readOnly: true,
    }, {
      project: state.currentProject ?? "",
      trends: state.intelligenceTrends,
      correlations: state.intelligenceCorrelations,
      impact: state.intelligenceImpactPredictions,
      dependencies: state.intelligenceDependencyRisks,
      ranking: state.intelligenceRecommendationRanking,
      evaluations: state.intelligenceEvaluations,
      metrics: state.intelligenceEvaluationMetrics,
      evidenceGraph: state.intelligenceEvidenceGraph,
      readOnly: true,
    }, state.intelligenceValidation, state.intelligenceGovernance));
    body.appendChild(renderSimulationDashboard(this.doc, state.simulation, state.simulationScenarios, state.simulationEvaluations, state.simulationPlans, state.simulationQuality));
    body.appendChild(renderExecutionDashboard(this.doc, state.executionTasks, state.executionProposals, state.executionResults, state.executionQuality7));
    body.appendChild(renderExecutionLoopDashboard(this.doc, state.executionLoops, state.executionLoopQuality8, {
      dags: state.executionDags,
      dagReady: state.executionDagReady,
      metrics: state.engineeringMetrics,
      context: state.executionLoopContext,
    }));
    if (state.executionLoops[0]) {
      body.appendChild(renderExecutionLoopTimeline(this.doc, state.executionLoops[0].id, state.executionLoopTimeline));
    }
    body.appendChild(renderEngineeringGraphDashboard(this.doc, {
      graph: state.engineeringGraph,
      failures: state.failurePatterns,
      timeline: state.evolutionTimeline,
      capabilities: state.agentCapabilityMetrics,
    }));
    body.appendChild(renderBenchmarkDashboard(this.doc, {
      benchmarks: state.benchmarks,
      results: [],
      failurePatterns: state.failurePatterns,
      capabilities: state.agentCapabilityMetrics,
    }));
    body.appendChild(renderDemoDashboard(this.doc, {
      scenarios: state.demoScenarios,
      flow: state.demoFlow,
      replays: state.replays,
      artifacts: state.artifacts,
    }));
    body.appendChild(renderGovernanceDashboard(this.doc, {
      health: state.governanceHealth,
      drift: state.governanceDrift,
      debt: state.governanceDebt,
      policies: state.governancePolicies,
      timeline: state.governanceTimeline,
      quality9: state.governanceQuality9,
    }));
    body.appendChild(renderOrganizationDashboard(this.doc, {
      health: state.organizationHealth,
      dashboard: state.organizationDashboard,
      learning: state.organizationLearning,
      quality10: state.organizationQuality10,
      impact: state.organizationStrategyImpact,
      risk: state.organizationStrategyRisk,
      strategies: state.organizationStrategies,
      recommendations: state.organizationRecommendations,
      context: state.organizationStrategyContext,
    }));

    return body;
  }

  private renderFooter(state: ExtensionState): HTMLElement {
    const footer = this.doc.createElement("div");
    footer.className = "footer";
    footer.textContent = state.lastResult ?? "Every action requires explicit approval.";
    return footer;
  }
}
