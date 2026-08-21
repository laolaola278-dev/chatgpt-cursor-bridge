# User Flow Test · Phase 34

一次完整的真实用户走查记录：从安装扩展到发出第一个问题、看到错误、按 Stop、重试、开 Developer Mode，最后做安全验收。

**这份文档记录的是流程与验收标准，以及每个检查点对应的自动化覆盖。** 表格里的"覆盖"列指向真正执行过的测试；带 🖐 的行需要人工在浏览器里确认（自动化只能覆盖状态与渲染，无法覆盖"看起来对不对"）。

- 环境：Windows 11 / Chrome 或 Edge（MV3）/ `local-bridge` 本机 `127.0.0.1:8765`
- 构建：`bash release/build-release.sh`（8 步全绿，`release/AI-Assistant-extension.zip`，63,571 bytes，3 个运行时文件）
- **本次走查没有使用任何真实 API Key，没有调用任何真实外部 LLM Provider。** 所有 Provider 行为都由 mock 提供；需要真实凭据的验证在 `local-bridge/tests/real/`，默认 SKIP。

---

## 1 · 安装

| 步骤 | 期望 |
|---|---|
| 解压 `release/AI-Assistant-extension.zip` | 只有 `manifest.json`、`content/content.js`、`background/service-worker.js` |
| `chrome://extensions` → 开发者模式 → 加载已解压的扩展程序 | 加载成功，无错误徽标 |
| 查看权限提示 | 只有 `storage` + `scripting`，没有 `<all_urls>` |

- 验收：安装扩展**不授予任何执行权限**。装完之后系统能做的事和装之前一样多。
- 覆盖：`local-bridge/tests/test_phase33_release.py`（Manifest Audit / Required Files / Security Audit），`bash release/build-release.sh` 第 4–8 步。
- 🖐 人工确认：Chrome 权限对话框的实际文案。

## 2 · 首次启动（First Run Onboarding）

| 步骤 | 期望 |
|---|---|
| 打开 ChatGPT 页面，展开面板 | **首屏就是 Chat**，引导浮在上面 |
| 引导内容 | 4 步：Start Local Bridge → Configure Provider → Test Connection → Start Chat |
| Next / Back | 游标前后移动，Back 在第 0 步被夹住 |
| Skip / Setup Later | 引导消失；`Setup Later` 留一个可点击的重开提示 |
| Finish（第 4 步） | 引导关闭并落在 Chat |
| 重新打开面板 | 引导**不再自动出现** |

- 验收：引导里没有 API Key 输入框、没有 Provider 写入、没有审批动作、没有执行控件；按钮只移动一个显示游标。
- 验收：`onboardingState` / `onboardingStep` 是非敏感本地状态，**不改变任何权限边界**。
- 覆盖：`phase34-user-trial.test.ts` §`first run onboarding`（自动显示一次、四步文案、Next/Back 夹取、三个 settled 状态、marker 非敏感）。

## 3 · Bridge 未启动时继续

| 步骤 | 期望 |
|---|---|
| 不启动 `local-bridge`，走引导 | 每一步都能 Next 和 Skip |
| 第 0 步的进度提示 | `Bridge not detected — you can continue anyway` |
| 一路 Skip | 到达 Chat，可以浏览界面 |
| 尝试发消息 | `Backend unreachable`，**没有 stack trace、没有路径** |

- 验收：没有 Bridge、没有 Provider 也能完成或跳过引导。引导不是门。
- 覆盖：`phase34-user-trial.test.ts` §`first run onboarding`（无 Bridge 无 Provider 仍可跳过）+ §`unified error experience`（网络失败 → `Backend unreachable`）。

## 4 · Bridge 连接

| 步骤 | 期望 |
|---|---|
| `uvicorn app.main:app --port 8765` | Bridge 起来 |
| 面板 Connect | 状态变为已连接；项目下拉可选 |
| 引导第 0 步提示 | `Bridge reachable` |

- 覆盖：`local-bridge/tests/test_health.py`，`phase34-user-trial.test.ts` §`first run onboarding`（进度提示随信号变化，但不 gate）。

## 5 · Provider 配置

| 步骤 | 期望 |
|---|---|
| Settings → 选 Provider → 填 API Key → 提交 | `202 pending`，**不是立即生效** |
| 审批队列 | 出现一条待批准项，预览写明"key 已 AES-256-GCM 加密，永不显示/记录/导出" |
| 审批前查 `GET /provider/status` | `hasStoredKey: false`（配置仍然是惰性的） |
| `POST /permission/approve` | 配置激活 |
| 查看任意响应 / 日志 / 审计 | 没有 API Key、没有 Authorization Header |

- 验收：Key 链路固定 `Extension → Backend → AES-256-GCM → Encrypted Storage`；不进 `chrome.storage`、`localStorage`、URL、Query、Console、日志、错误信息、Response、Chat、Context、Export。
- 覆盖：`test_phase34_user_trial.py::TestBoundariesUnchanged::test_provider_config_is_still_approval_gated_and_key_free`、`test_no_response_body_ever_carries_credential_material`；`phase34-user-trial.test.ts` §`security acceptance`（credential 形状的键永不持久化、显示态只有 `****cdef`）。

## 6 · Test Connection

| 步骤 | 期望 |
|---|---|
| Settings → Test connection | 结果只是一个固定词：`Connected` / `Not configured` / `Invalid API key` / `Rate limit reached` / `Provider unavailable` / `Backend unreachable` / `Provider rejected the request` |
| 故意用错的 key（mock 401） | `Invalid API key` |
| 断网（mock ConnectError） | `Backend unreachable` |

- 验收：**绝不显示** Provider 原始响应、stack trace、Authorization Header、内部路径。
- 覆盖：`test_phase34_user_trial.py::TestUnifiedErrorHTTP::test_provider_test_still_answers_with_the_fixed_vocabulary`（四个 provider 全部落在词表内且响应体干净）。

## 7 · Chat

| 步骤 | 期望 |
|---|---|
| 输入问题，按 **Enter** | 发送 |
| **Shift+Enter** | 换行，不发送 |
| 输入多行 | 输入框自动增高，到 160px 后锁定并出现滚动条 |
| 空输入按 Enter | 什么都不发生 |
| 中文输入法组字中按 Enter | 不发送（`isComposing`） |
| 发送后 | 出现一条用户消息 + 一条助手消息；草稿清空 |

- 覆盖：`phase34-user-trial.test.ts` §`chat ux`（Enter/Shift+Enter、空输入与 IME、`autoGrowComposer` 上限夹取）。

## 8 · Streaming

| 步骤 | 期望 |
|---|---|
| 发送后 | 出现 `Loading…` 与 **Stop**，发送按钮禁用，此时**没有 Retry** |
| token 陆续到达 | 助手消息逐步增长 |
| 结束 | 回到 idle，Stop 消失 |
| 中途 Provider 挂掉（mock 429） | 流以一个 `error` 事件收尾，面板显示 `Rate limit reached`，**不会永远停在 streaming** |

- 覆盖：`phase34-user-trial.test.ts` §`chat ux`（loading/Stop 只在 streaming 期间、发送禁用）；`test_phase34_user_trial.py::TestUnifiedErrorHTTP::test_a_mid_stream_failure_ends_the_stream_with_a_safe_error_frame`（SSE 里同时有 `delta` 和 `error`，且整段响应文本无泄漏）。

## 9 · Stop

| 步骤 | 期望 |
|---|---|
| streaming 中点 Stop | 请求被 `AbortController` 中止 |
| 已收到的内容 | **全部保留**（用户消息和助手半句都在） |
| 状态 | `Streaming stopped` |
| 之后 | **不自动重试、不自动重发**；界面回到可用态 |

- 覆盖：`phase34-user-trial.test.ts` §`chat ux`（`stopAssistantStreaming` 保留两条 turn 内容、`signal.aborted === true`、状态回到 idle）。

## 10 · Retry

| 步骤 | 期望 |
|---|---|
| 一次失败后 | 出现 Retry，草稿被放回输入框（**输入不丢**） |
| 点 Retry | 只重发**最后一条用户消息** |
| 会话里的用户消息 | **只有一条**，不重复 |
| 成功后 | 助手内容更新，状态清空 |
| 不点 Retry | **什么都不发生**（等 20ms 后 `stream` 仍然只被调用过一次） |
| 没有失败消息 / 正在 streaming 时调用 | no-op |

- 覆盖：`phase34-user-trial.test.ts` §`chat ux`（Retry 语义、`chat-retry` 接线、无自动重试）+ §`ui and state regression`（渲染失败态不触发任何请求）。

## 11 · Ask AI Context

| 步骤 | 期望 |
|---|---|
| 未点 Ask AI 时看 Context 面板 | `Nothing would be sent`，没有包含开关，注入内容为空 |
| 点 **Ask AI** | 采集页面标题 / URL / 选中文本 / 可读正文；状态写明 `sent only with your next message`；**不发起任何请求** |
| 面板显示 | Project、Agent、只读状态、Context 来源、页面标题、选中文本摘要、**实际将注入的内容** |
| 关掉包含开关 | 下一条消息的 `web_context` 为 `null`，但预览还在 |
| 发送成功 | Bundle 丢弃（只发一次） |
| 发送失败 | Bundle 保留，便于重试 |
| 刷新页面 | Bundle **不复活**（瞬时状态，从不持久化） |
| 不点 Ask AI | 页面**不被读取**；没有后台采集、没有自动上传、没有自动 LLM 请求 |

- 严格顺序：`Ask AI → Capture Context → Preview → 用户显式发送问题 → LLM Gateway`。
- 覆盖：`phase34-user-trial.test.ts` §`context preview and control`（9 项）；`test_phase34_user_trial.py::TestBoundariesUnchanged`（`trigger != ask_ai` → `422 context_consent_required`、`file://` 来源 → `422 context_source_rejected`、不给 bundle 时 `contextIncluded: false`）。

## 12 · Developer Mode

| 步骤 | 期望 |
|---|---|
| User Mode 首屏 | 只有 Chat / Model Selector / Context / History / Settings |
| 切到 Developer Mode | 额外出现 Project Context / Code Context / Tool Proposal / Engineering Graph 等既有只读面板 |
| Tool Proposal 卡片 | Developer Mode 才渲染，且**卡片内没有任何按钮** |
| 所有 Developer 面板 | 没有 Execute / Apply / Auto Fix / Auto Approve / Shell / Terminal 控件 |
| 切回 User Mode | 引导状态、Provider 选择、会话选择、streaming 状态、Context 状态**全部不动** |
| 重载 | 模式与选择恢复；瞬时状态（streaming / draft / bundle / 搜索词 / 重命名态）**不复活** |

- 验收：User Mode 只是"简化展示"，**不删除任何后端能力**；Developer Mode 也**不增加**任何执行能力。
- 覆盖：`phase34-user-trial.test.ts` §`ui and state regression`（6 项）+ §`security acceptance`（Tool Proposal 只在 Developer Mode 且无按钮、`NEVER_AVAILABLE` 与 `USER_MODE_SURFACES` 不相交）。

## 13 · Error Handling

| 触发 | 用户看到的唯一文案 |
|---|---|
| 错误 API Key（mock 401） | `Invalid API key` |
| 限流（mock 429） | `Rate limit reached` |
| Provider 5xx（mock） | `Provider unavailable` |
| Bridge 没起 / 网络失败 | `Backend unreachable` |
| 点 Stop | `Streaming stopped` |
| 没配 Provider | `LLM provider is not configured`（HTTP **400**，`{"error": "provider_not_configured", ...}`） |
| 其他 4xx | `Provider rejected the request` |

覆盖面：Chat、Streaming、Retry、Stop、Provider Settings、Onboarding 全部走同一个映射。

- 验收：任何错误 UI 里**不出现** stack trace、内部路径、文件系统路径、API Key、Authorization Header、Provider Secret、Provider 原始响应、内部异常对象、数据库连接信息。
- 覆盖：`phase34-user-trial.test.ts` §`unified error experience`；`test_phase34_user_trial.py::TestSafeVocabulary` / `TestSafeErrorBody` / `TestErrorResponseMapping` / `TestStreamErrorEvent` / `TestUnifiedErrorHTTP`（其中 `assert_safe()` 对每个失败体逐条断言 13 类禁止片段不存在，包括一个真实形状的 vendor 泄漏文本）。

## 14 · Security Acceptance

| 检查 | 结果 |
|---|---|
| UI 上有 Execute / Approve / Apply / Fix / Auto Fix / Auto Approve / Run / Terminal / Shell 吗 | 没有（User Mode 和 Developer Mode 都逐个按钮断言过） |
| 待审批项在 User Mode 是什么 | 只是一个计数（`approval-hint`），没有 `approve-action` |
| Tool Call 会被执行吗 | 不会，`toolCallsExecuted` 永远 `false`，状态写 `Tool proposal waiting for approval.` |
| Chat 链路会碰审批 / patch / 执行端点吗 | 不会（发送路径接触的 Bridge 方法名逐个断言不含 `approve|reject|execute|patch|apply|shell`） |
| 会话操作会碰后端吗 | 不会（接触 0 个 Bridge 方法） |
| credential 形状的键会落盘吗 | 不会（`isForbiddenStateKey` + 持久化后的 blob 里没有 `sk-` / `Bearer` / `apiKey` / `access_token`） |
| 只读投影会泄露凭据字段吗 | 不会（`api_key` / `encrypted_api_key` / `authorization` / `secret` / `password` 字段名都不存在；`keyEnv` 只是环境变量**名**，`keyHint` 只有掩码尾四位） |
| Provider 写入 / Key 删除还需要人批准吗 | 需要，仍是 `202 pending` → `POST /permission/approve` |
| 用了真实 API Key 或调了真实 Provider 吗 | **没有**。`no_outbound_network` fixture 让 `httpx.HTTPTransport.handle_request` 直接抛 `ConnectError` |

**注意**：UI 上没有危险按钮是**产品行为**，不是安全边界。真正的边界在后端 `NEVER_AVAILABLE` + ApprovalStore + 既有中央权限边界。

最终链路（本阶段未改动）：

```text
User → Onboarding → Provider Settings → Chat/Streaming
     → Ask AI Context Preview → Developer Context
     → Tool Proposal → ApprovalStore → Human Approval
```

修改链路：`Patch Proposal → ApprovalStore → Human Approval → Central Permission Boundary`。

---

## 走查结论

| 项目 | 结果 |
|---|---|
| `browser-extension/tests/phase34-user-trial.test.ts` | 64 passed |
| Extension 全量 `npx vitest run` | 1776 passed（30 文件） |
| `npx tsc --noEmit` | 无诊断 |
| MV3 构建 `bash release/build-release.sh` | 8 步全绿，退出码 0 |
| `local-bridge/tests/test_phase34_user_trial.py` | 38 passed |
| Phase 31/32/33 + `tests/security/` 定向回归 | 742 passed / 1 failed（既有 Windows 环境问题，与 Phase 34 无关） |
| Backend 全量 `python -m pytest tests` | 3436 passed / 2 failed / 13 skipped（864.44s，退出码 1；2 个失败均为既有 Windows 环境问题，13 个 skip 为默认 SKIP 的真实 Provider 测试） |
| `python -m compileall -q app tests` | 退出码 0 |
| `git diff --check` | **not applicable**（本仓库没有 `.git` 目录） |
| 是否调用真实外部 Provider | **否** |

### 已知问题

- `tests/security/test_phase26_intelligence_security.py::test_evaluation_does_not_mutate_prediction`：`PermissionError: [WinError 32]`，tmpdir 清理时 SQLite 文件仍被占用。Phase 33 已存在，与 Phase 34 无关。
- `tests/test_file.py::test_read_file_returns_content`：Windows CRLF，同为既有环境问题。
- `npm run build` 在 Windows `cmd.exe` 下不可用（POSIX 环境变量语法），MV3 构建请走 `bash release/build-release.sh`。
- 🖐 标记的三项（权限对话框文案、面板视觉、Chrome 加载体验）需要人工在浏览器里确认，自动化无法覆盖。
