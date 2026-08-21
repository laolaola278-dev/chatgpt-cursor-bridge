# Phase 10 Completion Report

项目：**ChatGPT Cursor Bridge**  
版本：**1.0.0**  
阶段：**Autonomous Development Runtime**

Phase 10 在 Phase 1–9 之上增量实现了一个可持久化、可恢复、可观测、但仍然受人工审批约束的 Runtime。没有新增通用 Shell、外部模型 API、隐藏执行路径或自动批准路径。

系统边界始终是：

```text
Proposal
  ↓
Risk Evaluation
  ↓
Approval Queue
  ↓
Human Approval
  ↓
Execution
```

Scheduler、Runtime Event、Task Queue 和 Browser Extension 都不能跳过这条边界。

## 1. Runtime 模块

新增 `local-bridge/app/runtime/`：

- `models.py`：`AgentRuntime`、`RuntimeState` 和 `ExecutionProposal`。
- `state_store.py`：每个 runtime 一个原子替换 JSON 状态文件，记录 `id`、Agent/Session/Workflow/Stage 绑定、当前状态、更新时间和历史。
- `scheduler.py`：校验 Session、Workflow、Agent 和 Task 绑定，只生成 `ExecutionProposal`。
- `executor.py`：显式阻断执行入口；调用会抛出 `ApprovalError`。
- `recovery.py`：启动扫描 `RUNNING` runtime 并转为 `RECOVERED`，记录审计；不恢复执行、不批准、不启动任务。

生命周期：

```text
CREATED → READY → RUNNING
                    ├→ WAITING_APPROVAL
                    ├→ WAITING_FEEDBACK
                    ├→ COMPLETED
                    └→ FAILED

RUNNING (restart) → RECOVERED → READY（用户确认后的元数据转移）
```

每次状态变化都会持久化并写入 Audit；开始运行时同时发布 `runtime.started`。

## 2. Task 系统

新增 `local-bridge/app/task/`，使用 SQLite `TASK_DB_PATH`（默认 `workspace/tasks/task.db`）和 WAL 模式。

`tasks` 表保存：

- `id`
- `workflow_id`
- `stage_id`
- `agent_id`
- `priority`
- `status`
- `context`
- `created_at`
- `updated_at`

状态：`PENDING`、`RUNNING`、`WAITING_APPROVAL`、`BLOCKED`、`COMPLETED`、`FAILED`、`CANCELLED`。所有迁移都经过 allowlist 校验；终态不可再次迁移。

`TaskManager` 提供 `create_task()`、`start_task()`、`complete_task()`、`cancel_task()`、`list_tasks()` 和 `get_task()`。创建与迁移通过 API 先建立 Pending Approval，只有用户批准后才改变 SQLite 状态。

## 3. Event Bus

新增 `local-bridge/app/event/`：

- `models.py`：事件包含 `event_id`、`timestamp`、`type`、`source`、`payload`、`audit_id` 和 SHA-256 `checksum`。
- `storage.py`：追加写入 `EVENT_ROOT/runtime.jsonl`，恢复时验证 checksum。
- `bus.py`：提供 `publish()`、`subscribe()`、`list_events()`、`recover_events()`。

支持事件类型：

`runtime.created`、`runtime.started`、`agent.started`、`task.created`、`task.completed`、`approval.required`、`approval.completed`、`execution.finished`、`memory.updated`。

每次发布都同步写入 `audit.jsonl`，共享 `audit_id`。篡改或损坏的事件不会被当作有效事件恢复，并会通过 `invalidCount` 暴露。

## 4. Agent Runtime 与 Message Protocol

新增 `app/agent/message/runtime_message.py`，支持 Planner、Architect、Coder、Tester、Reviewer 的运行时消息元数据：

- `message_id`
- `sender`
- `receiver`
- `type`：`REQUEST`、`RESPONSE`、`REPORT`、`BLOCK`、`APPROVAL_REQUIRED`
- `task_id`
- `workflow_id`
- `context_reference`
- `timestamp`

消息追加到 `MESSAGE_ROOT/runtime.jsonl` 并写入 Audit。消息只包含任务和上下文引用，不携带 Shell、工具权限或自动执行指令。既有 `/agent/message` 仍沿用 Preview → Approval → Execution。

## 5. Context Intelligence

新增 `app/memory/intelligence/context_builder.py`：

- Coder / Architect / Planner 读取 architecture、decisions、tasks。
- Tester 读取 tasks、changelog、decisions。
- 其他角色读取 project、changelog、tasks。
- 可附带受限的最近 Git diff。
- 输出 `contextId`、文档列表和摘要。

Context Builder 只有读取能力。它不会写 Memory、Workflow 或 Task；Memory 变更仍必须走 Memory Proposal → Approval → Memory Update。新增只读接口：

```text
GET /context/bundle?project=<name>&agent_role=CODER&task=<text>
```

## 6. Quality Gate 2.0

新增 `local-bridge/app/quality/`：

- `rules.py`：修改文件数量和风险扣分规则。
- `evaluator.py`：结合 Git diff、Test Runner 结果、风险等级、Memory 是否记录，输出确定性报告。
- `models.py`：`qualityScore`、`risk`、`blockingIssues`、`checks`。

检查内容：

- 修改文件数量（超过 5 个逐步扣分，超过 20 个形成阻塞问题）
- Test Runner 是否通过或缺少结果
- Risk Score / high-risk human review
- 是否存在 Memory 记录

接口：

```text
GET /quality/{workflow_id}
```

它只评估已提供的观察结果，不启动测试、不读取外部模型、不修改项目。

## 7. Recovery

启动过程在既有 Production Hardening 之后执行两类安全恢复：

1. `ApprovalStore.recover_pending()`：校验 TTL，将有效待审批请求改为 `RECOVERED`；用户必须先 `/permission/reconfirm`，再单独 `/permission/approve`。
2. `RuntimeRecovery.recover()`：将持久化 `RUNNING` runtime 标为 `RECOVERED`，记录 `requiresConfirmation: true` 和 `autoResumed: false`。

没有任何恢复代码调用 `_execute_action()`、`RuntimeScheduler.execute()` 或批准接口。

## 8. API 列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/runtime/status` | Runtime 状态、支持状态和 Execution Proposal 快照，只读 |
| GET | `/runtime/events` | 最近完整性校验后的 JSONL 事件，只读 |
| POST | `/runtime/create` | 创建 runtime 元数据的 Pending Approval |
| GET | `/agent/runtime` | 所有 AgentRuntime，只读 |
| GET | `/agent/{id}/state` | 某 Agent 的 runtime 状态，只读 |
| POST | `/task/create` | 创建 SQLite Task 的 Pending Approval |
| GET | `/task/list` | Task Queue 快照，只读 |
| GET | `/task/{id}` | Task 详情，只读 |
| POST | `/task/{id}/transition` | 任务迁移的 Pending Approval |
| GET | `/context/bundle` | Agent-specific read-only Context Bundle |
| GET | `/quality/{workflow_id}` | Quality Gate 2.0 评估，只读 |

所有新增 POST 接口都经过 Pydantic 校验、`ApprovalStore` 和 Audit。只读 GET 不会开放修改数据库或 Memory 的入口。

## 9. Extension Runtime Dashboard

新增 `browser-extension/src/runtime/`：

- runtime lifecycle status
- active / pending task queue
- waiting approval count
- recent event feed
- Quality score / risk / blocking issues
- recovered runtime warning

Dashboard 与既有 Project/Workflow Dashboard 一起由只读 refresh 流程加载。没有新增执行、批准、创建 Task 或直接写数据库的按钮；唯一的执行交互仍然是既有用户审批卡片。

## 10. Security Review

已保持并验证：

- Scheduler 没有可用的执行实现；`execute()` 明确拒绝。
- Runtime Executor 明确拒绝任何直接执行。
- Runtime 恢复永远不会自动继续。
- Task 非法状态跳转被拒绝。
- Event checksum 能发现 JSONL 内容篡改。
- Task、Runtime 和 Agent metadata 的写入仍先 Preview → Approval。
- 既有 Permission、Risk、Rollback 和 `shell=False` 安全逻辑未被替换。
- 没有新增 Shell、外部模型调用、环境修改或隐藏工具路径。
- Context 和 Quality 层为读取/评估逻辑，不直接修改 Memory。

## 11. Test Report

- Local Bridge full suite：**225 passed**（含 Phase 10 runtime、task、event、recovery、API、quality tests）。
- Phase 10 focused backend suite：**52 passed**（Runtime/Task/Quality/API）。
- Runtime lifecycle/recovery/security：覆盖创建、状态机、持久化、Proposal-only、恢复不自动执行、Event tamper detection。
- Task queue：覆盖 CRUD、SQLite 重载、优先级、状态迁移、终态、非法状态和完成事件。
- Quality：覆盖 score、risk、blocking issues、test/memory/file-count signals。
- Browser Extension：**103 passed**（含 Phase 10 Runtime Dashboard tests）。
- Extension TypeScript：`npm run typecheck` 通过。
- MV3 build：`npm run build` 通过，content/background bundle 均生成。
- Python：`compileall` 通过。
- `git diff --check`：通过。
- 未启动 Local Bridge、Next.js 或 Vite 服务。
- 当前环境没有 Chrome/Chromium，因此未执行真实浏览器视觉验证。

## 12. Phase 11 建议（未实施）

Phase 11 可在确认后考虑：

- 更完整的 Proposal → Approval UI 关联和人类风险解释。
- Task / Event / Runtime 的长期归档与指标聚合。
- 受限的多租户 Runtime 隔离与更细粒度身份审计。
- 只读运行报告导出和离线故障诊断工具。

**Phase 11 未开始。**
