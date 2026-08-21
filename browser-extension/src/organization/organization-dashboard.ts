import type {
  OrgDashboardResponse,
  OrgHealthReport,
  OrgImpactReport,
  OrgLearningResponse,
  OrgRecommendationsResponse,
  OrgRiskReport,
  OrgStrategyContext,
  OrgStrategyListResponse,
  QualityGate10Response,
} from "./models";

export interface OrganizationDashboardData {
  health: OrgHealthReport | null;
  dashboard: OrgDashboardResponse | null;
  learning: OrgLearningResponse | null;
  quality10: QualityGate10Response | null;
  impact?: OrgImpactReport | null;
  risk?: OrgRiskReport | null;
  strategies?: OrgStrategyListResponse | null;
  recommendations?: OrgRecommendationsResponse | null;
  context?: OrgStrategyContext | null;
}

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `organization-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

function block(doc: Document, title: string): HTMLElement {
  const wrapper = doc.createElement("div");
  wrapper.className = "organization-block";
  const heading = doc.createElement("h4");
  heading.textContent = title;
  wrapper.appendChild(heading);
  return wrapper;
}

/** Read-only Engineering Command Center: org health, debt ranking, risk trends, patterns, incidents, learning. */
export function renderOrganizationDashboard(doc: Document, data: OrganizationDashboardData): HTMLElement {
  const root = doc.createElement("section");
  root.className = "organization-dashboard";
  root.dataset.role = "organization-dashboard";
  const heading = doc.createElement("div");
  heading.className = "organization-heading";
  const title = doc.createElement("strong");
  title.textContent = "Engineering Command Center";
  const badge = doc.createElement("span");
  badge.className = "organization-badge";
  badge.textContent = "ORG READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  const { health, dashboard, learning, quality10, impact, risk, strategies, recommendations, context } = data;
  if (!health && !dashboard && !learning && !quality10 && !impact && !risk && !strategies && !recommendations && !context) {
    root.appendChild(line(doc, "No organization data yet. Register projects in the org graph to begin."));
    return root;
  }

  // Organization health score.
  if (health) {
    const healthBlock = block(doc, "Organization Health");
    const stats = doc.createElement("div");
    stats.className = "organization-stats";
    const scoreNode = doc.createElement("div");
    scoreNode.className = "organization-score";
    scoreNode.textContent = `${health.orgHealthScore}/100`;
    const countNode = doc.createElement("div");
    countNode.className = "organization-score";
    countNode.textContent = `${health.projectCount} project(s)`;
    stats.append(scoreNode, countNode);
    healthBlock.appendChild(stats);
    for (const item of health.healthByProject.slice(0, 5)) {
      healthBlock.appendChild(line(doc, `${item.project} · ${item.healthScore}/100 · ${item.riskLevel}`, item.riskLevel === "high" ? "warning" : item.riskLevel === "medium" ? "pending" : ""));
    }
    for (const trend of health.riskTrends.slice(0, 3)) {
      const arrow = trend.direction === "improving" ? "▲" : trend.direction === "declining" ? "▼" : "■";
      healthBlock.appendChild(line(doc, `${arrow} ${trend.project} ${trend.delta > 0 ? "+" : ""}${trend.delta}`, trend.direction === "declining" ? "warning" : ""));
    }
    for (const warning of health.warnings.slice(0, 3)) {
      healthBlock.appendChild(line(doc, `⚠ ${warning.message}`, "warning"));
    }
    root.appendChild(healthBlock);
  }

  // Debt ranking.
  if (health && health.debtRanking.length) {
    const debtBlock = block(doc, "Technical Debt Ranking");
    for (const item of health.debtRanking.slice(0, 5)) {
      debtBlock.appendChild(line(doc, `${item.project} · ${item.openDebt} open · est ${item.estimatedCost}h`));
    }
    root.appendChild(debtBlock);
  }

  // Organization graph (teams → projects).
  if (dashboard?.graph) {
    const graphBlock = block(doc, "Organization Graph");
    const company = dashboard.graph.company ? `${dashboard.graph.company.name}` : "No company registered";
    graphBlock.appendChild(line(doc, `${company} · ${dashboard.graph.teams.length} team(s) · ${dashboard.graph.projects.length} project(s)`));
    for (const team of dashboard.graph.teams.slice(0, 3)) {
      const projects = dashboard.graph.projects.filter((project) => project.parentId === team.id);
      graphBlock.appendChild(line(doc, `${team.name}: ${projects.map((project) => project.name).join(", ") || "no projects"}`));
    }
    root.appendChild(graphBlock);
  }

  // Failure patterns + cross-project learning.
  if (health && health.failurePatterns.length) {
    const patternBlock = block(doc, "Failure Patterns");
    for (const pattern of health.failurePatterns.slice(0, 4)) {
      patternBlock.appendChild(line(doc, `${pattern.project} · ${pattern.category} · ${pattern.signature} ×${pattern.occurrences}`, pattern.severity === "high" ? "warning" : ""));
    }
    root.appendChild(patternBlock);
  }
  if (learning && learning.matches.length) {
    const learningBlock = block(doc, "Cross-Project Learning");
    for (const match of learning.matches.slice(0, 4)) {
      learningBlock.appendChild(line(doc, `${match.message} (score ${match.matchScore})`, "warning"));
    }
    root.appendChild(learningBlock);
  }

  // Pattern library.
  if (dashboard && dashboard.patterns.length) {
    const libraryBlock = block(doc, "Engineering Pattern Library");
    for (const pattern of dashboard.patterns.slice(0, 4)) {
      libraryBlock.appendChild(line(doc, `${pattern.category} · ${pattern.name} · ${pattern.project}`));
    }
    root.appendChild(libraryBlock);
  }

  // Incidents + Quality Gate 10.
  if (dashboard && dashboard.incidents.length) {
    const incidentBlock = block(doc, "Incidents");
    for (const incident of dashboard.incidents.slice(0, 3)) {
      incidentBlock.appendChild(line(doc, `${incident.status} · ${incident.project} · ${incident.title}`, incident.severity === "high" ? "warning" : ""));
    }
    root.appendChild(incidentBlock);
  }
  if (quality10) {
    const qualityBlock = block(doc, "Quality Gate 10.0");
    qualityBlock.appendChild(line(doc, `Quality ${quality10.quality}/100 · health ${quality10.orgHealthScore} · ${quality10.openIncidents} incident(s)`));
    for (const issue of quality10.blockingIssues.slice(0, 3)) qualityBlock.appendChild(line(doc, `blocked: ${issue}`, "warning"));
    if (!quality10.blockingIssues.length) qualityBlock.appendChild(line(doc, "No blocking issues", "pass"));
    root.appendChild(qualityBlock);
  }

  // Cross-project impact analysis (read-only).
  if (impact) {
    const impactBlock = block(doc, "Cross-Project Impact");
    const stats = doc.createElement("div");
    stats.className = "organization-stats";
    const scoreNode = doc.createElement("div");
    scoreNode.className = "organization-score";
    scoreNode.textContent = `impact ${impact.impact_score}/100`;
    const levelNode = doc.createElement("div");
    levelNode.className = "organization-score";
    levelNode.textContent = `risk ${impact.risk_level} · confidence ${impact.confidence}`;
    stats.append(scoreNode, levelNode);
    impactBlock.appendChild(stats);
    impactBlock.appendChild(line(doc, `source: ${impact.source_node} · projects: ${impact.affected_projects.join(", ") || "none"}`));
    impactBlock.appendChild(line(doc, `teams: ${impact.affected_teams.join(", ") || "none"} · services: ${impact.affected_services.join(", ") || "none"}`));
    for (const path of impact.dependency_paths.slice(0, 3)) {
      impactBlock.appendChild(line(doc, `path: ${path.join(" → ")}`));
    }
    for (const issue of impact.blocking_issues.slice(0, 3)) {
      impactBlock.appendChild(line(doc, `⚠ ${issue}`, "warning"));
    }
    root.appendChild(impactBlock);
  }

  // Risk propagation (read-only).
  if (risk) {
    const riskBlock = block(doc, "Risk Propagation");
    riskBlock.appendChild(line(doc, `${risk.source} · ${risk.severity}/${risk.likelihood} · impact ${risk.impact} · confidence ${risk.confidence}`, risk.severity === "high" ? "warning" : risk.severity === "medium" ? "pending" : ""));
    for (const entry of risk.propagation_path.slice(0, 3)) {
      riskBlock.appendChild(line(doc, `${entry.node} via ${entry.via} (${entry.severity})`));
    }
    for (const node of risk.affected_nodes.slice(0, 4)) {
      riskBlock.appendChild(line(doc, `affects ${node.name} (${node.type}) · ${node.severity}`, node.severity === "high" ? "warning" : ""));
    }
    for (const recommendation of risk.recommendations.slice(0, 2)) {
      riskBlock.appendChild(line(doc, `→ ${recommendation}`));
    }
    root.appendChild(riskBlock);
  }

  // Active strategies + pending decisions.
  if (strategies && strategies.strategies.length) {
    const strategyBlock = block(doc, "Active Strategies");
    for (const strategy of strategies.strategies.slice(0, 5)) {
      strategyBlock.appendChild(line(doc, `${strategy.strategy_type} · ${strategy.title} · ${strategy.status} · confidence ${strategy.confidence}`, strategy.status === "SELECTED" ? "pass" : strategy.priority === "high" ? "pending" : ""));
    }
    root.appendChild(strategyBlock);
  }
  if (context && context.pending_decisions.length) {
    const decisionBlock = block(doc, "Pending Decisions");
    for (const decision of context.pending_decisions.slice(0, 4)) {
      decisionBlock.appendChild(line(doc, `${decision.status} · ${decision.title} · confidence ${decision.confidence}`, "pending"));
    }
    root.appendChild(decisionBlock);
  }

  // Strategic recommendations (read-only).
  if (recommendations && recommendations.recommendations.length) {
    const recommendationBlock = block(doc, "Strategic Recommendations");
    for (const recommendation of recommendations.recommendations.slice(0, 4)) {
      recommendationBlock.appendChild(line(doc, `${recommendation.problem} — ${recommendation.recommendation} (confidence ${recommendation.confidence})`));
      recommendationBlock.appendChild(line(doc, `  benefit: ${recommendation.expected_benefit} · risk: ${recommendation.risk}`));
    }
    root.appendChild(recommendationBlock);
  }

  return root;
}
