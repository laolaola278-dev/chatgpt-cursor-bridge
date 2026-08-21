# ChatGPT Cursor Bridge

ChatGPT Cursor Bridge 是一个面向 ChatGPT 网页版的本地软件工程能力桥接系统。目标是让 ChatGPT 负责需求分析、架构设计、代码审查和调试推理，让本地 Bridge 负责安全的文件读写、项目管理、Git 操作、测试执行、长期记忆和权限审批。

当前阶段：**Phase 34 - User Trial & Product Refinement**。

> 完整开发链路：Issue -> Agent Analysis -> Proposal -> Approval -> Execution -> Verification -> Report。
> 已实现 Phase 0-25 全部代码，包含三层架构（Browser Extension / Local Bridge / Web Preview）、
> 43+ 个后端模块、31+ 个测试套件、完整的 Docker 部署配置。

### 阶段总览

- Phase 0：项目初始化方案，见 [`docs/phase-0.md`](docs/phase-0.md)
- Phase 1：本地桥接服务，见 [`local-bridge/README.md`](local-bridge/README.md)
- Phase 2：浏览器扩展，见 [`browser-extension/README.md`](browser-extension/README.md)
- Phase 3：项目记忆系统，见 `local-bridge/app/memory/`
- Phase 5：工作流编排，见 `local-bridge/app/workflow/`
- Phase 6：Git / Test Runner / Command Policy / Rollback，见 `local-bridge/app/git/`、`app/test_runner/`、`app/security/command_policy.py`
- Phase 7：Workflow Dashboard、Project Context、只读 Web Dashboard、Health、Audit rotation、Backup、Recovery，见 [`docs/phase-7.md`](docs/phase-7.md)
- Phase 8：持久化审批恢复、Context Intelligence、跨项目只读搜索、Session Runtime，见 [`docs/phase-8.md`](docs/phase-8.md)
- Phase 9：Model Router、多 Agent Runtime、消息审计、Workflow Quality Gate，见 [`docs/phase-9.md`](docs/phase-9.md)
- Phase 10：Runtime Core、SQLite Task Queue、Event Bus、Agent Context、Quality Gate 2.0、Recovery 与只读 Runtime Dashboard，见 [`docs/phase-10.md`](docs/phase-10.md)
- Phase 11：Multi-Agent Collaboration、Team、Dependency Graph、Negotiation、Conflict、Context Router、Metrics 与 Quality Gate 3.0，见 [`docs/phase-11.md`](docs/phase-11.md)
- Phase 12：只读 Code Intelligence、SQLite Symbol Index、Project Profile、Architecture Knowledge Graph、Context Query、Impact Analysis、Project Memory Layer 与 Quality Gate 4.0，见 [`docs/phase-12.md`](docs/phase-12.md)

- Phase 13：只读 Intelligence Layer、Failure Intelligence 与扩展 Knowledge Graph，见 [`docs/phase-13.md`](docs/phase-13.md)
- Phase 14：Simulation Engine、Test Scenario 与 Approval-gated Demo，见 [`docs/phase-14.md`](docs/phase-14.md)
- Phase 15：Execution DAG、Replay Engine、Artifact Export 与 Approval-gated Execution，见 [`docs/phase-15.md`](docs/phase-15.md)
- Phase 16：Execution Loop、Runtime Event、Planner 与 Approval-gated Loop，见 [`docs/phase-16.md`](docs/phase-16.md)
- Phase 17：Engineering Graph、Orchestration、Benchmark Execution 与 Approval-gated 交付，见 [`docs/phase-17.md`](docs/phase-17.md)
- Phase 18：Benchmark Dashboard、Engineering Knowledge Graph、Agent Profile、Model Provider Adapters 与 Production Readiness，见 [`docs/phase-18.md`](docs/phase-18.md)
- Phase 19：Engineering Validation、Reference Cases、Engineering Report 与 Production Readiness Check，见 [`docs/phase-19.md`](docs/phase-19.md)
- Phase 20：Product Release、Engineering Demo、Replay 与 Artifact Export，见 [`docs/phase-20.md`](docs/phase-20.md)
- Phase 21：Autonomous Engineering Governance Layer（Health Monitor / Drift Detection / Debt Management / Policy Engine / Governance Timeline / Quality Gate 9.0 / Governance Dashboard），见 [`docs/phase-21.md`](docs/phase-21.md)
- Phase 22：Enterprise Engineering Intelligence（Organization Knowledge Graph / Cross Project Learning / Engineering Pattern Library / Engineering Command Center / Quality Gate 10.0），见 [`docs/phase-22.md`](docs/phase-22.md)
- Phase 23：Organization Graph Intelligence（Graph Reasoning / 非层级 Edge 模型 / AI Context Injection / Snapshot Versioning），见 [`docs/phase-23.md`](docs/phase-23.md)
- Phase 24：Organization Engineering Strategy（Cross-Project Impact / Risk Propagation / Strategy Generator / Organization Decision / Gate 10 升级 / 战略只读面板），见 [`docs/phase-24.md`](docs/phase-24.md)
- Phase 25：Engineering Intelligence Evolution（Observation / Pattern Intelligence / Risk Prediction / Recommendation / Outcome / Decision Evidence / Intelligence Memory / Quality Gate 11 / 只读演化面板），见 [`docs/phase-25.md`](docs/phase-25.md)
- Phase 26：Engineering Intelligence 2.0 & Predictive Engineering（Trend / Correlation / Impact Prediction / Dependency Risk / Recommendation Ranking / Prediction Evaluation / Evidence Graph / Confidence Model / 只读预测面板），见 [`docs/phase-26.md`](docs/phase-26.md)
- Phase 27：Engineering Intelligence Validation Layer（统一 Evaluation Core / Prediction Accuracy / Recommendation Effectiveness / Decision Outcome / 确定性 Benchmark / Knowledge Improvement Proposal / Quality Gate 13.0 / 只读验证面板），见 [`docs/phase-27.md`](docs/phase-27.md)
- Phase 28：Engineering Intelligence Governance Layer（统一 Governance Core / Intelligence Risk Analyzer / Governance Rule Engine + Policy Registry / Governance Memory / Review Proposal / Quality Gate 14.0 / 只读治理面板 / Governance Graph），见 [`docs/phase-28.md`](docs/phase-28.md)
- Phase 29：Advanced Developer Context & Read-only Code Intelligence（Project / File / Symbol / Dependency / Git / Test-Build 只读上下文 Bundle + 显式预算与安全过滤 / 只读 Dashboard），见 [`docs/phase-29.md`](docs/phase-29.md)
- Phase 30：Context Intelligence & Developer Workflow Preparation（Query Analysis → Relevance Scoring → Ranking → Budget 2.0 → Dedup 的 Suggested Context / Error Context Assistant / Test Failure Intelligence / Git Diff Intelligence / Code Review Assistant / Prompt Injection Protection / Patch Proposal 准备），见 [`docs/phase-30.md`](docs/phase-30.md)
- Phase 31：LLM Provider Integration Layer（Provider Registry / Model Registry / 统一 Message Protocol / Chat / Streaming / Conversation + Agent 绑定 / Tool Calling Proposal，全部经 ApprovalStore），见 [`docs/phase-31.md`](docs/phase-31.md)
- Phase 32：AI Assistant Productization（User Mode / Developer Mode 双模式 / Provider Settings + AES-256-GCM API Key 加密存储 / Chat + Streaming + Stop / Conversation History（Extension 本地视图）/ Ask AI 显式同意的 Web Context / 只读 Developer Context / 只读 Tool Proposal），见 [`docs/phase-32.md`](docs/phase-32.md)
- Phase 33：Release & Real-world Validation（`release/` Release Package + 8 步发布构建 / Release Security Audit + Manifest Audit / INSTALL.md + CONFIG.md / User Mode 发布体验 / Provider 状态三态 / 默认 SKIP 的可选真实 Provider 验证 / 本机性能基线），见 [`docs/phase-33.md`](docs/phase-33.md)
- Phase 34：User Trial & Product Refinement（4 步 First Run Onboarding / 前后端共用固定词表的 Unified Error Experience / Chat UX（Enter 发送、Shift+Enter 换行、自动增高、Loading、Stop、Retry）/ 本地 Conversation 管理 / Ask AI Context 预览与控制 / UI-State 回归），见 [`docs/phase-34.md`](docs/phase-34.md)，用户走查记录见 [`docs/user-flow-test.md`](docs/user-flow-test.md)

> Phase 12 在 Multi-Agent Runtime 上增加项目理解能力，但不开放通用 Shell、自动修改或自动重构。Scanner、Index、Graph、Context Query、Impact Analysis 和 Extension Intelligence Dashboard 都不能绕过 Preview → Risk Evaluation → Approval Queue → Human Approval → Execution；索引写入与 Project Memory Proposal 仍需要显式审批。
> Phase 26 在 Phase 25 的 Observation / Pattern / Prediction 链路之上增加跨时间 Trend、Failure Correlation、Change Impact Prediction、Dependency Risk、Recommendation Ranking、历史 Evaluation 与 Evidence Graph。Intelligence 仍只负责 Observe、Analyze、Predict、Recommend、Learn；所有持久化写入仍必须经过 ApprovalStore 和人工批准，系统不会自动执行、修复、批准或修改源码，也不会将 correlation 伪称为 causation。
> Phase 27 在 Phase 26 之上建立 Engineering Intelligence Validation Layer：Prediction → Actual Outcome → Evaluation → Accuracy Metrics → Knowledge Improvement Proposal → Human Approval。统一 Evaluation Core、Accuracy/Precision/Recall/Calibration 统计、Recommendation Effectiveness（拒绝 ≠ 错误）、确定性 Benchmark 与 Quality Gate 13.0 让 Intelligence 可验证、可量化；Knowledge Improvement 永远只是 Proposal，禁止自动写 Memory / 自动修改 Knowledge。
> Phase 28 在 Phase 27 之上建立 Engineering Intelligence Governance Layer：Risk Analysis → Governance Rules → Quality Gate 14.0 → Governance Review Proposal → Human Review。统一 GovernanceRecord、确定性 Risk Analyzer、只读 Policy Registry（策略只产生 Warning 或 Approval Requirement）、审批门控的 Governance Memory 与 Review Proposal、只读 Governance Graph；Governance 层只能 Observe / Analyze / Evaluate / Measure / Classify / Recommend / Propose，禁止自动治理、自动批准、自动执行、自动 Memory 写入或 Policy Mutation。
> Phase 29 在 Phase 28 之上建立 Advanced Developer Context & Read-only Code Intelligence：把项目 / 文件 / 符号 / 依赖 / Git / 测试构建六类上下文组装成受预算约束的只读 Context Bundle，供 Assistant 在生成 Proposal 前理解工程现状。全部端点只读（GET），读取受 ContextBudget 限制、经敏感路径过滤与 secret 脱敏，从不执行、不写源码、不运行测试/构建/包管理器；符号解析增量扩展 interface / type / enum / variable，Phase 12 无回归。
> Phase 30 在 Phase 29 之上建立 Context Intelligence & Developer Workflow Preparation：根据用户问题计算 Context relevance（filename / symbol / imports / references / dependency / git diff / test failure / error message / query keywords），经去重与 Context Budget 2.0（global / per-file / per-type + 截断标记）组装 Suggested Context，并新增 Error Context Assistant、Test Failure Intelligence、Git Diff Intelligence、Code Review Assistant 与 Prompt Injection Protection。项目内容一律视为 UNTRUSTED DATA；一切修改只能以 Patch Proposal 形式经 ApprovalStore → Human Approval → 既有受控执行器处理。本阶段纯只读，不自动执行、不自动批准、不自动修改源码、无 Shell Executor、不自动上传 Workspace。
> Phase 31 在 Phase 30 之上建立 LLM Provider Integration Layer：Provider Registry / Model Registry 统一管理 OpenAI（GPT-5 / GPT-4 系列）、Anthropic（Claude 系列）与 DeepSeek（Chat / Reasoner），以统一 Message Protocol（system / user / assistant / tool）提供 Chat 与 Streaming（无状态计算）、Conversation 持久化（项目隔离、Agent 绑定）与 Tool Calling Proposal。未配置的 vendor Provider 快速失败（422）且绝不发起网络调用；本地确定性模拟器让系统无凭据可用；Conversation / Message / Tool Proposal 持久化全部走 ApprovalStore + 人工审批，Tool Call 只记录（executed=false）绝不执行，工具执行留在既有受控运行时。
> Phase 32 在 Phase 31 之上做 AI Assistant 产品化：Extension 默认进入 User Mode（首屏即 Chat，只有 Chat / Model Selector / Context / History / Settings，不加载任何 Developer 工程数据），Developer Mode 只额外增加只读分析面板（Project Context / Code Context / Tool Proposal / Engineering Graph 等）。新增只读产品 API `GET /user/settings`、`GET /context/status` 与 `POST /provider/test`（返回固定安全词表 Connected / Not configured / Invalid API key / Rate limit reached / Provider unavailable / Backend unreachable，绝不返回 stack trace、Provider 原始错误、API Key、Authorization Header 或内部路径）。API Key 只作为 Settings 密码框的瞬时值存在，链路固定为 `Extension → Backend → AES-256-GCM → Encrypted Storage`，禁止进入 chrome.storage / localStorage / URL / Query / Console / 日志 / 错误信息 / Response / Chat / Context / Export；Provider 写入与 Key 删除仍是 ApprovalStore 审批（202）。Web Context 必须由用户点击 Ask AI 显式触发采集，采集 ≠ 发送，Bundle 只随用户下一条消息发送一次随后即丢弃，无后台抓取、无自动上传、无刷新自动发送。Developer Context 与 Tool Proposal 全部只读（无 Execute / Approve / Apply / Fix / Auto Fix / Auto Approve / Run / Terminal / Shell 控件），代码块只有 Language + Copy；Stop 只停止本次流式输出且绝不自动重试；任何修改仍只能走 Patch Proposal → ApprovalStore → Human Approval → 受控执行器。User Mode 只是"简化展示"，不删除任何后端能力。

> Phase 33 在 Phase 32 之上做发布化：`release/` 提供 `AI-Assistant-extension.zip`（仅 `manifest.json` / `content/content.js` / `background/service-worker.js` 三个运行时文件）、`INSTALL.md`、`CONFIG.md` 与 8 步发布构建 `build-release.sh`（Clean → TypeScript → MV3 → Manifest Audit → Required Files → Security Audit → ZIP → Inspect ZIP，任一步失败退出码非 0）。Release Security Audit 拦截 `.env` / API Key / Secret / Authorization / Bearer / SQLite DB / Workspace / Tests / Source Map，并严格区分"变量名"与"真实密钥值"，因此文档里的 `OPENAI_API_KEY` 说明不会误报；Manifest 保持 MV3 与最小权限（`storage` + `scripting`），绝不添加 `<all_urls>`。发布版默认 User Mode（首屏即 Chat），普通用户默认看不到 Governance / Intelligence / Engineering Graph / Metrics / Developer Context；`GET /provider/status` 为 OpenAI / Anthropic / DeepSeek 返回 Connected / Not configured / Failed 三态，只显示掩码尾部，绝不返回 API Key、Authorization Header、内部异常或本地路径。可选的真实 Provider 验证放在 `local-bridge/tests/real/`，**默认全部 SKIP**，只有同时设置 `OPENAI_API_KEY` 与 `REAL_LLM_RUN=1` 才执行；429 / 5xx 一律走 mock transport（禁止为触发限流而发起滥用流量），且密钥 / Authorization / Provider 原始响应即使在测试失败时也不会进入日志、快照或报告。性能基线（后端 SQLite 往返 / 并发写入 / 长会话 / 流式事件，扩展 100 turn 渲染 / 100 token 累积 / 100 次状态更新）只记录本机 elapsed / average / max，不代表任何 Provider 的生产容量。本阶段不新增任何执行能力：安装扩展不授予执行权限，写操作仍停在 `202 pending` 等待人工审批，Phase 8 审批链路完整保留。

> Phase 34 在 Phase 33 之上做用户试用与产品打磨，把"可发布版本"变成"可长期给真实用户使用的稳定版本"，**不新增任何能力边界**。新增 4 步 First Run Onboarding（Start Local Bridge → Configure Provider → Test Connection → Start Chat）：首次启动自动出现且只出现一次，Next / Back / Skip / Setup Later / Finish 齐备，没有 Bridge、没有 Provider 也能一路跳过到 Chat；引导是纯 UI，没有 API Key 输入框、没有 Provider 写入、没有审批动作、没有执行控件，`onboardingState` 只是非敏感本地标记，**不改变任何权限边界**。Unified Error Experience 让前后端共用同一封闭词表（`Invalid API key` / `Rate limit reached` / `Provider unavailable` / `Backend unreachable` / `Streaming stopped` / `LLM provider is not configured` / `Provider rejected the request`）：401 / 403 → Invalid API key，429 → Rate limit reached，5xx → Provider unavailable，网络失败与无法分类的失败 → Backend unreachable，用户 Stop → Streaming stopped；未配置 Provider 由 assistant API 统一回 **HTTP 400** + `{"error": "provider_not_configured", "message": "LLM provider is not configured"}`（Phase 31 的 `/llm/chat` 网关仍是 422，未改动），流式中途失败以一个安全的 `error` 事件收尾而不是断连；错误 UI 里绝不出现 stack trace、内部路径、文件系统路径、API Key、Authorization Header、Provider Secret、Provider 原始响应、内部异常对象或数据库连接信息。Chat UX 补齐 Enter 发送 / Shift+Enter 换行 / 输入框自动增高（上限 160px）/ Loading / Stop / Retry：Stop 只中止本次流式输出并保留已收到的内容，Retry 只重发最后一条用户消息且不产生重复的用户消息，失败时草稿放回输入框，全程**不自动重试、不自动重发**。Conversation 的 Search / Rename / Pin / Unpin / Remove from view / New Chat 只影响 Extension 本地展示状态，容忍 id 冲突、损坏 JSON、非法 id 与删除当前会话，且不删除 Backend Conversation、不改 Provider Key、不创建 Tool Proposal、不触发执行或 LLM 请求。Context 面板显示 Project / Agent / 只读状态 / Context 来源 / 页面标题 / 选中文本摘要与**实际将注入的内容**，用户可看、可移除、可决定是否包含，严格保持 `Ask AI → Capture Context → Preview → 用户显式发送 → LLM Gateway`，采集 ≠ 发送，Bundle 只随下一条消息发送一次且从不持久化，无后台采集、无自动上传、无刷新自动发送、无自动 LLM 请求。User Mode 仍只有 Chat / Model Selector / Context / History / Settings，Developer Mode 只额外增加既有只读面板（Tool Proposal 卡片内无任何按钮）。本阶段不新增 Phase 35 / Intelligence / Governance / Graph / Memory Evolution / Autonomous Agent，不新增自动执行、自动批准、自动修改源码或 Shell Executor，不做权限提升、不绕过 ApprovalStore；Tool Call 永远只是 Proposal，任何修改仍是 `Patch Proposal → ApprovalStore → Human Approval → Central Permission Boundary`。测试全部 mock：**未使用真实 API Key，未调用真实外部 LLM Provider**；用户走查记录见 [`docs/user-flow-test.md`](docs/user-flow-test.md)。

## 三层架构

1. **Browser Extension Layer**
   - Chrome / Edge Manifest V3 插件
   - 注入 ChatGPT 网页 UI
   - 捕获 GPT 输出中的 `<action>` 指令
   - 展示审批面板
   - 与本地 FastAPI Bridge 通信

2. **Local Bridge Service**
   - Python FastAPI
   - 暴露安全 API
   - 管理本地 workspace
   - 执行文件、Git、命令、Memory 和权限控制逻辑
   - 所有敏感操作进入审批流程并写入日志

3. **Workspace Layer**
   - 管理用户项目、记忆、权限、日志
   - 默认目录：`workspace/`

## 目标目录结构

```text
chatgpt-cursor-bridge/
├ browser-extension/
│  ├ manifest.json
│  ├ src/
│  │  ├ content-script.ts
│  │  ├ background.ts
│  │  ├ injected-ui.ts
│  │  └ action-parser.ts
│  └ README.md
├ local-bridge/
│  ├ app/
│  │  ├ main.py
│  │  ├ api/
│  │  │  ├ health.py
│  │  │  ├ workspace.py
│  │  │  ├ project.py
│  │  │  ├ files.py
│  │  │  └ patches.py
│  │  ├ core/
│  │  │  ├ config.py
│  │  │  ├ security.py
│  │  │  ├ permissions.py
│  │  │  └ logging.py
│  │  ├ services/
│  │  │  ├ workspace_service.py
│  │  │  ├ file_service.py
│  │  │  ├ patch_service.py
│  │  │  └ memory_service.py
│  │  └ models/
│  │     ├ requests.py
│  │     └ responses.py
│  ├ tests/
│  ├ pyproject.toml
│  └ README.md
├ workspace/
│  ├ projects/
│  ├ memory/
│  │  ├ project.md
│  │  ├ architecture.md
│  │  ├ decisions.md
│  │  ├ tasks.md
│  │  ├ changelog.md
│  │  └ memory.db
│  ├ permissions/
│  └ logs/
├ docs/
│  └ phase-0.md
└ README.md
```

## Phase 0 交付物

- 完整项目目录结构草案
- 技术选型说明
- 分阶段开发路线图
- 关键风险分析
- Phase 1 基础桥接实施计划

详细内容见 [`docs/phase-0.md`](docs/phase-0.md)。

## MVP 边界

Phase 1 只实现本地服务基础桥接 API：

- `GET /health`
- `GET /workspace/list`
- `GET /project/tree`
- `GET /file/read`
- `POST /file/write`
- `POST /file/create`
- `POST /file/delete`
- `POST /patch/apply`

所有操作必须：

- 限制在 workspace 沙箱目录内
- 记录结构化日志
- 经权限系统判定
- 对修改、创建、删除、Patch 操作进行审批预留

## Phase 18 System Architecture

```text
ChatGPT / Extension
        |
        v
Proposal -> Risk Evaluation -> ApprovalStore -> Human Approval
        |                                      |
        +-------------- Controlled Execution -+
                                               |
                                               v
              Verification -> Engineering Graph -> Learning Memory
```

Phase 18 adds record-only Benchmark validation, read-only Engineering Knowledge Graph queries, long-term Agent Profiles, and metadata-only Model Provider Adapters. None of these components can execute Actions, invoke Shell, write Memory without approval, or change permissions.

### Security Model

- Read operations use LEVEL_0 and emit Audit records.
- Benchmark metadata and evolution-memory writes become LEVEL_1 ApprovalStore requests.
- Provider adapters are disabled metadata boundaries; responses become Agent Proposal data with `requiresApproval: true` and empty operations.
- Recovery never resumes execution automatically.
- CI runs validation and security regression tests only; it does not deploy.

### Execution Lifecycle

```text
Analysis -> Proposal -> Risk -> Approval Queue -> Human Approval
         -> Controlled Executor -> Verification -> Learning Proposal -> Approval
```

## Phase 19 Engineering Validation & Productization

- **Real Project Validation**：记录 ValidationProject / Scenario / Run，只记录、不绕过执行链
- **Reference Cases**：Bug Fix、Refactoring、Failure Recovery 三套标准流程
- **Engineering Report**：只读聚合 Problem / Analysis / Decision / Execution / Verification / Risk / Learning
- **Benchmark Dashboard**：扩展只读展示成功率、平均质量、回滚率、Agent 表现与失败模式
- **Production Readiness**：`GET /production/readiness` 检查环境、SQLite 迁移与备份恢复

## Phase 20 Product Release & Engineering Demo

完整演示链路：

```text
Issue → Agent Analysis → Proposal → Approval → Execution → Verification → Report
```

- `GET /demo/catalog` / `GET /demo/flow`：标准演示场景与流程
- `POST /demo/scenario`：记录只读 Demo 场景（Approval）
- `POST /replay/create`：从 Audit/Events/Validation 重建工程回放（Approval）
- `POST /artifacts/export`：导出只读工程报告与回放（Approval）
- `GET /production/readiness`：部署就绪检查（环境、Migration、Backup restore）

## 当前 Web 预览

本仓库保留一个 Next.js 工程状态预览页；Phase 7 的真实只读 Developer Dashboard 由 Local Bridge 的 `GET /dashboard` 提供。Local Bridge 仍作为独立 `local-bridge/` 服务运行。
