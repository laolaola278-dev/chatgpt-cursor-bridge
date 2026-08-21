import type {
  EngineeringDecision,
  EngineeringInsight,
  EngineeringProposal,
  IntelligenceEvidenceBundle,
  IntelligenceEvolutionResponse,
  IntelligencePhase26Response,
  IntelligencePhase27Response,
  IntelligencePhase28Response,
  IntelligenceQuality5,
} from "./models";

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `engineering-intelligence-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

export function renderIntelligenceDashboard(
  doc: Document,
  insights: EngineeringInsight[],
  proposals: EngineeringProposal[],
  decisions: EngineeringDecision[],
  quality: IntelligenceQuality5 | null,
  evolution?: Partial<IntelligenceEvolutionResponse> | null,
  phase26?: Partial<IntelligencePhase26Response> | null,
  phase27?: Partial<IntelligencePhase27Response> | null,
  phase28?: Partial<IntelligencePhase28Response> | null,
): HTMLElement {
  const root = doc.createElement("section");
  root.className = "engineering-intelligence-dashboard";
  root.dataset.role = "engineering-intelligence-dashboard";
  const heading = doc.createElement("div");
  heading.className = "engineering-intelligence-heading";
  const title = doc.createElement("strong");
  title.textContent = "Engineering Intelligence";
  const badge = doc.createElement("span");
  badge.className = "engineering-intelligence-badge";
  badge.textContent = "ANALYSIS · READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  const summary = doc.createElement("div");
  summary.className = "engineering-intelligence-summary";
  summary.append(
    line(doc, `${insights.length} insights`),
    line(doc, `${proposals.length} proposals`),
    line(doc, `${decisions.length} decisions`),
    line(doc, quality ? `Quality ${quality.quality}/100` : "Quality pending"),
  );
  root.appendChild(summary);

  const blocks = doc.createElement("div");
  blocks.className = "engineering-intelligence-blocks";
  const insightBlock = doc.createElement("div");
  insightBlock.className = "engineering-intelligence-block";
  const insightTitle = doc.createElement("h4");
  insightTitle.textContent = "Risk signals";
  insightBlock.appendChild(insightTitle);
  for (const insight of insights.slice(0, 4)) {
    insightBlock.appendChild(line(doc, `${insight.severity.toUpperCase()} · ${insight.title}`, insight.severity === "high" || insight.severity === "critical" ? "warning" : ""));
  }
  if (!insights.length) insightBlock.appendChild(line(doc, "No analyzed risks yet"));
  blocks.appendChild(insightBlock);

  const proposalBlock = doc.createElement("div");
  proposalBlock.className = "engineering-intelligence-block";
  const proposalTitle = doc.createElement("h4");
  proposalTitle.textContent = "Active proposals";
  proposalBlock.appendChild(proposalTitle);
  for (const proposal of proposals.slice(0, 4)) proposalBlock.appendChild(line(doc, `${proposal.type} · ${proposal.risk} (${proposal.riskScore})`));
  if (!proposals.length) proposalBlock.appendChild(line(doc, "No proposals yet"));
  blocks.appendChild(proposalBlock);

  const decisionBlock = doc.createElement("div");
  decisionBlock.className = "engineering-intelligence-block";
  const decisionTitle = doc.createElement("h4");
  decisionTitle.textContent = "Pending decisions";
  decisionBlock.appendChild(decisionTitle);
  for (const decision of decisions.slice(0, 4)) decisionBlock.appendChild(line(doc, `${decision.status} · ${decision.title}`));
  if (!decisions.length) decisionBlock.appendChild(line(doc, "No decisions recorded"));
  blocks.appendChild(decisionBlock);
  root.appendChild(blocks);

  if (quality) {
    const debt = doc.createElement("small");
    debt.className = "engineering-intelligence-debt";
    debt.textContent = `Technical debt ${quality.technicalDebt.score}/100 · ${quality.technicalDebt.items} item(s) · Risk ${quality.risk}`;
    root.appendChild(debt);
  }

  // Phase 25 timeline: deliberately text-only. There are no controls for
  // approval, application, execution, or source changes in this component.
  if (evolution) {
    const evolutionHeading = doc.createElement("h4");
    evolutionHeading.className = "engineering-intelligence-evolution-title";
    evolutionHeading.textContent = "Observation → Pattern → Prediction";
    root.appendChild(evolutionHeading);

    const evolutionSummary = doc.createElement("div");
    evolutionSummary.className = "engineering-intelligence-evolution-summary";
    evolutionSummary.append(
      line(doc, `${evolution.observations?.length ?? 0} observations`),
      line(doc, `${evolution.patterns?.length ?? 0} patterns`),
      line(doc, `${evolution.predictions?.length ?? 0} predictions`),
      line(doc, `${evolution.recommendations?.length ?? 0} recommendations`),
      line(doc, `${evolution.outcomes?.length ?? 0} outcomes`),
      line(doc, `${evolution.knowledge?.length ?? 0} knowledge records`),
      line(doc, `${evolution.evidence?.length ?? 0} evidence bundles`),
    );
    root.appendChild(evolutionSummary);

    const evolutionBlock = doc.createElement("div");
    evolutionBlock.className = "engineering-intelligence-evolution-block";
    for (const observation of (evolution.observations ?? []).slice(0, 3)) {
      evolutionBlock.appendChild(line(doc, `${observation.timestamp} · ${observation.type} · ${observation.summary}`));
    }
    for (const prediction of (evolution.predictions ?? []).slice(0, 4)) {
      const risk = prediction.risk_level ?? prediction.riskLevel ?? "medium";
      evolutionBlock.appendChild(line(doc, `${risk.toUpperCase()} · ${prediction.prediction_type ?? prediction.predictionType} · confidence ${prediction.confidence}`, risk === "high" || risk === "critical" ? "warning" : ""));
    }
    for (const recommendation of (evolution.recommendations ?? []).slice(0, 3)) {
      evolutionBlock.appendChild(line(doc, `→ ${recommendation.recommendation}`, "recommendation"));
    }
    if (!evolutionBlock.childElementCount) evolutionBlock.appendChild(line(doc, "No evidence-backed intelligence signals yet"));
    root.appendChild(evolutionBlock);

    const learningBlock = doc.createElement("div");
    learningBlock.className = "engineering-intelligence-evolution-block";
    for (const outcome of (evolution.outcomes ?? []).slice(0, 3)) {
      learningBlock.appendChild(line(doc, `Outcome · ${outcome.status} · ${outcome.actual_outcome}`));
    }
    for (const knowledge of (evolution.knowledge ?? []).slice(0, 3)) {
      learningBlock.appendChild(line(doc, `Knowledge · ${knowledge.category} · confidence ${knowledge.confidence}`));
    }
    for (const bundle of ((evolution.evidence ?? []) as IntelligenceEvidenceBundle[]).slice(0, 3)) {
      learningBlock.appendChild(line(doc, `Evidence · ${bundle.bundle_id} · ${bundle.observation_ids.length} observation(s)`));
    }
    if (learningBlock.childElementCount) root.appendChild(learningBlock);

    if (evolution.quality) {
      root.appendChild(line(doc, `Quality Gate 11 · ${evolution.quality.status} · ${evolution.quality.quality}/100`, evolution.quality.status === "BLOCK" ? "warning" : ""));
    }
  }
  if (phase26) {
    const heading26 = doc.createElement("h4");
    heading26.className = "engineering-intelligence-phase26-title";
    heading26.textContent = "Engineering Intelligence 2.0 · READ ONLY";
    root.appendChild(heading26);

    const summary26 = doc.createElement("div");
    summary26.className = "engineering-intelligence-phase26-summary";
    summary26.append(
      line(doc, `${phase26.trends?.length ?? 0} trends`),
      line(doc, `${phase26.correlations?.length ?? 0} correlations`),
      line(doc, `${phase26.impact?.length ?? 0} impact predictions`),
      line(doc, `${phase26.dependencies?.length ?? 0} dependency risks`),
      line(doc, `${phase26.evaluations?.length ?? 0} evaluations`),
      line(doc, `${phase26.evidenceGraph?.nodes.length ?? 0} graph nodes`),
    );
    root.appendChild(summary26);

    const block26 = doc.createElement("div");
    block26.className = "engineering-intelligence-phase26-block";
    for (const trend of (phase26.trends ?? []).slice(0, 4)) {
      block26.appendChild(line(doc, `Trend · ${trend.metric} · ${trend.direction} · confidence ${trend.confidence}`, trend.direction === "increasing" || trend.direction === "volatile" ? "warning" : ""));
    }
    for (const correlation of (phase26.correlations ?? []).slice(0, 3)) {
      block26.appendChild(line(doc, `Correlation · ${correlation.relationship} · confidence ${correlation.confidence}`));
    }
    for (const impact of (phase26.impact ?? []).slice(0, 3)) {
      const risk = impact.risk_level ?? impact.riskLevel ?? "MEDIUM";
      block26.appendChild(line(doc, `Impact · ${risk} · ${impact.affected_modules?.length ?? impact.affectedModules?.length ?? 0} module(s) · confidence ${impact.confidence}`, risk === "HIGH" || risk === "CRITICAL" ? "warning" : ""));
    }
    for (const dependency of (phase26.dependencies ?? []).slice(0, 3)) {
      block26.appendChild(line(doc, `Dependency · ${dependency.risk} · ${dependency.dependency} · confidence ${dependency.confidence}`, dependency.risk === "HIGH" || dependency.risk === "CRITICAL" ? "warning" : ""));
    }
    if (!block26.childElementCount) block26.appendChild(line(doc, "No Phase 26 evidence signals yet"));
    root.appendChild(block26);

    const ranking = phase26.ranking;
    if (ranking) {
      const rankingBlock = doc.createElement("div");
      rankingBlock.className = "engineering-intelligence-phase26-block";
      rankingBlock.appendChild(line(doc, `Recommendation ranking · ${ranking.ranked.length} candidate(s) · confidence ${ranking.confidence}`));
      if (ranking.recommended_action) rankingBlock.appendChild(line(doc, `Recommended · ${ranking.recommended_action}`, "recommendation"));
      for (const alternative of (ranking.alternative_actions ?? ranking.alternativeActions ?? []).slice(0, 2)) rankingBlock.appendChild(line(doc, `Alternative · ${alternative}`, "recommendation"));
      root.appendChild(rankingBlock);
    }

    if (phase26.metrics) {
      const metrics = phase26.metrics;
      root.appendChild(line(doc, `Prediction accuracy · ${metrics.accuracy} · correct ${metrics.correct} · incorrect ${metrics.incorrect} · false positive ${metrics.false_positive_rate}`, metrics.accuracy < 0.5 ? "warning" : ""));
    }
    const graph = phase26.evidenceGraph;
    if (graph) root.appendChild(line(doc, `Evidence graph · ${graph.nodes.length} node(s) · ${graph.edges.length} edge(s)`));
  }
  if (phase27) {
    const heading27 = doc.createElement("h4");
    heading27.className = "engineering-intelligence-phase26-title";
    heading27.textContent = "Engineering Intelligence Validation · READ ONLY";
    root.appendChild(heading27);

    const accuracy = phase27.accuracy;
    const summary27 = doc.createElement("div");
    summary27.className = "engineering-intelligence-phase26-summary";
    summary27.append(
      line(doc, `${phase27.evaluations?.length ?? 0} evaluations`),
      line(doc, accuracy ? `accuracy ${accuracy.accuracy}` : "accuracy pending"),
      line(doc, phase27.effectivenessSummary ? `effectiveness ${phase27.effectivenessSummary.effectivenessRate}` : "effectiveness pending"),
      line(doc, phase27.decisionSummary ? `decision success ${phase27.decisionSummary.overallSuccessRate}` : "decision outcomes pending"),
      line(doc, `${phase27.benchmarks?.length ?? 0} benchmark runs`),
      line(doc, `${phase27.improvements?.length ?? 0} knowledge improvements`),
    );
    root.appendChild(summary27);

    const validationBlock = doc.createElement("div");
    validationBlock.className = "engineering-intelligence-phase26-block";
    if (accuracy) {
      validationBlock.appendChild(line(doc, `Accuracy · ${accuracy.accuracy} · correct ${accuracy.correct} · incorrect ${accuracy.incorrect} · precision ${accuracy.precision} · recall ${accuracy.recall}`, accuracy.accuracy < 0.5 ? "warning" : ""));
      validationBlock.appendChild(line(doc, `False positives ${accuracy.falsePositive} · false negatives ${accuracy.falseNegative} · calibration error ${accuracy.calibrationError}`));
      const populated = (accuracy.calibration ?? []).filter((bin) => bin.count > 0);
      if (populated.length) {
        validationBlock.appendChild(line(doc, `Confidence calibration · ${populated.map((bin) => `${bin.lower}-${bin.upper}: ${bin.binAccuracy}`).join(" · ")}`));
      }
    }
    const failed = phase27.failedPredictions ?? [];
    for (const record of failed.slice(0, 3)) {
      validationBlock.appendChild(line(doc, `Failed · ${record.prediction_id} · ${record.evaluation_kind} · ${record.prediction_result}`, "warning"));
    }
    if (!validationBlock.childElementCount) validationBlock.appendChild(line(doc, "No validation records yet"));
    root.appendChild(validationBlock);

    const effectivenessBlock = doc.createElement("div");
    effectivenessBlock.className = "engineering-intelligence-phase26-block";
    const effectivenessSummary = phase27.effectivenessSummary;
    if (effectivenessSummary) {
      effectivenessBlock.appendChild(line(doc, `Effectiveness · ${effectivenessSummary.effectivenessRate} · correct ${effectivenessSummary.correct} · partially useful ${effectivenessSummary.partiallyUseful} · incorrect ${effectivenessSummary.incorrect} · rejected ${effectivenessSummary.rejected}`));
    }
    for (const record of (phase27.effectiveness ?? []).slice(0, 3)) {
      effectivenessBlock.appendChild(line(doc, `Recommendation · ${record.classification} · score ${record.effectiveness_score} · ${record.content}`, record.classification === "incorrect" ? "warning" : ""));
    }
    if (effectivenessBlock.childElementCount) root.appendChild(effectivenessBlock);

    const decisionBlock = doc.createElement("div");
    decisionBlock.className = "engineering-intelligence-phase26-block";
    const decisionSummary = phase27.decisionSummary;
    if (decisionSummary) {
      const rates = Object.entries(decisionSummary.byType ?? {}).map(([type, value]) => `${type} ${value.successRate}`).join(" · ");
      decisionBlock.appendChild(line(doc, `Decision outcomes · ${decisionSummary.total} · overall success ${decisionSummary.overallSuccessRate}${rates ? ` · ${rates}` : ""}`));
    }
    for (const record of (phase27.decisionOutcomes ?? []).slice(0, 3)) {
      decisionBlock.appendChild(line(doc, `Decision · ${record.decision_type} · ${record.status} · ${record.title}`));
    }
    if (decisionBlock.childElementCount) root.appendChild(decisionBlock);

    const benchmarkBlock = doc.createElement("div");
    benchmarkBlock.className = "engineering-intelligence-phase26-block";
    for (const run of (phase27.benchmarks ?? []).slice(0, 3)) {
      benchmarkBlock.appendChild(line(doc, `Benchmark · ${run.dataset_name ?? run.datasetName} · score ${run.score} · accuracy ${run.accuracy} · model ${run.model_id}`));
    }
    if (!benchmarkBlock.childElementCount) benchmarkBlock.appendChild(line(doc, "No benchmark runs recorded"));
    root.appendChild(benchmarkBlock);

    const improvementBlock = doc.createElement("div");
    improvementBlock.className = "engineering-intelligence-phase26-block";
    for (const improvement of (phase27.improvements ?? []).slice(0, 4)) {
      improvementBlock.appendChild(line(doc, `Improvement · ${improvement.status} · ${improvement.category} · confidence ${improvement.confidence}`, improvement.status === "pending" || improvement.status === "proposed" ? "recommendation" : ""));
    }
    if (!improvementBlock.childElementCount) improvementBlock.appendChild(line(doc, "No knowledge improvement proposals"));
    root.appendChild(improvementBlock);

    if (phase27.quality13) {
      root.appendChild(line(doc, `Quality Gate 13 · ${phase27.quality13.status} · ${phase27.quality13.quality}/100`, phase27.quality13.status === "BLOCK" ? "warning" : ""));
    }
  }
  if (phase28) {
    const heading28 = doc.createElement("h4");
    heading28.className = "engineering-intelligence-phase26-title";
    heading28.textContent = "Intelligence Governance · READ ONLY";
    root.appendChild(heading28);

    const quality14 = phase28.quality14;
    const summary28 = doc.createElement("div");
    summary28.className = "engineering-intelligence-phase26-summary";
    summary28.append(
      line(doc, quality14 ? `Quality Gate 14 · ${quality14.status} · ${quality14.quality}/100` : "Quality Gate 14 pending", quality14?.status === "BLOCKED" || quality14?.status === "REVIEW_REQUIRED" ? "warning" : ""),
      line(doc, `${phase28.records?.length ?? 0} governance records`),
      line(doc, `${phase28.risks?.length ?? 0} risk findings`),
      line(doc, `${phase28.violations?.length ?? 0} policy violations`),
      line(doc, `${phase28.reviews?.length ?? 0} review proposals`),
      line(doc, `${phase28.trends?.length ?? 0} governance trends`),
    );
    root.appendChild(summary28);

    const riskBlock = doc.createElement("div");
    riskBlock.className = "engineering-intelligence-phase26-block";
    if (quality14) {
      riskBlock.appendChild(line(doc, `Risk · max ${quality14.maxRiskLevel} · score ${quality14.maxRiskScore} · benchmark ${quality14.benchmarkScore ?? "n/a"}`, quality14.maxRiskLevel === "HIGH" || quality14.maxRiskLevel === "CRITICAL" ? "warning" : ""));
      if (quality14.regressionRate !== null && quality14.regressionRate !== undefined) riskBlock.appendChild(line(doc, `Regression rate · ${quality14.regressionRate}`, quality14.regressionRate > 0.2 ? "warning" : ""));
    }
    let riskCount = 0;
    for (const risk of (phase28.risks ?? []).slice(0, 4)) {
      riskBlock.appendChild(line(doc, `Risk · ${risk.risk_level} · ${risk.risk_score} · ${risk.reason}`, risk.risk_level === "HIGH" || risk.risk_level === "CRITICAL" ? "warning" : ""));
      riskCount += 1;
    }
    if (!riskCount) riskBlock.appendChild(line(doc, "No risk findings recorded"));
    root.appendChild(riskBlock);

    const trendBlock = doc.createElement("div");
    trendBlock.className = "engineering-intelligence-phase26-block";
    for (const trend of (phase28.trends ?? []).slice(0, 5)) {
      trendBlock.appendChild(line(doc, `Trend · ${trend.metric} · ${trend.direction} · Δ${trend.change_rate} · confidence ${trend.confidence}`, trend.direction === "declining" || trend.direction === "increasing" ? "warning" : ""));
    }
    for (const signal of (phase28.signals ?? []).slice(0, 3)) {
      trendBlock.appendChild(line(doc, `Signal · ${signal.signal} · ${signal.detail}`, "warning"));
    }
    if (!trendBlock.childElementCount) trendBlock.appendChild(line(doc, "No governance trends yet"));
    root.appendChild(trendBlock);

    const violationBlock = doc.createElement("div");
    violationBlock.className = "engineering-intelligence-phase26-block";
    for (const violation of (phase28.violations ?? []).slice(0, 3)) {
      violationBlock.appendChild(line(doc, `Violation · ${violation.policy_id} · ${violation.severity} · ${violation.reason}`, violation.severity === "blocking" ? "warning" : ""));
    }
    if (!violationBlock.childElementCount) violationBlock.appendChild(line(doc, "No policy violations"));
    root.appendChild(violationBlock);

    const reviewBlock = doc.createElement("div");
    reviewBlock.className = "engineering-intelligence-phase26-block";
    for (const review of (phase28.reviews ?? []).slice(0, 4)) {
      reviewBlock.appendChild(line(doc, `Review · ${review.status} · ${review.risk_level} · ${review.source_kind} ${review.source_id} · ${review.recommended_action}`, review.status === "proposed" ? "recommendation" : ""));
    }
    if (!reviewBlock.childElementCount) reviewBlock.appendChild(line(doc, "No governance review proposals"));
    root.appendChild(reviewBlock);

    const policyBlock = doc.createElement("div");
    policyBlock.className = "engineering-intelligence-phase26-block";
    for (const policy of (phase28.policies ?? []).slice(0, 4)) {
      policyBlock.appendChild(line(doc, `Policy · ${policy.policy_id} · ${policy.severity} · threshold ${policy.threshold} · scope ${policy.scope}`));
    }
    if (!policyBlock.childElementCount) policyBlock.appendChild(line(doc, "No policies registered"));
    root.appendChild(policyBlock);

    const graph = phase28.graph;
    if (graph) {
      root.appendChild(line(doc, `Governance graph · ${graph.nodeCount} node(s) · ${graph.edgeCount} edge(s) · read only`));
    }
  }
  return root;
}
