import type { BenchmarkDashboardData, BenchmarkRecord, BenchmarkResultRecord } from "./models";

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `benchmark-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

export function renderBenchmarkDashboard(doc: Document, data: BenchmarkDashboardData): HTMLElement {
  const root = doc.createElement("section");
  root.className = "benchmark-dashboard";
  root.dataset.role = "benchmark-dashboard";
  const heading = doc.createElement("div");
  heading.className = "benchmark-heading";
  const title = doc.createElement("strong");
  title.textContent = "Benchmark Dashboard";
  const badge = doc.createElement("span");
  badge.className = "benchmark-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  const results = data.results;
  if (!data.benchmarks.length && !results.length && !data.capabilities.length) {
    root.appendChild(line(doc, "No benchmark data recorded yet"));
    return root;
  }
  const completed = results.length;
  const success = results.filter((result) => result.success).length;
  const successRate = completed ? Math.round((success / completed) * 100) : 0;
  const avgQuality = completed ? Math.round(results.reduce((sum, result) => sum + result.qualityScore, 0) / completed) : 0;
  const rollbackCount = results.filter((result) => result.rollbackTriggered).length;
  const rollbackRate = completed ? Math.round((rollbackCount / completed) * 100) : 0;

  root.appendChild(line(doc, `${data.benchmarks.length} benchmark(s) · ${completed} result(s) · success ${successRate}% · quality ${avgQuality}/100 · rollback ${rollbackRate}%`, completed ? "pass" : ""));

  const blocks = doc.createElement("div");
  blocks.className = "benchmark-blocks";

  const summary = doc.createElement("div");
  summary.className = "benchmark-block";
  const summaryTitle = doc.createElement("h4");
  summaryTitle.textContent = "Overview";
  summary.appendChild(summaryTitle);
  for (const record of data.benchmarks.slice(0, 5)) summary.appendChild(line(doc, `${record.id} · ${record.project} · ${record.status}`));
  if (!data.benchmarks.length) summary.appendChild(line(doc, "No benchmark projects recorded"));
  blocks.appendChild(summary);

  const agentBlock = doc.createElement("div");
  agentBlock.className = "benchmark-block";
  const agentTitle = doc.createElement("h4");
  agentTitle.textContent = "Agent Performance";
  agentBlock.appendChild(agentTitle);
  for (const metric of data.capabilities.slice(0, 5)) agentBlock.appendChild(line(doc, `${metric.agentId} · success ${metric.successRate}% · quality ${metric.averageQuality} · rollback ${metric.rollbackRate}%`));
  if (!data.capabilities.length) agentBlock.appendChild(line(doc, "No agent capability data recorded"));
  blocks.appendChild(agentBlock);

  const failureBlock = doc.createElement("div");
  failureBlock.className = "benchmark-block";
  const failureTitle = doc.createElement("h4");
  failureTitle.textContent = "Failure Patterns";
  failureBlock.appendChild(failureTitle);
  for (const pattern of data.failurePatterns.slice(0, 5)) failureBlock.appendChild(line(doc, `${pattern.category} · ${pattern.occurrences} occurrence(s)`, pattern.severity === "high" ? "warning" : ""));
  if (!data.failurePatterns.length) failureBlock.appendChild(line(doc, "No failure pattern detected"));
  blocks.appendChild(failureBlock);

  const resultBlock = doc.createElement("div");
  resultBlock.className = "benchmark-block";
  const resultTitle = doc.createElement("h4");
  resultTitle.textContent = "Results";
  resultBlock.appendChild(resultTitle);
  for (const result of results.slice(0, 5)) resultBlock.appendChild(line(doc, `${result.id} · ${result.success ? "pass" : "fail"} · quality ${result.qualityScore} · rollback ${result.rollbackTriggered ? "yes" : "no"}`));
  if (!results.length) resultBlock.appendChild(line(doc, "No results recorded yet"));
  blocks.appendChild(resultBlock);

  root.appendChild(blocks);
  return root;
}

export type { BenchmarkRecord, BenchmarkResultRecord };
