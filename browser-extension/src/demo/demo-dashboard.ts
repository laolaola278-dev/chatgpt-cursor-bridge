import type { ArtifactRecord } from "../artifacts/models";
import type { DemoScenarioRecord } from "./models";
import type { ReplayRecord } from "../replay/models";

export interface DemoDashboardData {
  scenarios: DemoScenarioRecord[];
  flow: string[];
  replays: ReplayRecord[];
  artifacts: ArtifactRecord[];
}

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `demo-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

export function renderDemoDashboard(doc: Document, data: DemoDashboardData): HTMLElement {
  const root = doc.createElement("section");
  root.className = "demo-dashboard";
  root.dataset.role = "demo-dashboard";
  const heading = doc.createElement("div");
  heading.className = "demo-heading";
  const title = doc.createElement("strong");
  title.textContent = "Engineering Demo";
  const badge = doc.createElement("span");
  badge.className = "demo-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  if (!data.scenarios.length && !data.replays.length && !data.artifacts.length) {
    root.appendChild(line(doc, "No demo artifacts recorded yet"));
    return root;
  }
  root.appendChild(line(doc, data.flow.length ? data.flow.join(" → ") : "Issue → Analysis → Proposal → Approval → Execution → Verification → Report"));

  const blocks = doc.createElement("div");
  blocks.className = "demo-blocks";
  const scenarioBlock = doc.createElement("div");
  scenarioBlock.className = "demo-block";
  const scenarioTitle = doc.createElement("h4");
  scenarioTitle.textContent = "Demo Scenarios";
  scenarioBlock.appendChild(scenarioTitle);
  for (const scenario of data.scenarios.slice(0, 5)) scenarioBlock.appendChild(line(doc, `${scenario.name} · ${scenario.issue}`));
  if (!data.scenarios.length) scenarioBlock.appendChild(line(doc, "No demo scenarios recorded"));
  blocks.appendChild(scenarioBlock);

  const replayBlock = doc.createElement("div");
  replayBlock.className = "demo-block";
  const replayTitle = doc.createElement("h4");
  replayTitle.textContent = "Engineering Replays";
  replayBlock.appendChild(replayTitle);
  for (const replay of data.replays.slice(0, 5)) replayBlock.appendChild(line(doc, `${replay.id} · ${replay.title} · ${replay.steps.length} step(s)`));
  if (!data.replays.length) replayBlock.appendChild(line(doc, "No replays recorded yet"));
  blocks.appendChild(replayBlock);

  const artifactBlock = doc.createElement("div");
  artifactBlock.className = "demo-block";
  const artifactTitle = doc.createElement("h4");
  artifactTitle.textContent = "Artifacts";
  artifactBlock.appendChild(artifactTitle);
  for (const artifact of data.artifacts.slice(0, 5)) artifactBlock.appendChild(line(doc, `${artifact.kind} · ${artifact.project}`));
  if (!data.artifacts.length) artifactBlock.appendChild(line(doc, "No artifacts exported yet"));
  blocks.appendChild(artifactBlock);
  root.appendChild(blocks);
  return root;
}
