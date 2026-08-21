import type { LlmGatewaySnapshot } from "./types";

function line(doc: Document, text: string, tone = ""): HTMLElement {
  const node = doc.createElement("div");
  node.className = `llm-line ${tone}`.trim();
  node.textContent = text;
  return node;
}

function block(doc: Document, title: string, children: HTMLElement[]): HTMLElement {
  const section = doc.createElement("div");
  section.className = "llm-block";
  const heading = doc.createElement("h4");
  heading.textContent = title;
  section.appendChild(heading);
  for (const child of children) section.appendChild(child);
  return section;
}

/**
 * Read-only LLM Gateway dashboard (Phase 31).
 *
 * Shows the provider registry (with enabled/disabled state), the model
 * catalogue, persisted conversations and recorded tool-call proposals. Chat
 * itself is stateless; nothing here can execute a tool, approve a request or
 * modify system state. Tool proposals are records only and always carry
 * `executed=false`.
 */
export function renderLlmGatewayDashboard(doc: Document, snapshot: LlmGatewaySnapshot | null): HTMLElement {
  const root = doc.createElement("section");
  root.className = "llm-dashboard";
  root.dataset.role = "llm-dashboard";

  const heading = doc.createElement("div");
  heading.className = "llm-heading";
  const title = doc.createElement("strong");
  title.textContent = "LLM Gateway";
  const badge = doc.createElement("span");
  badge.className = "llm-badge";
  badge.textContent = "READ ONLY";
  heading.append(title, badge);
  root.appendChild(heading);

  if (!snapshot) {
    root.appendChild(line(doc, "No LLM gateway data loaded. Select a project and refresh."));
    return root;
  }

  // -- Providers --------------------------------------------------------
  const providerChildren: HTMLElement[] = [];
  if (snapshot.providers.length) {
    for (const provider of snapshot.providers) {
      const tone = provider.enabled ? "ok" : "";
      providerChildren.push(
        line(
          doc,
          `${provider.name} — ${provider.enabled ? "configured" : "not configured"} · ${provider.models.length} model(s)`,
          tone,
        ),
      );
    }
    providerChildren.push(line(doc, "Vendor providers activate only when their API key is set in the environment.", "ok"));
  } else {
    providerChildren.push(line(doc, "No providers registered."));
  }
  root.appendChild(block(doc, "Provider Registry", providerChildren));

  // -- Models -----------------------------------------------------------
  const modelChildren: HTMLElement[] = [];
  if (snapshot.models.length) {
    const enabled = snapshot.models.filter((model) => model.enabled);
    const shown = enabled.slice(0, 10);
    for (const model of shown) {
      modelChildren.push(
        line(doc, `${model.id} — ${model.provider} · ${model.capabilities.join(", ")}`),
      );
    }
    if (enabled.length > shown.length) {
      modelChildren.push(line(doc, `+${enabled.length - shown.length} more enabled model(s)`, "warn"));
    }
    const disabledCount = snapshot.models.length - enabled.length;
    if (disabledCount) {
      modelChildren.push(line(doc, `${disabledCount} vendor model(s) disabled until provider keys are configured.`, "warn"));
    }
  } else {
    modelChildren.push(line(doc, "No models in the registry."));
  }
  root.appendChild(block(doc, "Model Registry", modelChildren));

  // -- Conversations ----------------------------------------------------
  const conversationChildren: HTMLElement[] = [];
  if (snapshot.conversations.length) {
    for (const conversation of snapshot.conversations.slice(0, 6)) {
      const agent = conversation.agent ? ` · agent=${conversation.agent}` : "";
      conversationChildren.push(
        line(doc, `${conversation.title.slice(0, 80)} — ${conversation.provider}/${conversation.model}${agent}`),
      );
    }
  } else {
    conversationChildren.push(line(doc, "No persisted conversations for this project yet."));
  }
  conversationChildren.push(line(doc, "Conversation persistence is approval-gated on the bridge.", "ok"));
  root.appendChild(block(doc, "Conversations (bound to project/agent)", conversationChildren));

  // -- Tool proposals ---------------------------------------------------
  const proposalChildren: HTMLElement[] = [];
  if (snapshot.toolProposals.length) {
    for (const proposal of snapshot.toolProposals.slice(0, 6)) {
      proposalChildren.push(
        line(doc, `${proposal.toolName} — ${proposal.status} · ${proposal.reason.slice(0, 80)}`),
      );
    }
    proposalChildren.push(line(doc, "Recorded proposals only — tools are never executed by the gateway.", "ok"));
  } else {
    proposalChildren.push(line(doc, "No recorded tool-call proposals for this project."));
  }
  root.appendChild(block(doc, "Tool-Call Proposals (record only)", proposalChildren));

  const footer = doc.createElement("div");
  footer.className = "llm-footer";
  footer.textContent = "Read-only. No execute, approve, apply, fix, auto-learn or auto-govern. Chat is stateless; tool calls are proposals only.";
  root.appendChild(footer);
  return root;
}
