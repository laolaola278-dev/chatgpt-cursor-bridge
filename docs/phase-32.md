# Phase 32 · AI Assistant Productization

## 状态

Phase 32 在 Phase 31 的 LLM Provider Integration Layer 之上做 **产品化**：把已有的 Extension Chat 变成一个面向普通用户的 AI Assistant，同时把工程能力收进 Developer Mode。本阶段 **不新增任何执行能力**——产品化只改变"展示"与"同意"，不改变权限模型。

- ✅ User Mode（默认，首屏即 Chat）/ Developer Mode 双模式
- ✅ Provider Settings（OpenAI / Anthropic / DeepSeek）+ AES-256-GCM 加密存储 + Test Connection
- ✅ Chat / Streaming / Stop / Conversation History（Extension 本地视图）
- ✅ Ask AI 显式同意的 Web Context（采集 ≠ 发送，单次使用）
- ✅ 只读 Developer Context / 只读 Tool Proposal
- ❌ 不新增 Autonomous Agent / Auto Loop / Auto Tool Execution / Auto Approval / Auto Fix / Auto Patch / Shell / Terminal
- ❌ 不新增 Intelligence / Governance / Graph / Memory Evolution 能力，不做权限提升，不绕过 ApprovalStore
- ❌ 不开始 Phase 33

完整链路：

```text
User
  ↓
AI Assistant Extension（Shadow DOM Panel）
  ↓ User Mode（默认）/ Developer Mode
Chat
  ↓ 可选：用户点击 Ask AI → Web Context Bundle（单次）
  ↓ 可选：Developer Mode 只读 Developer Context
LLM Gateway（Phase 31 Provider Registry / Model Registry）
  ↓
GPT / Claude / DeepSeek
  ↓ 模型回复中的 Tool Call
Tool Proposal（只展示，executed=false）
  ↓ ApprovalStore
  ↓ Human Approval
Controlled Tools（既有受控执行器）
```

## 双模式 Surface

| Surface | User Mode | Developer Mode |
|---|---|---|
| Chat / Streaming / Stop | ✅ | ✅ |
| Model Selector（Provider + Model） | ✅ | ✅ |
| Context（Ask AI + 只读预览） | ✅ | ✅ |
| Conversation History（New Chat / Open / Remove from view） | ✅ | ✅ |
| Provider Settings（API Key / Base URL / Test Connection） | ✅ | ✅ |
| Sessions / 工程遥测计数 | ❌ | ✅ |
| Developer Context（Project / File / Symbol / Dependency / Git / Test） | ❌ | ✅ 只读 |
| Tool Proposal（Tool Name / Arguments / Waiting Approval） | ❌ | ✅ 只读 |
| Approval Cards（Approve / Reject） | ❌（只提示"切到 Developer Mode 审批"） | ✅ |
| Project Context / Code Context / Engineering Graph / Governance / Intelligence / Benchmark / Metrics | ❌ | ✅ 只读 |

- User Mode 是 **简化展示**，不是能力删除：后端一个端点、一个 Action、一条审批链都没有被移除。
- User Mode 下 `refreshContext()` 在拉完 assistant 三个只读端点后立即返回，**不请求任何 developer 工程数据**（`userSettings` / `providerStatus` / `contextStatus` 之外的端点一律不 touch）。
- 两种模式都不存在 Execute / Approve（User Mode）/ Apply / Fix / Auto Fix / Auto Approve / Run / Terminal / Shell 控件。

## Provider 与模型（Settings 页）

| Provider | 模型 | 状态来源 |
|---|---|---|
| `local` | `local/simulator-v1`、`local/architect-v1` | 始终 `Connected`（确定性模拟器，无凭据） |
| `openai` | `gpt-5`、`gpt-5-mini`、`gpt-4.1`、`gpt-4o`、`gpt-4-turbo` | 已批准凭据 → `Connected`；否则 `OPENAI_API_KEY`；否则 `Not configured` |
| `anthropic` | `claude-4-sonnet`、`claude-3-7-sonnet`、`claude-3-5-sonnet`、`claude-3-5-haiku` | 同上（`ANTHROPIC_API_KEY`） |
| `deepseek` | `deepseek-chat`、`deepseek-reasoner` | 同上（`DEEPSEEK_API_KEY`） |

- Provider allowlist 固定为 `("local", "openai", "anthropic", "deepseek")`；未知 Provider → 404，未知 Model → 422。
- Provider 状态词表固定：`Connected` / `Not configured` / `Failed`（附安全消息，见下）。
- 未配置的 vendor Provider 在 chat/stream 时快速失败（422），**绝不发起网络调用**；测试永不使用真实 Key（注入 mock transport）。

## 模块（local-bridge/app/assistant/）

| 文件 | 职责 |
|---|---|
| `crypto.py` | `SecretBox`：AES-256-GCM、随机 96-bit nonce、AAD = provider 名；**无明文回退**——cryptography 后端不可用时拒绝保存而不是降级存明文 |
| `store.py` | SQLite 凭据 + 偏好存储。API Key 只以密文信封落盘；新凭据落地为 `status='staged'`，只有 `activate_credential`（由审批动作分发器调用）才能启用；`public_credentials()` / `preferences()` 是唯一可序列化形状；日志只写 `fingerprint(api_key)` |
| `providers.py` | 凭据版 Provider Registry，叠加在 Phase 31 的 env-var Provider 之上；明文 Key 只存在于单次请求的调用栈内；`provider_catalog()` 返回状态 + 模型，**从不返回 Key** |
| `errors.py` | `safe_provider_failure()`：把任何失败映射为固定小词表 `Connected` / `Not configured` / `Invalid API key` / `Rate limit reached` / `Provider unavailable` / `Backend unreachable` / `Request rejected`——无 stack trace、无 Provider 原始响应、无 Header、无内部路径、无 Key |
| `context.py` | `build_web_context()` 拒绝缺少 `trigger="ask_ai"` 或同意时间戳的 bundle；`redact_secrets()` 脱敏；`render_context_block()` 把 Context 作为普通 system message 数据注入（是数据，不是指令） |
| `service.py` | 产品编排：user settings / provider staging + test / context status / 带同意 bundle 的 chat；**无执行、无源码修改、无自动批准** |
| `routes.py` | Phase 32 API（见下）；Audit 记录只写 provider / model / status / `contextIncluded` / `toolCallsExecuted=False` |

接线：`app/security/permissions.py`（3 个 LEVEL_1 + 6 个 LEVEL_0 动作）、`app/main.py`（`assistant_provider_config` / `assistant_provider_forget` / `assistant_settings_update` 三个审批分支）。

## 模块（browser-extension/src/assistant/）

| 文件 | 职责 |
|---|---|
| `types.ts` | `UiMode`、`WebContextBundle`、Provider / Model / Conversation / ToolProposal 视图类型 |
| `settings-view.ts` | `renderModeToggle` / `renderModelSelector` / `renderProviderSettings`；API Key 是 `type="password"` 的瞬时输入，读取后立刻清空 |
| `chat-view.ts` | `renderAssistantChat` / `renderChatTurn` / `renderHistory` / `renderToolProposal`；Tool Proposal 只有 Tool Name + Arguments + `Waiting Approval`，**零按钮** |
| `markdown.ts` | 安全 Markdown：段落 / 标题 / 列表 / 引用 / 行内代码 / 围栏代码块；无 `innerHTML` 路径；代码块只有 Language + Copy，**无 Run / Execute / Terminal / Shell** |
| `web-context.ts` | `renderAskAiButton` / `collectWebContext` / `renderWebContextPreview`；`safeUrl` 只接受 http(s) 并在 `?`/`#` 处截断；模块内只有 2 个 `addEventListener`（皆为按钮 click），无 load / DOMContentLoaded / visibilitychange / selectionchange / MutationObserver / 定时器 |
| `dev-context-view.ts` | 只读 Developer Context 行；整棵子树 0 个 `button/input/textarea/select`，源码无 `addEventListener` |

状态与控制：`src/state/store.ts` 用 `FORBIDDEN_STATE_KEY_FRAGMENTS`（`apikey` / `api_key` / `secret` / `authorization` / `credential` / `bearer` / `token` / `password`）+ `stripForbiddenKeys()` 让任何形似凭据的键都无法进入持久化状态；`TRANSIENT_STATE_KEYS` 保证 Web Context / Provider Test / Streaming 只活在内存里。`src/content/controller.ts` 负责 User Mode 早退、`signal` 驱动的 Stop、以及"同意 bundle 用一次即丢弃"。

## API

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/user/settings` | LEVEL_0 只读（provider / model / base_url / preferences / mode） |
| GET | `/provider/status` | LEVEL_0 只读（状态 + 模型，无 Key） |
| GET | `/context/status?project=&scope=` | LEVEL_0 只读（能力标志位） |
| POST | `/provider/test` | LEVEL_0（固定安全词表结果） |
| POST | `/assistant/chat` | LEVEL_0 无状态（不持久化、不执行） |
| POST | `/assistant/chat/stream` | LEVEL_0 无状态（SSE） |
| POST | `/provider/config` | LEVEL_1（ApprovalStore，202；批准后才 activate 已加密凭据） |
| POST | `/provider/forget` | LEVEL_1（ApprovalStore，202） |
| POST | `/user/settings` | LEVEL_1（ApprovalStore，202；只接受偏好白名单） |

Phase 31 API 全部保持兼容并继续可用：`GET /llm/providers`、`/llm/models`、`/llm/conversations`、`/llm/conversations/{id}`、`/llm/tool-proposals`、`POST /llm/chat`、`/llm/chat/stream`、`POST /llm/conversations`、`/llm/conversations/{id}/messages`、`/llm/conversations/{id}/tool-proposal`。Phase 29 的 `GET /context/dev/status` 继续作为 Developer Context 的只读来源被复用（未重新设计）。

`GET /user/settings` 响应中禁止出现 `api_key`、`encrypted_api_key`、`authorization`、`secret`。`GET /context/status` 只返回能力标志位（`requiresExplicitTrigger` / `trigger` / `automaticCapture:false` / `automaticUpload:false` / 字段名 / `readOnly`），不返回文件内容、Secret、API Key、内部路径或 Workspace 私密数据。

## API Key 安全链路（本阶段最高优先级）

```text
Settings 密码框（瞬时值，读取后立即清空）
  ↓ POST body（绝不进 URL / Query）
Backend
  ↓ AES-256-GCM（随机 nonce，AAD = provider）
Encrypted Storage（SQLite，只存密文信封）
  ↓ status='staged'
ApprovalStore → Human Approval（202）
  ↓ activate_credential
可用凭据（每次请求在内存中解密，用完即弃）
```

API Key 禁止出现的位置，以及本阶段的对应保证：

| 禁止位置 | 保证 |
|---|---|
| `chrome.storage` / Extension `localStorage` / `sessionStorage` | `browser-extension/src/{assistant,content,bridge}` 内零 `localStorage` / `sessionStorage` 引用；`stripForbiddenKeys()` 拦截所有形似凭据的状态键 |
| URL / Query Parameter | Key 只出现在 `POST /provider/config` 与 `POST /provider/test` 的 body |
| Console Log | 上述目录内零 `console.*` |
| Application Log | `store.py` 只记录 `fingerprint(api_key)`；`routes.py` 的 Audit 只记录 provider / model / status |
| Error Message | `safe_provider_failure()` 固定词表，不透传 Provider 响应或异常 |
| Response | `public_credentials()` / `provider_catalog()` / `user_settings()` 的形状里没有 Key 字段 |
| Chat Message / Context / Export / Analytics | Key 从不进入消息协议、Context Bundle 或导出物；Local Preferences 白名单只有 `mode` / `selected_provider` / `selected_model` / `onboarding_state` / `theme` / `language`，且 `set_preference` 主动拒绝含 `api_key` / `secret` / `token` / `password` / `authorization` / `credential` / `bearer` 的键 |

`POST /provider/test` 的错误映射：401 → `Invalid API key`、429 → `Rate limit reached`、5xx → `Provider unavailable`、网络失败 → `Backend unreachable`、未配置 → `Not configured`。

## Web Context 显式同意链路

```text
用户点击 Ask AI（唯一采集入口）
  ↓ collectWebContext()：Page Title / Page URL / Selected Text / Readable Content / Timestamp
Context Bundle（只在内存，只读预览，可 Clear）
  ↓ 用户主动发送下一条消息
Bundle 随该条消息发送一次
  ↓ 发送后立即丢弃（单次使用）
LLM Gateway
```

- 采集 ≠ 发送：点击 Ask AI 只产生 bundle，不发任何请求（`askAi()` 之后 Bridge 的 `touched` 端点集合为空）。
- 后端 `build_web_context()` 拒绝没有 `trigger="ask_ai"` 与同意时间戳的 bundle。
- 禁止且经测试证明不存在：后台自动抓取、自动上传、页面刷新自动发送、未点击即采集、自动向 Provider 发送 Context。
- URL 在采集时就被裁剪（去掉 query 与 fragment），`file://` 等非 http(s) 来源直接变成空串。
- Context 一律视为 **UNTRUSTED DATA**，以普通 system message 数据形式注入，并经 `redact_secrets()` 脱敏。

## 安全边界

- **无自动执行**：Assistant 链路上没有 execute / apply / run / patch 方法；Tool Call 只作为 Proposal 展示，Audit 固定写 `toolCallsExecuted=False`。
- **无自动批准**：凭据写入、凭据删除、偏好更新全部 202 pending → ApprovalStore → 人工审批；没有 auto-approve 端点，User Mode 干脆连 Approve 控件都不渲染。
- **无源码修改**：Developer Context 只读、只解释、只提议；一切修改仍是 `Patch Proposal → ApprovalStore → Human Approval → 中央权限边界 → 既有受控执行器`。LLM 不得直接修改源码。
- **无 Shell / Terminal**：代码块只有 Language + Copy；`assistant/` 源码经安全测试扫描，无 `os.system` / `subprocess` / `eval`。
- **Stop 语义**：Stop 只中止本次流式输出，保留已收到的 token，状态置为 `Streaming stopped`，**绝不自动重试**（`controller.ts` 经源码扫描无 `setTimeout` / `setInterval` / `retry`）。
- **History 只是本地视图**：New Chat / Open / Remove from view 只改 Extension 展示状态，不触碰 Phase 31 Conversation Storage（`state/store.ts` 经源码扫描无 `fetch(` / `BridgeClient` / `conversations/`）。
- **向后兼容**：Provider Registry / Model Registry / LLM Gateway / Chat / Streaming / Conversation / Agent / Context / ApprovalStore / Governance / Intelligence / Tools / Memory / Code Assistant / Extension Panel 全部保持原有行为。

## 测试

- Backend：`tests/test_phase32_assistant.py`（153）+ `tests/security/test_phase32_assistant_security.py`（38）= **191 passed**
  - 功能：user settings / provider catalog / staging + 审批激活 / forget / provider test 词表 / context status（user vs developer scope）/ 消息组装 / chat / streaming / 偏好白名单 / 加密信封 / 权限等级 / 路由
  - 安全：API Key 不返回 / 不入日志 / 不入错误 / 不入 URL；未知 Provider 与非法 Model 被拒；Provider 状态与 Test 安全；Context 需显式 Ask AI、无自动采集、无自动上传、无后台传输；Developer Context 只读、不自动改源码、不自动执行；Gateway 无 execute / shell / apply_patch、不能自动批准、不能绕过 ApprovalStore
- Extension：`browser-extension/tests/phase32-assistant.test.ts` **53 passed**；完整 Extension 套件 **28 files / 1690 passed**
- 回归：Phase 31 gateway + Phase 31 security + Phase 29 context(+security) + Phase 21 governance + Phase 30 intelligence(+security) 定向回归 **268 passed**
- 全量 Backend：3298 个用例，2 个失败，均为与 Phase 32 无关的既有 Windows 环境问题（两者在隔离运行时同样失败）：
  - `tests/security/test_phase26_intelligence_security.py::test_evaluation_does_not_mutate_prediction` — `PermissionError: [WinError 32]` 临时文件句柄未释放
  - `tests/test_file.py::test_read_file_returns_content` — conftest 用 `write_text` 写入，Windows 换行翻译成 CRLF
- 构建：`tsc --noEmit` 通过；MV3 双入口构建通过；`python -m compileall -q local-bridge/app` 通过

## 完成标准核对

- [x] User Mode 默认、首屏即 Chat，只有 Chat / Model Selector / Context / History / Settings
- [x] User Mode 不加载 Developer 工程数据，不展示 Governance / Intelligence / Graph / Metrics / Developer Context / Tool Proposal
- [x] Developer Mode 只额外增加只读分析面板，仍无 Execute / Approve / Apply / Fix / Auto Approve / Shell
- [x] Provider Settings（Provider / Model / API Key / Base URL / Test Connection / Provider Status）
- [x] API Key 链路 `Extension → Backend → AES-256-GCM → Encrypted Storage`，Extension 永不持久化明文
- [x] `POST /provider/test` 安全错误映射，固定安全词表
- [x] `GET /user/settings` 只返回非敏感字段
- [x] `GET /context/status` 只返回能力标志位
- [x] Chat / Streaming / Stop（不自动重试）/ Conversation History（Extension 本地视图）
- [x] 安全 Markdown（代码块只有 Language + Copy）
- [x] Ask AI 显式同意的 Web Context（采集 ≠ 发送，单次使用）
- [x] 只读 Developer Context（复用既有 Context 系统，未重新设计）
- [x] 只读 Tool Proposal（Tool Name / Arguments / Waiting Approval，零按钮）
- [x] Local Preferences 白名单，禁存任何凭据
- [x] Phase 32 backend / security / extension 测试 + Phase 31 与既有回归
- [x] docs/phase-32.md + README 更新
- [x] 未新增自动执行 / 自动批准 / 自动修改 / 自动抓取 / 权限提升 / ApprovalStore 绕过
- [x] 未开始 Phase 33

## 当前 Phase

Phase 32 · AI Assistant Productization
