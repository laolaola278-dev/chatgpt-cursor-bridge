import type { EngineeringPlan, SimulationEvaluation, SimulationRecord, SimulationScenario, SimulationQuality6 } from "./models";

function line(doc: Document, text: string, tone = ""): HTMLElement { const node = doc.createElement("div"); node.className = `simulation-line ${tone}`.trim(); node.textContent = text; return node; }

export function renderSimulationDashboard(doc: Document, simulation: SimulationRecord | null, scenarios: SimulationScenario[], evaluations: SimulationEvaluation[], plans: EngineeringPlan[], quality: SimulationQuality6 | null): HTMLElement {
  const root = doc.createElement("section"); root.className = "simulation-dashboard"; root.dataset.role = "simulation-dashboard";
  const heading = doc.createElement("div"); heading.className = "simulation-heading";
  const title = doc.createElement("strong"); title.textContent = "Engineering Simulation";
  const badge = doc.createElement("span"); badge.className = "simulation-badge"; badge.textContent = "SIMULATION · READ ONLY"; heading.append(title, badge); root.appendChild(heading);
  if (!simulation) { root.appendChild(line(doc, "No simulation created yet")); return root; }
  root.appendChild(line(doc, `Problem · ${simulation.problem}`, "simulation-problem"));
  root.appendChild(line(doc, `${scenarios.length} candidate solutions · ${simulation.status}`));
  const candidates = doc.createElement("div"); candidates.className = "simulation-candidates";
  for (const scenario of scenarios.slice(0, 4)) {
    const block = doc.createElement("article"); block.className = "simulation-candidate";
    block.appendChild(line(doc, scenario.name)); block.appendChild(line(doc, `${scenario.type} · ${scenario.risk.toUpperCase()} risk · impact ${scenario.impactScore}/100`, scenario.risk === "high" ? "warning" : ""));
    block.appendChild(line(doc, `${scenario.affectedFiles.length} files · ${scenario.dependentModules.length} dependents`));
    const evaluation = evaluations.find((item) => item.scenario === scenario.id); if (evaluation) block.appendChild(line(doc, `Score ${evaluation.score}/100 · ${evaluation.advantages[0] ?? "evaluated"}`));
    candidates.appendChild(block);
  }
  if (!scenarios.length) candidates.appendChild(line(doc, "No scenarios analyzed yet")); root.appendChild(candidates);
  if (plans.length) { const plan = plans[0]; const preview = doc.createElement("pre"); preview.className = "simulation-plan"; preview.textContent = plan.content.slice(0, 900); root.appendChild(preview); }
  if (quality) root.appendChild(line(doc, `Quality ${quality.quality}/100 · confidence ${(quality.simulationConfidence * 100).toFixed(0)}%`, "simulation-quality"));
  return root;
}
