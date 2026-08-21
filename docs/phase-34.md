# Phase 34 · User Trial & Product Refinement

## 状态

Phase 34 把 Phase 33 的**可发布版本**打磨成**可长期给真实用户使用的稳定版本**：首次运行引导、统一错误体验、Chat 交互细节、会话管理、Context 预览与控制、UI/State 回归。本阶段 **不新增任何能力边界**，权限模型与 Phase 8 的 ApprovalStore 完全一致。

- ✅ First Run Onboarding：4 步引导（Start Local Bridge → Configure Provider → Test Connection → Start Chat），首次启动自动出现、只出现一次，Next / Back / Skip / Setup Later / Finish
- ✅ Unified Error Experience：401 / 429 / 5xx / 网络失败 / 用户停止 / 未配置 Provider 各自映射到**一句固定文案**，前后端共用同一词表
- ✅ `provider_not_configured` 统一为 **HTTP 400** + `{"error": "provider_not_configured", "message": "LLM provider is not configured"}`
- ✅ 流式中途失败以一个安全的 `error` 事件收尾，不再是断掉的连接
- ✅ Chat UX：Enter 发送 / Shift+Enter 换行 / 输入框自动增高（上限 160px）/ Loading / Stop / Retry，失败不吞输入、不重复用户消息、不自动重试
- ✅ Conversation Management：Search / Rename / Pin / Unpin / Remove from view / New Chat，**只影响 Extension 本地展示状态**
- ✅ Context Preview & Control：面板显示 Project / Agent / 只读状态 / Context 来源 / 页面标题 / 选中文本摘要 / **实际将注入的内容**，采集 ≠ 发送
- ✅ Developer Context 兼容：User Mode 只有 Chat / Model Selector / Context / History / Settings；Developer Mode 额外增加既有只读面板
- ❌ 不新增 Phase 35 / Intelligence / Governance / Graph / Memory Evolution / Autonomous Agent
- ❌ 不新增自动执行 / 自动批准 / 自动修改源码 / Shell Executor / 权限提升 / 权限绕过
- ❌ 不新增自动 Web 采集 / 自动 Context 上传 / 自动 LLM 请求
- ❌ 不使用真实 API Key，不调用真实外部 LLM Provider（全部 mock）

完整用户链路（本阶段保持不变）：

```text
User
  ↓ First Launch
Onboarding（4 步，纯 UI，可随时 Skip）
  ↓ Settings
Provider Settings（API Key → Bridge → AES-256-GCM，202 pending → 人工审批）
  ↓ POST /provider/test
Test Connection（固定安全词表）
  ↓
Chat / Streaming（Enter 发送 / Stop / Retry）
  ↓ 用户点击 Ask AI
Capture Context → Preview → 用户显式发送问题
  ↓
LLM Gateway
  ↓ 只读
Developer Context
  ↓ executed=false
Tool Proposal
  ↓
ApprovalStore
  ↓
Human Approval
  ↓
Central Permission Boundary（既有受控执行器）
```

## Task 1 · First Run Onboarding

`browser-extension/src/assistant/onboarding.ts` + `store.ts` 的 5 个状态机方法。

| 步骤 | 标题 | 内容 |
|---|---|---|
| 0 | Start Local Bridge | `uvicorn app.main:app --port 8765`，扩展只访问 `127.0.0.1` |
| 1 | Configure Provider | 去 Settings 选 Provider；API Key 交给 Bridge 并在那里加密 |
| 2 | Test Connection | 用 Settings 的 Test connection；结果只是一个固定状态词 |
| 3 | Start Chat | 提问；助手只解释和起草，任何修改都停在提案 |

- 状态：`new`（首次启动自动显示）→ `active`（用户在走引导）→ `done` / `skipped` / `later`（三个 settled 状态）。`ONBOARDING_SETTLED_STATES` 之后**不再自动出现**，`later` 保留一个可点击的重开提示。
- 引导**是纯 UI**：没有 API Key 输入框、没有 Provider 写入、没有审批动作、没有执行控件。按钮只移动一个显示游标。
- Bridge 不可达、Provider 未配置时**每一步都能继续和跳过**（步骤下方只给一句 informational 进度提示，例如 `Bridge not detected — you can continue anyway`），用户永远能到达 Chat。
- 标记 `onboardingState` / `onboardingStep` 是非敏感本地状态，落在既有 `chrome.storage.local` 的 `ccb_state_v1` 里，**不改变任何权限边界**。

## Task 2 · Unified Error Experience

一个**封闭映射**：前端 `browser-extension/src/assistant/errors.ts`，后端 `local-bridge/app/assistant/errors.py`，两边词表一字不差（前端故意复制字符串而不是去后端取，Bridge 不可达时也能给出安全文案）。

| 情况 | 用户看到的唯一文案 |
|---|---|
| 401 / 403 | `Invalid API key` |
| 429 | `Rate limit reached` |
| 5xx | `Provider unavailable` |
| 网络 / Bridge 不可达 / 无法分类 | `Backend unreachable` |
| 用户点击 Stop | `Streaming stopped` |
| 未配置 Provider | `LLM provider is not configured` |
| 其他 4xx | `Provider rejected the request` |

- 后端所有 assistant 失败共用一个信封 `safe_error_body(code, message, detail)` → `{"detail", "code", "error", "message"}`：`error` + `message` 给扩展，`code` + `detail` 给既有 Phase 31/32/33 调用方。`message` 永远来自固定词表。
- **状态优先**：`provider_http_error` / `assistant_error` 这类"只说明 HTTP 调用失败"的 code 让位于 status（401 → Invalid API key，429 → Rate limit reached）；语义明确的 code（`context_consent_required` 等）保留自己的含义。前端 `STATUS_FIRST_CODES` 与后端 `safe_message_for_http` 对齐。
- **未配置 Provider 的状态码变更**：assistant API（`POST /assistant/chat`、`POST /assistant/chat/stream`）由 Phase 32 的 `422` 改为 Phase 34 文档规定的 **`400`**；Phase 31 的 `/llm/chat` 网关仍然是 `422`（未改动）。前端两个都接受，因此不依赖具体值。
- **流式中途失败**：响应已经开始就无法再回 JSON，`_stream_error_event()` 用一个 `{"type": "error", "content": <固定文案>, "toolCall": null, "provider": "", "model": ""}` 帧收尾，面板因此不会永远停在 "streaming"。
- 覆盖面：Chat / Streaming / Retry / Stop / Provider Settings / Onboarding 全部走 `safeErrorMessage()`。
- `sanitizeStatusText()` 是最后一道闸：任何不属于词表又携带禁止内容的状态行被**替换**成 `Backend unreachable`。

禁止出现在 UI 的内容（有正向测试逐条断言）：stack trace、内部路径、文件系统路径、API Key、Authorization Header、Provider Secret、Provider 原始响应、内部异常对象、数据库连接信息。

## Task 3 · Chat UX Refinement

`browser-extension/src/assistant/chat-view.ts` + `controller.ts`。

- **Enter 发送，Shift+Enter 换行**。`Ctrl` / `Meta` / `Alt` 组合与 IME `isComposing` 期间的 Enter 都不发送；空输入不发送。
- **输入框自动增高**，`MAX_COMPOSER_HEIGHT = 160`；超过上限后高度锁定、`overflow-y` 变 `auto`。
- **Loading 状态**与 **Stop** 只在 `streaming` 期间出现，同时 `chat-send` 禁用；此时不出现 Retry。
- **Stop**：`AbortController` 中止本次请求 → `stopAssistantStreaming()` 把流式 turn 标成 `{streaming: false, stopped: true}`，**已收到的内容全部保留**，状态变 `Streaming stopped`。不自动重试、不自动重发。
- **Retry** 只重发**最后一条用户消息**：删掉失败的尾巴、复用原文、`appendUserTurn: false`，因此**不会出现重复的用户消息**（有测试断言只有一条 `explain retries`）。
- **失败不吞输入**：发送失败时草稿被放回输入框，turn 标记 `failed: true`。
- 流式状态在成功 / 失败 / 取消后都回到可用态（idle / failed / cancelled），`controller.ts` 里没有 `setTimeout` / `setInterval` / 自动 retry。
- Markdown / 代码块渲染沿用 Phase 32（Language + Copy，无 Apply / Run）。

## Task 4 · Conversation Management

全部是 **Extension 本地展示状态**：`New Chat` 生成 `local_*` id，Search / Rename / Pin / Unpin / Remove from view 只改本地数组。

- 禁止且实现上不可能：删除 Backend Conversation、修改 Backend Conversation Storage、修改 Provider Key、创建 Tool Proposal、触发执行、触发 LLM 请求。有一条测试断言所有会话操作**接触 0 个 Bridge 方法**。
- 容错：id 冲突 / 损坏 JSON（`hydrate()` 只接受 object，异常回落到初始状态）/ 非法 id（select / remove / rename / pin 全部忽略未知 id）/ 删除当前会话（活动指针改到下一条，删空则 `assistantActiveConversation: null` 并渲染空态）。
- 搜索同时匹配标题和 turn 内容，大小写不敏感，query 上限 120 字符，Rename 输入上限 80 字符且自动 trim；重命名后不再自动改标题。

## Task 5 · Context Preview & Control

`browser-extension/src/assistant/context-panel.ts`。面板显示：Project、Agent、只读状态、Context 来源、页面标题、选中文本摘要，以及 **`injectedContextText()` 实际将注入的内容**（截断到 `CONTEXT_PREVIEW_LIMIT`）。

- **采集 ≠ 发送**：点 Ask AI 只把 bundle 放进瞬时状态，状态行明确写 `sent only with your next message`；Bundle 只随用户下一条消息发送一次，成功后丢弃，失败时保留以便重试。
- 用户可以**看 / 移除 / 决定是否包含**（`toggle-context-include` 关闭后 `web_context` 为 `null`，预览仍在）。Ask AI 之前面板显示 "Nothing would be sent"，并且没有包含开关。
- 无后台采集（`refreshContext` 不采集页面）、无刷新自动发送、未点 Ask AI 不读页面、无自动上传、无自动注入、无自动 LLM 请求。
- Bundle 在 `TRANSIENT_STATE_KEYS` 里，**永不持久化**（有测试断言序列化后的 storage 既不含页面标题也不含选中文本，重新 hydrate 得到 `null`）。
- 后端同意门未改动：`trigger != "ask_ai"` → `422 context_consent_required`；非 http(s) 来源 → `422 context_source_rejected`。

## Task 6 · Developer Context 兼容

沿用既有只读面板，未新增 Developer 能力。

- `USER_MODE_SURFACES`：`chat` / `model_selector` / `context` / `history` / `settings`
- `DEVELOPER_ONLY_SURFACES`：`project_context` / `code_context` / `tool_proposal` / `engineering_graph`
- `NEVER_AVAILABLE`（后端 `app/assistant/service.py` 与扩展 `src/assistant/types.ts` 一字不差）：`execute` / `approve_from_chat` / `apply_patch` / `auto_fix` / `auto_approve` / `shell`
- Tool Proposal 卡片只在 Developer Mode 渲染，且**卡片内没有任何按钮**。
- User Mode 里待审批只显示为一个计数（`approval-hint`），没有 `approve-action` 控件。

## Task 7 · UI / State 回归

- 新用户首屏是 **Chat**（`assistant-surface[data-mode=user]`，无 `developer-surface`）。
- 模式切换只改 `uiMode`：`onboardingState` / `onboardingStep` / `assistantProvider` / `assistantModel` / `assistantActiveConversation` / `assistantStreaming` / `assistantWebContext` / `assistantContextInclude` 全部不动。
- 重载后恢复模式、引导状态、Provider 与会话选择；**瞬时状态永不复活**（`assistantStreaming` → `false`、`assistantDraft` → `""`、`assistantWebContext` → `null`、搜索词与重命名态清空）。
- 五种引导状态下面板都能渲染，且没有任何 execute / approve / apply / auto fix / auto approve / shell / terminal / run 控件。
- 渲染一个失败 turn + 错误状态**不触发任何请求**（Retry 只是一个按钮，只有点击才会重发）。
- Governance / Intelligence / Tools / Developer Mode / Provider Settings / Context / History 面板无回归（Extension 全量 1776 项通过）。

## 测试

| 套件 | 数量 | 结果 |
|---|---|---|
| `browser-extension/tests/phase34-user-trial.test.ts` | 64 | passed |
| Extension 全量 `npx vitest run` | 1776（30 文件） | passed |
| `local-bridge/tests/test_phase34_user_trial.py` | 38 | passed |
| Phase 31/32/33 + `tests/security/` 定向回归 | 742 passed / 1 failed（既有环境问题） | 见下 |
| Backend 全量 `python -m pytest tests` | 3436 passed / 2 failed / 13 skipped（864s） | 2 个失败均为既有 Windows 环境问题，13 个 skip 是默认 SKIP 的真实 Provider 测试 |

Extension 分组：§1 Onboarding、§2 Error Handling、§3 Chat UX、§4 Conversation、§5 Context、§6 Security、§7 UI/State 回归。
后端分组：固定词表、`safe_error_body` 信封、`_error_response` 映射、`_stream_error_event` 帧、HTTP 表面、边界回归。

全部 mock：`no_outbound_network` autouse fixture 直接让 `httpx.HTTPTransport.handle_request` 抛 `ConnectError`，Provider 失败一律由 mock 抛出。**本阶段没有使用任何真实 API Key，没有调用任何真实外部 LLM Provider。**

## 安全边界（本阶段复核，未改动）

- Tool Call 永远只是 Proposal，`toolCallsExecuted` 永远 `false`
- Provider 写入 / Key 删除仍是 `202 pending` → `POST /permission/approve` → 人工批准；ApprovalStore 权限语义未修改
- API Key 只在 Settings 密码框里瞬时存在，链路固定为 `Extension → Backend → AES-256-GCM → Encrypted Storage`；`isForbiddenStateKey` 保证 credential 形状的键**永远不进 chrome.storage**
- `GET /user/settings` / `GET /provider/status` / `GET /context/status` 都不返回 `api_key` / `encrypted_api_key` / `authorization` / `secret` 字段（`keyEnv` 只是环境变量**名**，`keyHint` 只有掩码尾四位）
- Onboarding 状态只影响 UI，不改变任何权限边界
- UI 上没有 Execute / Approve / Apply / Fix / Auto Fix / Auto Approve / Run / Terminal / Shell 控件——但这被当作**产品行为**而不是安全边界，真正的边界在后端 `NEVER_AVAILABLE` + ApprovalStore

## 已知限制

- 本仓库当前没有 `.git` 目录，`git diff --check` 无法执行（记为 **not applicable**，不记为通过）。
- `npm run build` 的脚本用 POSIX 环境变量语法（`CCB_TARGET=content vite build`），Windows `cmd.exe` 下无法执行；MV3 构建走 `bash release/build-release.sh`（= `npm run release`）。
- `tests/security/test_phase26_intelligence_security.py::test_evaluation_does_not_mutate_prediction` 在 Windows 上因 `PermissionError: [WinError 32]`（tmpdir 清理时 SQLite 文件仍被占用）失败，与 Phase 34 无关，Phase 33 已存在。
- `tests/test_file.py::test_read_file_returns_content` 在 Windows 上因 CRLF 失败，同为既有环境问题。
- 错误分类依赖 status / code / 异常名 / 网络文案；无法分类的失败统一报 `Backend unreachable`，这是**有意的保守选择**（宁可说不准，也不回显任何内部文本）。

## Human-in-the-loop

打磨不改变权限模型。模型能做的最多是解释、起草和提出提案；任何真实修改都停在 `202 pending`，直到人在审批队列里点批准，再由既有受控执行器执行。

修改链路：`Patch Proposal → ApprovalStore → Human Approval → Central Permission Boundary`。

## 当前 Phase

Phase 34 - User Trial & Product Refinement。Phase 35 未开始。
