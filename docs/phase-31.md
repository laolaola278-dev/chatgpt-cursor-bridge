# Phase 31 · LLM Provider Integration Layer

## 状态

Phase 31 在 Phase 30 的只读 Context Intelligence 之上建立 **统一、可扩展、安全的 LLM Provider Integration Layer**：通过 Provider Registry / Model Registry 管理 OpenAI（GPT-5 / GPT-4 系列）、Anthropic（Claude 系列）、DeepSeek（Chat / Reasoner），以统一 Message Protocol（system / user / assistant / tool）提供 Chat、Streaming、Conversation（Agent / Conversation 绑定）与 Tool Calling Proposal 接入层。

本阶段只实现 **接入层**：

- ✅ Provider Registry / Model Registry / Provider 配置 / Model 选择
- ✅ 统一 Message Protocol / Chat / Streaming / Conversation / Agent 绑定
- ✅ Tool Calling Proposal（记录式，经 ApprovalStore + 人工审批）
- ❌ 不新增 Phase 32 / Productization / Intelligence / Governance / Graph / Autonomous Agent
- ❌ 无自动执行、无自动批准、无 Shell、无权限提升

完整链路：

```text
Extension Chat
  ↓ 统一 Message Protocol（system / user / assistant / tool）
LLM Gateway（Provider Registry 解析 → Model Registry 选择）
  ↓ Chat / Streaming（无状态计算，不持久化）
模型回复（含 Tool Call）
  ↓
Tool Calling Proposal
  ↓ ApprovalStore
  ↓ Human Approval
  ↓ 记录（executed=false）—— 工具执行仍留在既有受控运行时，不在本阶段
```

## Provider 模型

| Provider | 模型 | 启用条件 |
|---|---|---|
| `local` | `local/simulator-v1`、`local/architect-v1` | 始终启用（确定性模拟器，无凭据） |
| `openai` | `gpt-5`、`gpt-5-mini`、`gpt-4o`、`gpt-4-turbo` | `OPENAI_API_KEY` 存在时 |
| `anthropic` | `claude-4-sonnet`、`claude-3-7-sonnet`、`claude-3-5-sonnet`、`claude-3-5-haiku` | `ANTHROPIC_API_KEY` 存在时 |
| `deepseek` | `deepseek-chat`、`deepseek-reasoner` | `DEEPSEEK_API_KEY` 存在时 |

- 控制器与 Gateway 一律通过 **Provider Registry** 解析 Provider，不硬编码 Provider 分支。
- 未配置的 vendor Provider 在 chat/stream 时返回 422（`provider_not_configured`），**绝不发起网络调用**。
- 测试永不使用真实 API Key；Provider 支持注入 `httpx` transport，测试用 mock transport 覆盖协议解析。

## 模块（local-bridge/app/llm_gateway/）

| 文件 | 职责 |
|---|---|
| `models.py` | 统一 Message Protocol（`MessageRole` / `ChatMessage` / `ToolCall`）、`ChatRequest` / `ChatResult` / `StreamEvent`、`Conversation` / `ConversationMessage` / `ToolCallProposal`（状态机 proposed → recorded，`executed=false`） |
| `registry.py` | `ProviderRegistry`（固定 allowlist，名称 → 实例，`enabled` 由 key 决定）与 `ModelRegistry`（跨 Provider 模型目录） |
| `providers/base.py` | `LLMProvider` 协议、`ProviderError`、`HTTPProviderMixin`（httpx + transport 注入 + 401/5xx 翻译）、`@tool(name {...})` 文本工具调用解析 |
| `providers/local.py` | `LocalSimulatorProvider`：确定性、无凭据；用户消息含 `@tool(...)` 时回复携带 Tool Call proposal |
| `providers/openai.py` | OpenAI chat/stream（OpenAI 消息格式 ↔ 统一协议，tool_calls 解析） |
| `providers/anthropic.py` | Anthropic messages API（system 分离、tool_use block 解析） |
| `providers/deepseek.py` | DeepSeek chat/stream（OpenAI 兼容格式） |
| `conversation.py` | `ConversationStore`：SQLite、项目隔离、Conversation ↔ Agent 绑定、消息历史、Tool Call Proposal 记录 |
| `gateway.py` | `LLMGateway`：chat / stream 编排（无状态）、conversation / tool proposal 持久化入口 |
| `routes.py` | Phase 31 API（见下） |

其他接线：`app/models/request.py`（`LlmChatRequest` / `LlmConversationCreateRequest` / `LlmConversationMessageRequest` / `LlmToolProposalRequest`）、`app/security/permissions.py`、`app/main.py`（三个 LEVEL_1 审批动作 + `_execute_action` 分支）。

## API

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/llm/providers` | LEVEL_0 只读 |
| GET | `/llm/models?provider=` | LEVEL_0 只读 |
| GET | `/llm/conversations?project=&agent=` | LEVEL_0 只读 |
| GET | `/llm/conversations/{id}?project=` | LEVEL_0 只读（含消息） |
| GET | `/llm/tool-proposals?project=&conversation_id=` | LEVEL_0 只读 |
| POST | `/llm/chat` | LEVEL_0 无状态（不持久化、不执行） |
| POST | `/llm/chat/stream` | LEVEL_0 无状态（SSE） |
| POST | `/llm/conversations` | LEVEL_1（ApprovalStore，202） |
| POST | `/llm/conversations/{id}/messages` | LEVEL_1（ApprovalStore，202） |
| POST | `/llm/conversations/{id}/tool-proposal` | LEVEL_1（ApprovalStore，202，记录式） |

## 安全边界

- **无自动执行**：Gateway 无 execute/apply/run 方法；Tool Call 永远以 Proposal 呈现，批准后也只记录（`executed=false`），工具执行属于既有受控运行时，不在本阶段。
- **无自动批准**：Conversation / Message / Tool Proposal 持久化全部 202 pending → ApprovalStore → 人工审批；无 auto-approve 端点。
- **Secret 保护**：Provider 信息只暴露 env 变量**名**（`keyEnv`），从不暴露值；源码无默认凭据；未配置 Provider 快速失败（422），不发网络请求。
- **项目隔离**：Conversation / Message / Tool Proposal 全部按 project 隔离，跨项目读取返回 404/空。
- **协议封闭**：未知 role 归一为 user；消息条数与长度受 Pydantic 校验；`@tool` 参数保持不透明（Gateway 不解释）。
- **无 Shell / 无 os.system / 无 eval**：`llm_gateway/` 源码经安全测试扫描。

## 测试

- Backend：`tests/test_phase31_llm_gateway.py`（58）+ `tests/security/test_phase31_llm_security.py`（26）= **84 passed**
  - 消息协议 / Provider / Model Registry / Local chat / Streaming / 错误路径 / Conversation 持久化 / Tool Proposal 记录 / API
  - 安全：无执行、无自动批准、审批边界、项目隔离、Secret 保护、输入校验、无状态性、Provider 安全
- Extension：`browser-extension/tests/phase31-llm.test.ts` **100 passed**（≥100）
- 回归：Phase 12 / 25–30 全部通过，无破坏

## 完成标准核对

- [x] Provider Registry（不允许 Controller 硬编码 Provider 分支）
- [x] Model Registry（GPT-5 / GPT-4 系列、Claude 系列、DeepSeek Chat / Reasoner）
- [x] Provider 配置（key 环境变量 → enabled）与 Model 选择
- [x] 统一 Message Protocol（system / user / assistant / tool）
- [x] Chat（无状态）与 Streaming（SSE）
- [x] Conversation（持久化、项目隔离、Agent / Conversation 绑定）
- [x] Tool Calling Proposal（ApprovalStore → 人工审批 → 记录，绝不执行）
- [x] Security：无自动执行 / 自动批准 / Shell / 权限提升 / Secret 泄露
- [x] docs/phase-31.md + README 更新
- [x] 未新增 Phase 32 / Productization / Intelligence / Governance / Graph / Autonomous Agent

## 当前 Phase

Phase 31 · LLM Provider Integration Layer
