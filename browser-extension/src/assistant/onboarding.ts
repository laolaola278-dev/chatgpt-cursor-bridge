/**
 * Phase 34 · First-run onboarding.
 *
 * A four-step guide — Start Local Bridge → Configure Provider → Test
 * Connection → Start Chat — shown automatically on the first launch and never
 * again once the user finishes, skips it or defers it.
 *
 * The guide is **pure UI**. It has no API key field, no provider write, no
 * approval action and no execution control. Each step describes what the user
 * should do and points at the surface that does it (Settings, the composer);
 * the buttons here only move a display cursor. Skipping is always allowed, so a
 * user with no Bridge and no provider can still reach Chat and look around.
 */

import { ONBOARDING_STEPS, ONBOARDING_STEP_COUNT, type OnboardingState, type OnboardingStep } from "./types";

export interface OnboardingViewState {
  onboardingState: string;
  onboardingStep: number;
  /** Live signals, used to show progress. Neither one gates Next or Skip. */
  bridgeReachable: boolean;
  providerConfigured: boolean;
}

export interface OnboardingHandlers {
  onNext?: () => void;
  onBack?: () => void;
  onSkip?: () => void;
  onSetupLater?: () => void;
  onFinish?: () => void;
  /** Reopen from the hint. Only ever a click. */
  onReopen?: () => void;
}

/** States in which the guide is on screen. */
export const ONBOARDING_VISIBLE_STATES = ["new", "active"] as const;

export function isOnboardingVisible(state: string): boolean {
  return (ONBOARDING_VISIBLE_STATES as readonly string[]).includes(state);
}

/** True when a dismissed-for-now guide should still offer a reopen hint. */
export function isOnboardingDeferred(state: string): boolean {
  return state === "later";
}

export function clampOnboardingStep(step: number): number {
  if (!Number.isFinite(step)) return 0;
  return Math.min(Math.max(Math.trunc(step), 0), ONBOARDING_STEP_COUNT - 1);
}

export function onboardingStepAt(step: number): OnboardingStep {
  return ONBOARDING_STEPS[clampOnboardingStep(step)];
}

/** Progress note for a step. Informational only — never a gate. */
function stepSignal(step: OnboardingStep, state: OnboardingViewState): string {
  if (step.id === "start_bridge") {
    return state.bridgeReachable ? "Bridge reachable" : "Bridge not detected — you can continue anyway";
  }
  if (step.id === "configure_provider" || step.id === "test_connection") {
    return state.providerConfigured ? "A provider is configured" : "No provider configured — you can continue anyway";
  }
  return "Chat works without a provider using the local simulator";
}

function button(
  doc: Document,
  role: string,
  label: string,
  className: string,
  handler?: () => void,
): HTMLButtonElement {
  const element = doc.createElement("button");
  element.className = className;
  element.dataset.role = role;
  element.type = "button";
  element.textContent = label;
  element.addEventListener("click", () => handler?.());
  return element;
}

/**
 * The guide itself. Rendered above Chat, never instead of it: the first surface
 * a new user sees is still the chat panel.
 */
export function renderOnboarding(
  doc: Document,
  state: OnboardingViewState,
  handlers: OnboardingHandlers = {},
): HTMLElement {
  const root = doc.createElement("div");
  root.className = "assistant-onboarding";
  root.dataset.role = "onboarding";
  root.dataset.onboardingState = state.onboardingState;

  const index = clampOnboardingStep(state.onboardingStep);
  const step = ONBOARDING_STEPS[index];
  root.dataset.stepId = step.id;
  root.dataset.step = String(index + 1);

  const head = doc.createElement("div");
  head.className = "assistant-onboarding-head";
  const title = doc.createElement("span");
  title.className = "assistant-onboarding-title";
  title.textContent = "Getting started";
  const progress = doc.createElement("span");
  progress.className = "assistant-onboarding-progress";
  progress.dataset.role = "onboarding-progress";
  progress.textContent = `Step ${index + 1} of ${ONBOARDING_STEP_COUNT}`;
  head.append(title, progress);
  root.appendChild(head);

  const list = doc.createElement("ol");
  list.className = "assistant-onboarding-steps";
  list.dataset.role = "onboarding-steps";
  ONBOARDING_STEPS.forEach((entry, position) => {
    const row = doc.createElement("li");
    row.className = `assistant-onboarding-step${position === index ? " current" : ""}${
      position < index ? " done" : ""
    }`;
    row.dataset.role = "onboarding-step";
    row.dataset.stepId = entry.id;
    if (position === index) row.dataset.current = "true";

    const label = doc.createElement("span");
    label.className = "assistant-onboarding-step-title";
    label.textContent = `${position + 1}. ${entry.title}`;
    row.appendChild(label);

    if (position === index) {
      const detail = doc.createElement("div");
      detail.className = "assistant-onboarding-detail";
      detail.dataset.role = "onboarding-detail";
      detail.textContent = entry.detail;
      row.appendChild(detail);

      const signal = doc.createElement("div");
      signal.className = "assistant-onboarding-signal";
      signal.dataset.role = "onboarding-signal";
      signal.textContent = stepSignal(entry, state);
      row.appendChild(signal);
    }
    list.appendChild(row);
  });
  root.appendChild(list);

  const note = doc.createElement("div");
  note.className = "assistant-onboarding-note";
  note.dataset.role = "onboarding-note";
  note.textContent =
    "This guide only shows you where things are. It stores no API key and changes no permission: " +
    "every write still waits for your approval in the Bridge.";
  root.appendChild(note);

  const actions = doc.createElement("div");
  actions.className = "assistant-onboarding-actions";
  if (index > 0) {
    actions.appendChild(button(doc, "onboarding-back", "Back", "assistant-onboarding-secondary", handlers.onBack));
  }
  const last = index === ONBOARDING_STEP_COUNT - 1;
  if (last) {
    actions.appendChild(
      button(doc, "onboarding-finish", "Start Chat", "assistant-onboarding-primary", handlers.onFinish),
    );
  } else {
    actions.appendChild(button(doc, "onboarding-next", "Next", "assistant-onboarding-primary", handlers.onNext));
  }
  actions.appendChild(button(doc, "onboarding-skip", "Skip", "assistant-onboarding-secondary", handlers.onSkip));
  actions.appendChild(
    button(doc, "onboarding-later", "Setup Later", "assistant-onboarding-secondary", handlers.onSetupLater),
  );
  root.appendChild(actions);

  return root;
}

/** One-line hint shown after Setup Later, so the guide is not lost. */
export function renderOnboardingHint(doc: Document, handlers: OnboardingHandlers = {}): HTMLElement {
  const hint = doc.createElement("div");
  hint.className = "assistant-onboarding-hint";
  hint.dataset.role = "onboarding-hint";

  const text = doc.createElement("span");
  text.textContent = "Setup postponed. Chat is available now.";
  hint.appendChild(text);
  hint.appendChild(
    button(doc, "onboarding-reopen", "Show setup guide", "assistant-onboarding-secondary", handlers.onReopen),
  );
  return hint;
}

/** Convenience for callers that keep the state as a plain string. */
export function asOnboardingState(value: string): OnboardingState {
  const known = ["new", "active", "later", "skipped", "done"];
  return (known.includes(value) ? value : "new") as OnboardingState;
}
