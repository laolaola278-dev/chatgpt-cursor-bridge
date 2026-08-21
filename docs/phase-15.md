# Phase 15 Completion Report · Controlled Engineering Execution System

> Status: **COMPLETED** — Phase 16 未开始。

Phase 15 在 Phase 14 的 Simulation / Engineering Plan 之上增加受控执行管理层：Plan → Implementation Task → Change Proposal → Human Approval → Controlled Execution → Verification。系统仍然不自动修改代码、不自动执行整个计划、不自动 commit / merge / publish，也不绕过 ApprovalStore。

---

## 1. Execution Architecture

新增模块 `local-bridge/app/execution/`：

| 文件 | 职责 |
| --- | --- |
| `models.py` | `ExecutionTask`、`ExecutionProposal`、`ExecutionOperation`、`ExecutionResult` 与任务/提案状态机枚举 |
| `planner.py` | 从已审批的 Engineering Plan 生成任务与提案元数据（proposal-only） |
| `task_builder.py` | 确定性解析 Plan 的 Files / Implementation Steps，拆分为 Implementation Task |
| `proposal.py` | 任务 → `ExecutionProposal`（operations、estimated_changes、risk_score） |
| `executor.py` | `ControlledExecutor`：审批、风险、路径、快照、Workflow 状态五项前置校验 + 可逆快照 + 确定性结果记录 |
| `verifier.py` | `VerificationService`：执行后自动生成验证建议（只分析，不自动修复） |
| `storage.py` | SQLite `execution.db`：`execution_tasks` / `execution_proposals` / `execution_results` |
| `manager.py` | `ExecutionManager`：任务生命周期、严格状态机、提案生成、受控执行与只读查询 |

```text
Engineering Plan (Phase 14)
        ↓  POST /execution/create (LEVEL_1)
Implementation Tasks (PROPOSED)
        ↓  POST /execution/{task_id}/proposal (LEVEL_1)
Execution Proposal (PROPOSED)
        ↓  POST /execution/{proposal_id}/execute (LEVEL_1)
Human Approval  →  /permission/approve
        ↓  ControlledExecutor
Snapshot + ExecutionResult + Verification
        ↓  独立 Memory Proposal → 再次人工审批
Execution Memory
```

## 2. Task System

- 输入：已审批的 Engineering Plan（`SimulationStorage.get_plan`）。
- 输出：每个 Implementation Step 生成一个任务，含 `files`、`dependencies`（其他步骤）、`risk`、`risk_score`。
- 状态机（非法迁移一律 `ValidationFailed`）：

```text
PROPOSED → APPROVAL_REQUIRED → APPROVED → EXECUTING → VERIFYING → COMPLETED
                                    │             │          └──→ FAILED / ROLLED_BACK
                                    └──→ FAILED / ROLLED_BACK
```

## 3. Proposal Flow

- 每个任务生成一个 `ExecutionProposal`：`operations`（file.patch + path + reason）、`estimated_changes`、`risk_score`。
- Proposal 只是元数据，不执行；提案生成后任务进入 `APPROVAL_REQUIRED`。
- `GET /execution/proposals`、`GET /execution/proposal/{id}` 只读。

## 4. Approval Integration

- 所有写入口复用既有 `_register_pending` + `ApprovalStore`：
  - `POST /execution/create` → action `execution_create`（LEVEL_1）
  - `POST /execution/{task_id}/proposal` → action `execution_proposal`（LEVEL_1）
  - `POST /execution/{proposal_id}/execute` → action `execution_execute`（LEVEL_1，唯一执行入口）
  - `execution_memory_append`（LEVEL_1）
- 执行仅由 `/permission/approve` 触发；`ControlledExecutor` 执行前强制校验：
  1. Approval exists（状态必须 APPROVED/EXECUTED）
  2. Risk unchanged（按当前任务重算 risk 必须与提案一致）
  3. Path valid（sandbox `validate_path`，拒绝穿越/绝对路径）
  4. Snapshot exists（先捕获 `workspace/execution_snapshots/<workflow|standalone>/<task_id>/metadata.json`）
  5. Workflow stage active（绑定的 Workflow 必须处于活跃状态）
- 执行结果不会写入项目源码；真实文件修改仍只能通过既有 `patch_apply` / `file_write` 审批管线进行。

## 5. Verification System

- `VerificationService` 执行后自动生成验证：`approval_verified`、`snapshot_captured`、`git_diff_present`、`tests_*`、`no_dependency_break`、`quality_score:N`、`files_analyzed:N`。
- 输出 `{status: PASS|FAIL, checks, autoFix: false}` —— 只分析，不自动修复。
- `GET /execution/{id}/verify` 只读查看验证结果；`GET /execution/results` 展示执行历史。

## 6. Security Review

- ✅ Scheduler / Planner / Coordinator 只能生成 Proposal，无 `execute()` 旁路。
- ✅ `ControlledExecutor` 不写项目文件、不运行 Shell、不修改 Memory。
- ✅ 快照只写入 `execution_snapshots`（可逆、可审计），git 状态仅 `rev-parse HEAD`（固定 argv、shell=False）。
- ✅ 未审批的 `execute` 请求不产生任何结果、任务停留在 `APPROVAL_REQUIRED`。
- ✅ 非法任务迁移被状态机拒绝。
- ✅ Execution Memory 写入必须二次人工审批（`Execution Result → Memory Proposal → Approval → Append`）。
- ✅ Decision（Phase 13）扩展 `implementation_plan_id` / `execution_status`，通过既有 `/intelligence/decision/create` 审批流写入。
- ✅ 未新增 Shell、外部模型 API、自动 commit、自动 merge、自动发布或隐藏执行路径。

## 7. API

| Method | Endpoint | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/execution/create` | LEVEL_1 | 从已审批 Plan 生成实现任务元数据 |
| GET | `/execution/tasks` | LEVEL_0 | 只读任务列表（project/status 过滤） |
| GET | `/execution/task/{id}` | LEVEL_0 | 只读任务详情与提案 |
| POST | `/execution/{task_id}/proposal` | LEVEL_1 | 生成执行提案 |
| GET | `/execution/proposals` | LEVEL_0 | 只读提案队列 |
| GET | `/execution/proposal/{id}` | LEVEL_0 | 只读提案详情 |
| POST | `/execution/{proposal_id}/execute` | LEVEL_1 | 唯一执行入口，须 `/permission/approve` |
| GET | `/execution/results` | LEVEL_0 | 只读执行历史 |
| GET | `/execution/{id}/verify` | LEVEL_0 | 只读验证结果 |
| GET | `/quality/v7/{workflow_id}` | LEVEL_0 | Quality Gate 7.0 |
| GET | `/memory/execution/history` | LEVEL_0 | 只读执行记忆时间线 |

## 8. Tests

- Backend Phase 15 专项：**210 passed**（任务构建 / 状态机 / 存储持久化 / 提案 / 执行前置校验 / 快照 / 验证 / Memory 审批 / Quality Gate 7 / API / Decision 集成）。
- Backend 全量：**840 passed**（`exit=0`）。
- Extension Phase 15 专项：**86 passed**（Dashboard 渲染与只读契约、BridgeClient 读取、无执行入口断言）。
- Extension 全量：**384 passed**。
- TypeScript：**0 errors**；MV3 production build：**通过**。
- Python `compileall`：通过；`git diff --check`：通过。
- 未启动服务；Chrome 不可用，未做真实浏览器视觉验证。

## 9. Phase 16 Proposal（建议）

1. **Execution Orchestration Loop**：把 Execution Task 接回 Runtime Scheduler，支持按依赖图顺序进入 `APPROVAL_REQUIRED`，仍保持 proposal-only。
2. **Test Verification Integration**：执行后自动把白名单 Test Runner 结果与 Quality Gate 7 合并进 Verification checks（仍不自动修复）。
3. **Rollback Execution 接线**：把 `execution_snapshots` 与既有 Stage Rollback 打通，提供 Execution 级回滚预览与审批。
4. **Execution Insights**：汇总执行历史到 Engineering Memory，形成长期执行指标（成功率、回滚率、平均验证分）。

等待确认后再开始 Phase 16。
