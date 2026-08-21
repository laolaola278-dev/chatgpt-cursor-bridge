/** Phase 31 · LLM Gateway types (read-only mirror of the backend protocol). */

export interface LlmProviderInfo {
  name: string;
  enabled: boolean;
  keyEnv: string;
  models: string[];
}

export interface LlmModel {
  id: string;
  provider: string;
  displayName: string;
  capabilities: string[];
  contextWindow: number;
  enabled: boolean;
}

export interface LlmToolCall {
  name: string;
  arguments: string;
  callId: string;
}

export interface LlmChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  name?: string;
  toolCalls?: LlmToolCall[];
}

export interface LlmChatResult {
  reply: string;
  toolCalls: LlmToolCall[];
  provider: string;
  model: string;
  finishReason: string;
  usage: Record<string, number>;
  simulated: boolean;
  readOnly: true;
}

export interface LlmConversation {
  conversationId: string;
  project: string;
  provider: string;
  model: string;
  title: string;
  agent: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  readOnly: true;
}

export interface LlmConversationMessage {
  messageId: string;
  conversationId: string;
  role: string;
  content: string;
  toolCalls: LlmToolCall[];
  createdAt: string;
  approvalRequestId: string;
  readOnly: true;
}

export interface LlmToolProposal {
  proposalId: string;
  conversationId: string;
  project: string;
  messageId: string;
  toolName: string;
  arguments: string;
  reason: string;
  status: string;
  approvalRequestId: string;
  createdAt: string;
  executed: false;
  readOnly: true;
}

export interface LlmGatewaySnapshot {
  providers: LlmProviderInfo[];
  models: LlmModel[];
  conversations: LlmConversation[];
  toolProposals: LlmToolProposal[];
  readOnly: true;
}
