import type { ContextStage, ContextWorkflow } from "../context/types";

const STAGE_ORDER = [
  "REQUIREMENT",
  "ANALYSIS",
  "ARCHITECTURE",
  "IMPLEMENTATION",
  "TESTING",
  "DEBUG",
  "DELIVERY",
];

function label(value: string): string {
  return value.replace(/_/g, " ").toLowerCase().replace(/(^|\s)\S/g, (char) => char.toUpperCase());
}

function stageFor(workflow: ContextWorkflow, stageType: string): ContextStage | undefined {
  return [...workflow.stages].reverse().find((stage) => stage.stageType === stageType);
}

export function renderStageTimeline(doc: Document, workflow: ContextWorkflow): HTMLElement {
  const timeline = doc.createElement("div");
  timeline.className = "workflow-timeline";
  timeline.dataset.role = "stage-timeline";

  for (const stageType of STAGE_ORDER) {
    const stage = stageFor(workflow, stageType);
    const card = doc.createElement("div");
    const status = stage?.status ?? "PENDING";
    const stateClass = status === "APPROVED" ? "done" : status === "IN_PROGRESS" || status === "REPORTED" || status === "WAITING_APPROVAL" ? "active" : "pending";
    card.className = `timeline-stage ${stateClass}`;
    card.dataset.stage = stageType;

    const marker = doc.createElement("span");
    marker.className = "timeline-marker";
    marker.textContent = status === "APPROVED" ? "✓" : status === "IN_PROGRESS" || status === "REPORTED" || status === "WAITING_APPROVAL" ? "●" : "○";

    const name = doc.createElement("strong");
    name.textContent = label(stageType);
    const state = doc.createElement("small");
    state.textContent = label(status);
    card.append(marker, name, state);

    if (stage) {
      const meta = doc.createElement("small");
      meta.className = "timeline-meta";
      meta.textContent = `${stage.actionIds.length} action${stage.actionIds.length === 1 ? "" : "s"}`;
      card.appendChild(meta);

      if (stage.report) {
        const details = doc.createElement("details");
        details.className = "stage-report";
        const summary = doc.createElement("summary");
        summary.textContent = "View report";
        const report = doc.createElement("pre");
        report.textContent = stage.report;
        details.append(summary, report);
        card.appendChild(details);
      }
      if (stage.approvalRequestId) {
        const approval = doc.createElement("small");
        approval.className = "stage-approval";
        approval.textContent = status === "WAITING_APPROVAL" ? "Approval pending" : `Approval ${label(status)}`;
        card.appendChild(approval);
      }
    }
    timeline.appendChild(card);
  }
  return timeline;
}
