# Phase 16 Completion Report · Autonomous Engineering Loop (Approval Controlled)

> ChatGPT Cursor Bridge · 不要进入 Phase 17 · 等待确认

## 1. Architecture

Phase 16 在 Phase 15 受控执行之上构建完整工程闭环：

```
Problem → Analysis → Architecture → Planning → Proposal
   → Risk Evaluation → Approval Queue → Human Approval
   → Controlled Execution → Verification → Rollback → Learning Memory
```

新增 `local-bridge/app/execution_loop/`：

| 模块 | 职责 |
| --- | --- |
| `models.py` | `ExecutionLoop` + `LoopStatus`（CREATED → PLANNING → PROPOSAL_READY → WAITING_APPROVAL → EXECUTING → VERIFYING → COMPLETED；异常 FAILED / ROLLED_BACK / CANCELLED） |
| `storage.py` | SQLite `execution_loop.db`（`execution_loops` 表，UPSERT 保留子记录） |
| `orchestrator.py` | 唯一协调器：规划任务、生成 Proposal、收集 Verification、排队 Memory Proposal；**无任何文件/Shell/Action 执行能力** |
| `rollback_manager.py` | 按 reverse execution order 恢复快照（文件 + git state），API 层审批后才执行 |

新增 `local-bridge/app/execution/verification_pipeline.py`：

- 聚合 Git Diff、Test Result、Quality Score、Risk Score、Dependency Impact 生成 `VerificationReport`
- 只检测，不修复（`autoFix: false`）

新增 `local-bridge/app/quality/gate8.py`（Quality Gate 8.0）：

- 输入：approval_present / snapshot_present / verification_status / risk_level / rollback_capability / test_result / confidence
- 阻塞条件：无 Approval、无 Snapshot、Verification failed、Risk HIGH、Tests failed

## 2. 核心机制

### Loop Manager 状态机

- 白名单迁移表（`_ALLOWED`），非法迁移抛 `ValidationFailed`
- 每次迁移：写 Audit（`execution_loop_transition`）→ 追加 history → 持久化到 SQLite

### Approval 绑定

- `ApprovalStore` 新增 `execution_loop_id` 列与 `create(..., execution_loop_id=...)` / `attach_loop()` 支持
- `_execute_action` 中 `execution_execute` 分支检测任务所属 Loop：loop 任务由 `orchestrator.on_executed()` 接管（`EXECUTING → VERIFYING`），非 loop 任务保持 Phase 15 行为（独立 implementation memory proposal）

### Verification Pipeline

- `verify()` 在 `on_executed()` 之后由人工显式触发（`execution_loop_verify` 需 LEVEL_1 审批）
- PASS → `COMPLETED`；FAIL → `FAILED`；两种结局都会排队对应 Learning Memory Proposal

### Rollback

- `rollback()` 需要快照存在（无快照抛 404）
- 恢复顺序为 reverse execution order；恢复后 Loop → `ROLLED_BACK`

### Engineering Learning

- `memory/execution/` 新增：`execution-history.md`、`failure-patterns.md`、`engineering-lessons.md`
- 写入流程：Execution Result → Memory Proposal（`execution_memory_append`，LEVEL_1）→ 人工审批 → 写入
- 绝不自动写

## 3. API 列表

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/execution-loop/create` | LEVEL_1 | 创建 Loop（校验 plan 存在，404） |
| GET | `/execution-loop/list` | LEVEL_0 | 只读 Loop 列表 |
| GET | `/execution-loop/{id}` | LEVEL_0 | 只读 Loop 详情（含 verification / quality / rollback / memoryProposalId） |
| POST | `/execution-loop/{id}/prepare` | LEVEL_1 | 生成 Execution Proposal → PROPOSAL_READY → WAITING_APPROVAL |
| POST | `/execution-loop/{id}/verify` | LEVEL_1 | 生成 VerificationReport + Quality Gate 8.0 + 排队 Learning Memory |
| POST | `/execution-loop/{id}/rollback` | LEVEL_1 | 生成 rollback proposal（快照 restore 仅在本审批通过后执行） |
| GET | `/execution-loop/{id}/timeline` | LEVEL_0 | 只读迁移时间线 |
| GET | `/quality/v8/{workflow_id}` | LEVEL_0 | Quality Gate 8.0 只读评估 |

所有写接口统一走 `_register_pending` → `ApprovalStore` → `/permission/approve`（唯一执行入口）。

## 4. Security Review

- ✅ **无自动执行**：Scheduler/Orchestrator 均无 `execute()`；所有副作用经 ControlledExecutor + ApprovalStore
- ✅ **无自动批准**：恢复的 approval 必须 `reconfirm` 后才能 approve（有专项测试）
- ✅ **未批准 execute 零副作用**：源码字节在执行前后一致（有专项断言）
- ✅ **Rollback 必须有 snapshot**：无快照抛 404
- ✅ **Memory 二次审批**：Loop Learning Memory 生成独立 proposal，`memoryProposalId` 绑定 loop，独立人工审批
- ✅ **无 Shell / 无外部模型 / 无隐藏执行入口**：未新增任何 shell 或外部 API 调用路径
- ✅ Agent 无法提权：未新增 LEVEL_2 action，执行仍是 LEVEL_1 审批链
- ✅ 状态机白名单 + 非法迁移拒绝 + 全部迁移写 Audit

## 5. Tests

### Backend（`tests/test_phase16_execution_loop.py`）

- **149 passed**（要求 ≥120 ✓）
- 覆盖：Loop lifecycle、状态迁移白名单（18 合法 / 30 非法）、Proposal 生成与绑定、Approval binding（execution_loop_id）、VerificationPipeline（含 quality/risk/test 反映）、Quality Gate 8.0 阻塞条件、Rollback（快照必需 + reverse order）、Learning Memory 二次审批、Audit 事件、API 契约（202/404/readOnly）、安全不变量（无 execute 方法、未审批零副作用、恢复不自动批准）
- **Backend 全量：989 passed**（exit=0）

### Extension（`tests/execution-loop.test.ts`）

- **100 passed**（要求 ≥50 ✓）
- 覆盖：Loop Dashboard 渲染（状态、时间线、Quality Gate 8.0、blocking、rollback、memory proposal）、Timeline 渲染、只读保证（无 button/input/link、无 execute/auto-fix 文案、记录不可变）、BridgeClient 只读端点（list/detail/timeline/quality8）、URL 编码、禁止写方法
- **Extension 全量：484 passed**（14 files）

### 静态验证

- TypeScript：**0 errors**
- MV3 build：通过
- `python -m compileall`：通过

## 6. Known Limitations

- `execution-loop/{id}/rollback` 的 git reset 仅在快照含 `gitHead` 且项目为真实 git 仓库时执行；非 git 项目仅恢复文件快照
- `ExecutionLoopRollbackManager._reset_git` 使用 subprocess 调用 `git reset --mixed`（只读 repo 元数据操作，无 shell 展开），属于既有 Rollback 能力复用
- `find_by_task` 为 O(n) 全表扫描（loop 数量较小，可接受）
- Extension 一次仅展示最近一个 Loop 的 timeline 与 Quality Gate 8.0
- 浏览器视觉验证未执行（Chrome 不可用）

## 7. Phase 17 Proposal（仅建议，未开始）

1. **Execution Insights**：聚合 Loop 历史生成工程度量（成功率、平均风险、回滚率）
2. **Loop 恢复**：启动时扫描 EXECUTING/VERIFYING 的 Loop，标记 RECOVERED 并要求人工确认
3. **多 Loop 编排**：跨任务依赖的 Loop 顺序执行（DAG）
4. **Verification 自动合并**：将 Phase 10 的 Test Runner 结果自动并入 VerificationReport

> 本阶段未进入 Phase 17，等待确认。
