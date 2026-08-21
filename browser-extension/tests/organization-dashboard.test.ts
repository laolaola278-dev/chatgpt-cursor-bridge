import { describe, expect, it, vi } from "vitest";

import { BridgeClient } from "../src/bridge/client";
import { renderOrganizationDashboard } from "../src/organization/organization-dashboard";
import type {
  OrgDashboardResponse,
  OrgGraphResponse,
  OrgHealthReport,
  OrgImpactReport,
  OrgIncidentsResponse,
  OrgLearningResponse,
  OrgRecommendationsResponse,
  OrgRiskReport,
  OrgSimulationDetail,
  OrgStrategyContext,
  OrgStrategyListResponse,
  QualityGate10Response,
} from "../src/organization/models";

const graph: OrgGraphResponse = {
  company: { id: "org_comp_1", type: "COMPANY", name: "Acme Inc", parentId: null, metadata: {}, createdAt: "2026-01-01T00:00:00Z", readOnly: true },
  teams: [{ id: "org_team_1", type: "TEAM", name: "Platform", parentId: "org_comp_1", metadata: {}, createdAt: "2026-01-01T00:00:00Z", readOnly: true }],
  projects: [{ id: "org_proj_1", type: "PROJECT", name: "checkout", parentId: "org_team_1", metadata: {}, createdAt: "2026-01-01T00:00:00Z", readOnly: true }],
  services: [],
  repositories: [],
  decisions: [],
  incidents: [],
  readOnly: true,
};

const health: OrgHealthReport = {
  org: "organization",
  orgHealthScore: 78,
  projectCount: 2,
  healthByProject: [
    { project: "alpha", healthScore: 90, riskLevel: "low" },
    { project: "beta", healthScore: 66, riskLevel: "medium" },
  ],
  debtRanking: [{ project: "beta", openDebt: 8, estimatedCost: 40 }],
  riskTrends: [{ project: "beta", healthScore: 66, delta: -12, direction: "declining" }],
  failurePatterns: [{ project: "alpha", category: "cache", signature: "Redis cache invalidation failure", occurrences: 3, severity: "high" }],
  agentEffectiveness: [{ agentCount: 2, completionRate: 0.9, averageQuality: 85, effectivenessScore: 87 }],
  warnings: [{ code: "project_health_declining", severity: "medium", message: "Project beta health is 66/100 (medium)" }],
  recommendations: [{ code: "monitor_declining", priority: "medium", suggestion: "Review recent executions for the declining projects" }],
  createdAt: "2026-01-01T00:00:00Z",
  readOnly: true,
};

const dashboard: OrgDashboardResponse = {
  graph,
  patterns: [{ id: "pat_1", category: "successful_refactor", name: "Gateway interface", summary: "decoupled checkout", project: "checkout", tags: [], createdAt: "2026-01-01T00:00:00Z", readOnly: true }],
  incidents: [{ id: "inci_1", project: "alpha", service: "", title: "Redis cache failure", summary: "stale keys", severity: "high", signature: "cache", status: "OPEN", createdAt: "2026-01-01T00:00:00Z", readOnly: true }],
  decisions: [],
  categories: ["successful_refactor", "bad_migration", "deployment_failure", "architecture_success"],
  readOnly: true,
};

const learning: OrgLearningResponse = {
  project: "beta",
  matches: [{ sourceProject: "alpha", targetProject: "beta", category: "cache", signature: "Redis cache invalidation failure", matchScore: 1, message: "Similar failure detected from alpha", readOnly: true }],
  readOnly: true,
};

const quality10: QualityGate10Response = {
  organization: "organization",
  orgHealthScore: 78,
  projectCount: 2,
  openIncidents: 1,
  criticalProjects: 0,
  recommendations: ["monitor_declining"],
  blockingIssues: [],
  quality: 73,
  readOnly: true,
};

function render(overrides: Partial<Parameters<typeof renderOrganizationDashboard>[1]> = {}) {
  return renderOrganizationDashboard(document, {
    health,
    dashboard,
    learning,
    quality10,
    ...overrides,
  });
}

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("organization dashboard", () => {
  it.each(Array.from({ length: 20 }, (_, index) => index))("renders read-only command center case %i", () => {
    const root = render();
    expect(root.dataset.role).toBe("organization-dashboard");
    expect(root.textContent).toContain("ORG READ ONLY");
    expect(root.textContent).toContain("Engineering Command Center");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders org health and debt ranking case %i", () => {
    const root = render();
    expect(root.textContent).toContain("78/100");
    expect(root.textContent).toContain("2 project(s)");
    expect(root.textContent).toContain("Technical Debt Ranking");
    expect(root.textContent).toContain("beta · 8 open · est 40h");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders graph and patterns case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Acme Inc");
    expect(root.textContent).toContain("Platform: checkout");
    expect(root.textContent).toContain("Engineering Pattern Library");
    expect(root.textContent).toContain("Gateway interface");
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders learning and incidents case %i", () => {
    const root = render();
    expect(root.textContent).toContain("Cross-Project Learning");
    expect(root.textContent).toContain("Similar failure detected from alpha");
    expect(root.textContent).toContain("Redis cache failure");
  });

  it("renders quality gate 10", () => {
    const root = render();
    expect(root.textContent).toContain("Quality Gate 10.0");
    expect(root.textContent).toContain("73/100");
  });

  it("renders an empty read-only state", () => {
    const root = renderOrganizationDashboard(document, { health: null, dashboard: null, learning: null, quality10: null });
    expect(root.textContent).toContain("No organization data yet");
    expect(root.querySelector("button")).toBeNull();
  });
});

describe("organization bridge client", () => {
  it("loads the org graph with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/graph");
      return response(graph);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationGraph();
    expect(result.company?.name).toBe("Acme Inc");
    expect(result.readOnly).toBe(true);
  });

  it("loads organization health with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/health");
      return response(health);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationHealth();
    expect(result.orgHealthScore).toBe(78);
    expect(result.projectCount).toBe(2);
  });

  it("loads the org dashboard with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/dashboard");
      return response(dashboard);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationDashboard();
    expect(result.categories).toContain("successful_refactor");
  });

  it("loads patterns and incidents with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/patterns");
      return response({ patterns: dashboard.patterns, readOnly: true });
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationPatterns();
    expect(result.patterns[0].category).toBe("successful_refactor");

    const fetchImpl2 = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/incidents?project=alpha");
      return response({ incidents: dashboard.incidents, readOnly: true } as OrgIncidentsResponse);
    });
    const incidents = await new BridgeClient({ fetchImpl: fetchImpl2 as unknown as typeof fetch }).organizationIncidents("alpha");
    expect(incidents.incidents[0].status).toBe("OPEN");
  });

  it("loads cross-project learning with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/learning/similar?project=beta");
      return response(learning);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationLearningSimilar("beta");
    expect(result.matches[0].message).toContain("Similar failure detected from alpha");
  });

  it("loads quality gate 10 with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/quality/v10/organization");
      return response(quality10);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationQuality10("organization");
    expect(result.quality).toBe(73);
    expect(result.blockingIssues).toEqual([]);
  });

  it("does not expose organization write methods", () => {
    const client = new BridgeClient();
    expect("organizationEntityCreate" in client).toBe(false);
    expect("organizationIncidentCreate" in client).toBe(false);
    expect("organizationPatternCreate" in client).toBe(false);
    expect("organizationLearningScan" in client).toBe(false);
    expect("organizationDecisionCreate" in client).toBe(false);
  });
});

describe("organization strategy dashboard (phase 24)", () => {
  const impact: OrgImpactReport = {
    id: "imp_1",
    source_node: "s1",
    affected_projects: ["checkout", "payments"],
    affected_teams: ["Platform"],
    affected_services: ["payments-api"],
    dependency_paths: [["checkout-api", "checkout-repo", "payments-api"]],
    risk_level: "high",
    impact_score: 72,
    confidence: 0.8,
    blocking_issues: ["shared repository checkout-repo affected"],
    createdAt: "2026-01-01T00:00:00Z",
    readOnly: true,
  };

  const risk: OrgRiskReport = {
    risk_id: "risk_1",
    source: "s1",
    severity: "high",
    likelihood: "high",
    propagation_path: [{ node: "checkout-repo", via: "DEPENDS_ON", severity: "high", path: ["checkout-api", "checkout-repo"] }],
    affected_nodes: [{ id: "r1", name: "checkout-repo", type: "REPOSITORY", severity: "high" }],
    affected_projects: ["checkout", "payments"],
    affected_teams: ["Platform"],
    impact: "high",
    confidence: 0.75,
    recommendations: ["Require human approval before touching the shared repository"],
    readOnly: true,
  };

  const strategyList: OrgStrategyListResponse = {
    project: "checkout",
    strategies: [
      {
        strategy_id: "ostrat_1",
        strategy_type: "STANDARDIZATION",
        title: "Unify authentication",
        problem: "auth fragmentation",
        affected_projects: ["checkout", "payments"],
        affected_teams: ["Platform"],
        benefits: ["one shared approach"],
        risks: ["touchpoints"],
        estimated_effort: "4-7 person-weeks",
        confidence: 0.8,
        priority: "high",
        alternatives: ["status quo"],
        evidence: ["checkout: healthScore 60"],
        status: "SELECTED",
        createdAt: "2026-01-01T00:00:00Z",
        readOnly: true,
      },
    ],
    readOnly: true,
  };

  const recommendations: OrgRecommendationsResponse = {
    recommendations: [
      {
        recommendation_id: "rec_1",
        problem: "repeated cache failures",
        evidence: ["checkout cache ×3"],
        recommendation: "Standardize cache provider",
        expected_benefit: "fewer incidents",
        risk: "migration effort",
        confidence: 0.7,
        affected_projects: ["checkout", "payments"],
        affected_teams: ["Platform"],
        alternatives: ["status quo"],
        readOnly: true,
      },
    ],
    readOnly: true,
  };

  const context: OrgStrategyContext = {
    organization: "organization",
    graph: { nodes: [], edges: [], readOnly: true },
    organization_health: [{ project: "checkout", healthScore: 66, riskLevel: "medium" }],
    active_risks: [],
    cross_project_impacts: [],
    active_strategies: [],
    pending_decisions: [
      {
        decision_id: "ostdec_1",
        organization_id: "organization",
        title: "Adopt unified auth",
        source_graph_nodes: ["s1"],
        selected_strategy: "ostrat_1",
        alternatives: [],
        confidence: 0.8,
        impact_report: {},
        risk_report: {},
        status: "APPROVAL_REQUIRED",
        history: [],
        createdAt: "2026-01-01T00:00:00Z",
        readOnly: true,
      },
    ],
    technical_debt: {},
    architecture_drift: {},
    recommendations: [],
    readOnly: true,
  };

  const strategyData = {
    health: null,
    dashboard: null,
    learning: null,
    quality10: null,
    impact,
    risk,
    strategies: strategyList,
    recommendations,
    context,
  };

  function renderStrategy(overrides: Partial<typeof strategyData> = {}) {
    return renderOrganizationDashboard(document, { ...strategyData, ...overrides });
  }

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders cross-project impact read-only case %i", () => {
    const root = renderStrategy();
    expect(root.textContent).toContain("Cross-Project Impact");
    expect(root.textContent).toContain("impact 72/100");
    expect(root.textContent).toContain("payments");
    expect(root.textContent).toContain("shared repository");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders risk propagation read-only case %i", () => {
    const root = renderStrategy();
    expect(root.textContent).toContain("Risk Propagation");
    expect(root.textContent).toContain("high/high");
    expect(root.textContent).toContain("Require human approval");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders active strategies and recommendations case %i", () => {
    const root = renderStrategy();
    expect(root.textContent).toContain("Active Strategies");
    expect(root.textContent).toContain("Unify authentication");
    expect(root.textContent).toContain("Strategic Recommendations");
    expect(root.textContent).toContain("Standardize cache provider");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 20 }, (_, index) => index))("renders pending decisions from context case %i", () => {
    const root = renderStrategy();
    expect(root.textContent).toContain("Pending Decisions");
    expect(root.textContent).toContain("Adopt unified auth");
    expect(root.textContent).toContain("APPROVAL_REQUIRED");
    expect(root.querySelector("button")).toBeNull();
  });

  it.each(Array.from({ length: 10 }, (_, index) => index))("has no execute/apply/fix/rollback/auto-approve controls case %i", () => {
    const root = renderStrategy();
    const text = root.textContent ?? "";
    expect(text).not.toMatch(/execute|apply|fix|rollback|auto approve/i);
    expect(root.querySelector("button")).toBeNull();
    expect(root.querySelector("input")).toBeNull();
  });

  it("renders empty state when only strategy data is missing", () => {
    const root = renderOrganizationDashboard(document, {
      health: null, dashboard: null, learning: null, quality10: null,
      impact: null, risk: null, strategies: null, recommendations: null, context: null,
    });
    expect(root.textContent).toContain("No organization data yet");
    expect(root.querySelector("button")).toBeNull();
  });

  it("does not render strategy sections without data", () => {
    const root = renderOrganizationDashboard(document, {
      health, dashboard, learning, quality10,
      impact: null, risk: null, strategies: null, recommendations: null, context: null,
    });
    expect(root.textContent).not.toContain("Cross-Project Impact");
    expect(root.textContent).not.toContain("Risk Propagation");
    expect(root.textContent).not.toContain("Strategic Recommendations");
  });

  it("loads cross-project impact with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/impact/");
      return response(impact);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationImpact("s1");
    expect(result.impact_score).toBe(72);
    expect(result.readOnly).toBe(true);
  });

  it("loads risk propagation with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/risk/s1?severity=high&likelihood=high");
      return response(risk);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationRisk("s1", "high", "high");
    expect(result.risk_id).toBe("risk_1");
    expect(result.readOnly).toBe(true);
  });

  it("loads strategy list with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/strategies/checkout");
      return response(strategyList);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationStrategies("checkout");
    expect(result.strategies[0].strategy_type).toBe("STANDARDIZATION");
  });

  it("loads recommendations with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/recommendations");
      return response(recommendations);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationRecommendations();
    expect(result.recommendations[0].recommendation).toContain("Standardize");
  });

  it("loads strategy detail with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/strategy/ostrat_1");
      return response(strategyList.strategies[0]);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationStrategyDetail("ostrat_1");
    expect(result.strategy_id).toBe("ostrat_1");
  });

  it("loads decision detail with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/decision/ostdec_1");
      return response(context.pending_decisions[0]);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationDecisionDetail("ostdec_1");
    expect(result.status).toBe("APPROVAL_REQUIRED");
  });

  it("loads simulation detail with GET", async () => {
    const simulation: OrgSimulationDetail = {
      simulation_id: "ostsim_1",
      strategy_id: "ostrat_1",
      strategy_type: "MIGRATION",
      predictions: { risk: 0.7, cost: 0.5 },
      createdAt: "2026-01-01T00:00:00Z",
      readOnly: true,
    };
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/simulation/ostsim_1");
      return response(simulation);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationSimulationDetail("ostsim_1");
    expect(result.predictions.risk).toBe(0.7);
  });

  it("loads organization strategy context with GET", async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain("/organization/context");
      return response(context);
    });
    const result = await new BridgeClient({ fetchImpl: fetchImpl as unknown as typeof fetch }).organizationContext();
    expect(result.readOnly).toBe(true);
    expect(result.pending_decisions[0].title).toContain("Adopt unified auth");
  });

  it("does not expose strategy write methods on the client", () => {
    const client = new BridgeClient();
    expect("organizationStrategyCreate" in client).toBe(false);
    expect("organizationStrategyEvaluate" in client).toBe(false);
    expect("organizationMemoryAppend" in client).toBe(false);
  });
});
