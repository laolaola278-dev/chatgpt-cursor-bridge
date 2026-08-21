# Phase 30 · Context Intelligence & Developer Workflow Preparation

## 状态

Phase 30 在 Phase 29 的只读 Developer Context（Project / File / Symbol / Dependency / Git / Test-Build 六类 Bundle）之上，新增 **Context Intelligence Layer**：系统能够根据用户问题选择最相关的只读上下文，并对错误、测试失败、Git diff 和代码做确定性分析，生成建议与 Patch Proposal。

本阶段是**纯只读 Intelligence 阶段**。系统：

- ✅ 分析代码、错误、测试结果、Git diff、依赖关系
- ✅ 生成建议 / Finding / Review Context
- ✅ 生成结构化 Patch Proposal（仅记录，经 ApprovalStore + 人工审批后由既有受控执行器处理）
- ❌ 自动执行 / 自动批准 / 自动修改源码
- ❌ Shell Executor / 自动运行测试 / 自动安装依赖 / 自动 Git 操作
- ❌ 自动上传 Workspace（上下文只在用户显式发送后才进入 LLM）

完整链路：

```text
User
  ↓
Extension
  ↓
Context Intelligence（Query Analysis → Relevance Scoring → Ranking → Budget 2.0 → Dedup）
  ↓
Suggested Context（Preview / Add / Remove / Clear，默认不发送）
  ↓
User Explicit Send
  ↓
LLM Gateway（GPT / Claude / DeepSeek —— 本阶段不调用真实 Provider）
  ↓
Analysis / Suggestion
  ↓
Patch Proposal
  ↓
ApprovalStore
  ↓
Human Approval
  ↓
Existing Controlled Tools
```

Phase 演进：

```text
Phase 26  Engineering Intelligence Loop
        ↓
Phase 27  Engineering Intelligence Validation Layer（Prediction → Outcome → Evaluation → Metrics）
        ↓
Phase 28  Engineering Intelligence Governance Layer（Risk / Policy / Quality Gate 14.0 / Review）
        ↓
Phase 29  Advanced Developer Context & Read-only Code Intelligence
        ↓
Phase 30  Context Intelligence & Developer Workflow Preparation（本阶段）
```

## 模块（local-bridge/app/context/dev/intelligence/）

| 文件 | 职责 |
|---|---|
| `models.py` | `SuggestedContextResponse`、`RelationshipReport`、`ErrorContextBundle`、`TestFailureContext`、`GitDiffAnalysis`、`CodeReviewResult`、`InjectionReport`、`BudgetUsage`、`PatchProposalRecord`、`Phase30Snapshot` |
| `scoring.py` | `ContextRelevanceScorer`：按 filename / symbol / imports / references / dependency / selected code / git diff / test failure / error message / query keywords 计算 0–1 相关性分数，输出 score + reason + source + size |
| `dedup.py` | `ContextDeduplicator`：按 source identity + content hash + symbol identity 去重，确定性、项目隔离 |
| `budget2.py` | `ContextBudget2`：global / per-file / per-context-type 预算，按 relevance 排序保留高相关 Context、截断低优先级并标记 truncated，禁止静默超预算 |
| `relationships.py` | `CodeRelationshipAnalyzer`：import relationship / symbol reference / callers / callees / class inheritance / interface implementation / module dependency，只读复用现有索引 |
| `error_assistant.py` | `ErrorContextAssistant`：解析 error message / stack trace / HTTP error / build error / TS error / Python exception，生成 Error Context Bundle（source location / related file / symbol / dependencies / recent diff / relevant test），过滤 API Key、Authorization、password、token、secret、环境变量，移除 stack trace 绝对路径 |
| `test_failure.py` | `TestFailureIntelligence`：failed test / assertion / traceback / test file / related source / related symbol → Test Failure Context + Suggested Investigation；只生成 Patch Proposal，不自动运行/修改测试 |
| `git_intel.py` | `GitDiffIntelligence`：changed files / symbols / added-removed lines / affected tests / dependencies / change summary / potential impact / risk indicators / review points；禁 commit/push/merge/reset/checkout |
| `code_review.py` | `CodeReviewAssistant`：correctness / maintainability / security / performance / error handling / test coverage / API compatibility 启发式检查，输出 Finding（severity Info→Critical + location + explanation + recommendation），只建议不改代码 |
| `injection.py` | `PromptInjectionProtector`：区分 system instruction / user instruction / project content / tool output / external content；项目内容一律视为 UNTRUSTED DATA，检测 "ignore previous instructions" / "run this command" / "send secrets" / "approve this operation" 等信号 |
| `proposal.py` | `PatchProposalBuilder`：结构化 Patch Proposal（target file / target symbol / proposed change / reason / expected impact / risk），只记录，不写文件、不 auto_apply / auto_fix / direct_write / shell_execute |
| `engine.py` | `ContextIntelligenceEngine`：编排 scorer → dedup → budget → 组装 Suggested Context / Error / Test Failure / Git / Review / Injection / Snapshot |
| `index_source.py` | `ReadOnlyProjectIndex`：只读 CodeIndex 读取 + 扫描回退（未索引项目优雅降级），不写入索引 |
| `routes.py` | Phase 30 API（见下） |

其他接线：`app/models/request.py`（PatchProposalRequest）、`app/security/permissions.py`（patch_proposal_create LEVEL_1）、`app/main.py`（审批动作 `intelligence_patch_proposal`）。

## API

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/context/dev/intelligence/suggest?project=&query=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/relationships?project=&file=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/error?project=&error=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/test-failure?project=&test=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/git?project=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/review?project=&file=&symbol=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/injection?project=&text=&source=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/budget?project=` | LEVEL_0 只读 |
| GET | `/context/dev/intelligence/snapshot?project=` | LEVEL_0 只读（统一快照） |
| POST | `/context/dev/intelligence/patch-proposal` | LEVEL_1（ApprovalStore，202 pending） |

无 Execute / Shell / apply_patch / Auto Fix / Auto Approve / 直接写文件端点。Patch Proposal 只进入 ApprovalStore，人工批准后由既有受控工具执行。

## 安全边界

- 项目内容（文件、diff、测试输出）一律视为 **UNTRUSTED PROJECT CONTENT**，只作为数据，不作为系统指令
- Secret 过滤：API Key / Authorization / password / token / credential / 环境变量在错误与 diff 上下文中被脱敏
- Stack trace 绝对路径移除
- 预算与去重：确定性、项目隔离、禁止静默超预算
- 无自动上传 Workspace；Suggested Context 默认不发送，必须用户显式确认
- 所有潜在修改只以 Patch Proposal 形式存在，写入路径：`Proposal → ApprovalStore → Human Approval → Controlled Execution`

## 测试

- Backend：`tests/test_phase30_intelligence.py` + `tests/security/test_phase30_intelligence_security.py`（relevance scoring / ranking / bundle / dedup / budget / error context / test failure / git diff / code review / prompt injection / secret filtering / project & agent isolation / read-only & patch-proposal boundary / no shell / no execute / no auto apply / no auto approve / path traversal / malicious filenames）
- Extension：`browser-extension/tests/phase30-intelligence.test.ts`（Suggested Context / Ranking / Explanation / Error / Test Failure / Git Diff / Code Review / Budget / Dedup / Analysis Result / Patch Proposal UI / Developer Mode / Read-only boundary / Prompt Injection UI）
- 回归：Phase 12 / 25 / 26 / 27 / 28 / 29 全部通过，无破坏

## 完成标准核对

- [x] Context Intelligence（Query → Relevance → Rank → Prioritize → Summarize）
- [x] Context Relevance Ranking（score / reason / source / size，仅选预算内最高相关）
- [x] Code Relationship Analysis（imports / callers / callees / related symbols / related files，只读）
- [x] Error Context Assistant（secret / 绝对路径过滤）
- [x] Test Failure Intelligence（Expected / Actual / Related Code / Investigation，禁自动运行）
- [x] Git Diff Intelligence（change summary / impact / risk / review points，禁 Git 写操作）
- [x] Code Review Assistant（Finding + Severity + Location + Explanation + Recommendation）
- [x] Suggested Context（Preview / Add / Remove / Clear，用户最终确认）
- [x] Context Explanation（why this context / source / size / filtered / truncated）
- [x] Context Deduplication（source identity / content hash / symbol identity，确定性）
- [x] Context Budget 2.0（global / per-file / per-type / priority / truncation / ranking，UI 显示用量）
- [x] Developer Assistant UI（只读，无 Execute / Run / Apply / Fix / Approve）
- [x] Analysis Result UI（Copy / Expand / Collapse / Add-remove context，无 one-click fix）
- [x] Patch Proposal Preparation（结构化 Proposal，仅 ApprovalStore 路径）
- [x] Prompt Injection Protection（UNTRUSTED PROJECT CONTENT 模型）
- [x] Security Tests + Extension Tests + Backend Tests 全部通过
- [x] docs/phase-30.md + README 更新
- [x] 无自动执行 / 自动批准 / 自动源码修改 / Shell Executor / 权限绕过 / 真实 API Key / 外部 LLM 调用

## 当前 Phase

Phase 30 · Context Intelligence & Developer Workflow Preparation

（未新增 Phase 31）
