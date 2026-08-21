/**
 * Content script entry point.
 *
 * Runs only on ChatGPT hosts (enforced by the manifest AND re-checked here).
 */

import { BridgeClient } from "../bridge/client";
import { Controller } from "./controller";
import { ConversationObserver } from "./dom-observer";
import { defaultSelectorAdapter } from "./selectors";
import { ExtensionStore } from "../state/store";
import { Panel } from "../ui/panel";
import { mountShadowHost } from "../ui/shadow-root";

const ATTACH_RETRY_MS = 1500;
const MAX_ATTACH_ATTEMPTS = 20;

async function bootstrap(): Promise<void> {
  if (!defaultSelectorAdapter.isChatGPTHost(window.location.hostname)) {
    return;
  }
  if (document.getElementById("ccb-extension-root")) {
    return;
  }

  const store = new ExtensionStore();
  await store.hydrate();

  const state = store.getState();
  const client = new BridgeClient({ origin: state.bridgeOrigin });

  const ui = mountShadowHost(document);
  let panel: Panel;

  const render = () => panel.render(store.getState());

  const controller = new Controller({
    store,
    client,
    render: () => render(),
    onProjects: (projects) => panel.setProjects(projects),
  });

  panel = new Panel(document, ui.container, {
    onConnect: () => void controller.connect(),
    onSelectProject: (project) => void controller.selectProject(project),
    onApprove: (id) => void controller.approve(id),
    onReject: (id) => void controller.reject(id),
    onReconfirm: (requestId) => void controller.reconfirm(requestId),
    onApproveRecovered: (requestId) => void controller.approveRecovered(requestId),
    onToggleContextSelection: (id) => void store.toggleDevContextSelection(id),
    // Phase 32 · assistant surfaces. Every callback below is driven by a click.
    onSetMode: (mode) => void controller.setUiMode(mode),
    onSelectProvider: (provider) => void controller.selectAssistantProvider(provider),
    onSelectModel: (model) => void controller.selectAssistantModel(model),
    onSaveProvider: (input) => void controller.saveProvider(input),
    onTestConnection: (input) => void controller.testProvider(input),
    onForgetKey: (provider) => void controller.forgetProviderKey(provider),
    onSend: (text) => void controller.sendAssistantMessage(text),
    onStop: () => void controller.stopAssistant(),
    onNewChat: () => void controller.newConversation(),
    onSelectConversation: (id) => void controller.selectConversation(id),
    onRemoveConversation: (id) => void controller.removeConversation(id),
    onAskAi: (bundle) => void controller.askAi(bundle),
    onClearContext: () => void controller.clearWebContext(),
    // Phase 34 · retry, conversation management, context decision and the
    // first-run guide. All of them are clicks; none of them auto-sends anything.
    onRetry: () => void controller.retryAssistant(),
    onSearchConversations: (query) => void controller.searchConversations(query),
    onBeginRename: (id) => void controller.beginRenameConversation(id),
    onRename: (id, title) => void controller.renameConversation(id, title),
    onCancelRename: () => void controller.cancelRenameConversation(),
    onTogglePin: (id) => void controller.toggleConversationPinned(id),
    onToggleContextInclude: (include) => void controller.toggleContextInclude(include),
    onNext: () => void controller.onboardingNext(),
    onBack: () => void controller.onboardingBack(),
    onSkip: () => void controller.onboardingSkip(),
    onSetupLater: () => void controller.onboardingLater(),
    onFinish: () => void controller.onboardingFinish(),
    onReopen: () => void controller.onboardingReopen(),
  });
  render();

  const observer = new ConversationObserver({
    adapter: defaultSelectorAdapter,
    onResults: (results) => void controller.handleParseResults(results),
  });

  let attempts = 0;
  const attach = () => {
    if (observer.start(document)) return;
    attempts += 1;
    if (attempts < MAX_ATTACH_ATTEMPTS) {
      setTimeout(attach, ATTACH_RETRY_MS);
    }
  };
  attach();

  // Best-effort initial connection; failures surface as "offline" in the UI.
  void controller.connect();

  // Context is read-only and refreshed periodically so the dashboard follows
  // workflow/test/Git changes without introducing any execution path.
  window.setInterval(() => {
    void controller.refreshApprovals();
    void controller.refreshContext();
  }, 10000);
}

void bootstrap();
