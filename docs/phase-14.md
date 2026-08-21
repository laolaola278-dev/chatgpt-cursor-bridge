# Phase 14 Completion Report

项目：**ChatGPT Cursor Bridge**  
阶段：**Engineering Simulation & Planning System**

Phase 14 在 Phase 13 Engineering Decision Intelligence 之上增加了一个只读工程方案模拟层。系统现在可以在实施前比较多个方案、预测影响、评估风险并生成可审阅的 Engineering Plan，但不会自动应用方案、修改代码、提交 Git、执行 migration 或更新 Memory。

所有可能产生副作用的路径仍然遵循：

```text
Analysis
  ↓
Simulation
  ↓
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

## 1. Simulation Architecture

新增 `local-bridge/app/simulation/`：

- `models.py`：`Simulation`、`Scenario`、`Evaluation`、`Plan` 及其生命周期状态。
- `planner.py`：读取 Phase 13 Proposal/Code Index 元数据，生成多个候选工程方案。
- `scenario.py`：`ImpactSimulator`，预测文件、依赖模块、测试、Workflow stage 和 Memory/ADR 影响。
- `evaluator.py`：基于变更范围、风险、测试覆盖、回滚难度、架构改善和维护成本的确定性评分。
- `storage.py`：SQLite `simulation.db`，持久化 simulations、scenarios、evaluations 和 plans。
- `manager.py`：协调创建、分析、评估读取和计划生成。

Simulation 生命周期支持：

```text
DRAFT → ANALYZING → COMPLETED → REVIEWING → APPROVED
                         └──────→ REJECTED → ARCHIVED
```

Scenario 默认生成三类候选方案：

1. **Minimal Patch**：小范围 patch，低影响。
2. **Module Extraction**：提取服务边界，改善耦合但涉及更多文件。
3. **Architecture Rewrite**：更大范围的结构调整，风险和影响最高。

这些记录是工程元数据，不是执行 Action。

## 2. Scenario Engine

每个 Scenario 保存：

- `changes`
- `affected_files`
- `dependent_modules`
- `affected_tests`
- `workflow_stages`
- `memory_impacts`
- `risk_score`
- `impact_score`
- `risk`

默认的 Workflow 影响链为：

```text
IMPLEMENTATION → TESTING → REVIEW
```

涉及架构边界的 refactor、rewrite 或 migration 会标记 `ADR required`。Impact Simulator 只读取 Code Index 和输入元数据，不导入、运行或修改项目代码。

Evaluation 输出：

```json
{
  "scenario": "scenario_...",
  "score": 82,
  "risk": "medium",
  "advantages": ["lower coupling"],
  "disadvantages": ["larger change"],
  "factors": {}
}
```

所有分数经过边界约束，不会自动降低风险等级。

## 3. Planning System

新增 `local-bridge/app/planning/generator.py`，生成只读 Markdown Engineering Plan：

```markdown
# Engineering Plan
## Problem
## Current State
## Selected Scenario
## Files
## Implementation Steps
## Testing Plan
## Rollback Plan
## Risks
```

Plan 描述实施方案，但自身不是执行入口。Plan 生成后仍然会创建单独的 Planning Memory Proposal，不会直接写入长期记忆。

新增 `local-bridge/app/memory/planning/`：

- `engineering-plans.md`
- `architecture-options.md`
- `tradeoff-history.md`

Memory 只有在独立的 `planning_memory_append` ApprovalStore 请求被用户明确批准后才会追加。

## 4. Decision Integration

Phase 13 Decision 增加了以下可选字段：

- `simulation_id`
- `selected_scenario`
- `confidence`
- `alternatives`

绑定关系为：

```text
Simulation
    ↓
Scenario Selection
    ↓
Phase 13 Decision Proposal
    ↓
Human Approval
    ↓
Engineering Plan
    ↓
Separate Memory Proposal
```

Decision 批准只会创建 Decision 元数据或 Plan 元数据；不会自动选择方案、改写源代码或批准 Memory。任何之后的实现动作仍必须重新进入既有 Permission/Approval 系统。

SQLite 持久化结构：

- `simulations`：项目、问题、状态、时间和生命周期历史。
- `scenarios`：候选方案、影响范围、风险和评估 JSON。
- `plans`：Simulation/Scenario 绑定、Markdown 内容和计划状态。

同时修复了一个持久化安全问题：Simulation 状态更新使用冲突更新而不是 SQLite `INSERT OR REPLACE`，避免父记录替换触发外键级联并删除已生成的 Scenario/Plan。

## 5. API

### Approval-gated

| Method | Endpoint | Boundary |
|---|---|---|
| POST | `/simulation/create` | LEVEL_1；只创建待审批 Simulation 元数据 |
| POST | `/simulation/{id}/analyze` | LEVEL_1；批准后生成候选方案和评估 |
| POST | `/simulation/{id}/plan` | LEVEL_1；批准后生成 Plan，并排队独立 Memory Proposal |
| POST | `/permission/approve` | 既有唯一执行入口 |

### Read-only

| Method | Endpoint | 内容 |
|---|---|---|
| GET | `/simulation/{id}` | Simulation 和已有 Plans |
| GET | `/simulation/{id}/scenarios` | 候选方案与影响范围 |
| GET | `/simulation/{id}/evaluation` | 方案评分、优点、缺点和评分因子 |
| GET | `/quality/v6/{workflow_id}` | Quality Gate 6.0 |
| GET | `/memory/planning/history` | Planning Memory 历史 |

未知 Simulation/Scenario 资源返回 404。旧 Phase 1–13 API 保持兼容。

Quality Gate 6.0 输出包括：

- `quality`
- `simulationConfidence`
- `alternativeCoverage`
- `riskPredictionAccuracy`
- `planCompleteness`
- `missingInformation`
- `readOnly: true`

## 6. Extension Dashboard

新增 `browser-extension/src/simulation/`：

- `models.ts`
- `simulation-dashboard.ts`
- `index.ts`

BridgeClient 增加只读读取方法：

- `simulation()`
- `simulationScenarios()`
- `simulationEvaluation()`
- `simulationPlans()`
- `simulationQuality()`
- `planningMemoryHistory()`

Dashboard 展示：

- Current Problem
- Candidate Solutions
- Risk / Impact Comparison
- Affected Files / Dependents
- Evaluation Score and Trade-offs
- Engineering Plan Preview
- Quality and Simulation Confidence

面板包含 `SIMULATION · READ ONLY` 标记，没有 Apply Scenario、Execute Plan、Approve、修复或表单控件。BridgeClient 只提供 GET 读取路径；新增写入仍由后端 API 的 ApprovalStore 负责，不由扩展直接执行。

## 7. Security Review

已验证并保持：

- Simulation、Scenario、Evaluation 和 Plan 不修改源文件。
- Planner、Impact Simulator、Evaluator 不调用 Shell、`subprocess` 或外部模型 API。
- `/simulation/create`、`/analyze`、`/plan` 全部先进入 ApprovalStore，不会自动执行。
- 计划批准后只生成 Plan 和独立 Memory Proposal；不会直接写 Memory。
- Memory 追加仍然要求第二次显式人工批准。
- 不新增 migration、Git commit、自动重构或自动任务执行路径。
- Agent 不能自行选择 Scenario 或降低风险等级。
- Simulation 数据不会改变 PermissionLevel、Agent permissions 或 Rollback 策略。
- SQLite 状态更新不会通过级联副作用删除候选方案和计划。
- Extension Dashboard 纯只读，不含执行按钮、审批按钮或数据库写入口。
- Unknown resource 使用 404，避免把不存在资源误认为可执行请求。

## 8. Tests

本次验证结果：

- Local Bridge 全量：**630 passed**
- Phase 14 后端专项：**120 passed**
- Browser Extension 全量：**298 passed**
- Phase 14 Extension Simulation 专项：**72 passed**
- TypeScript：**0 errors**
- MV3 content/background build：**通过**
- Python `compileall`：**通过**
- `git diff --check`：**通过**

后端专项覆盖：

- Simulation lifecycle 和 SQLite reopen
- 三方案生成和类型安全
- Impact 文件/依赖/测试/Workflow/Memory 预测
- Evaluation trade-offs、风险和回滚因子
- Plan sections、绑定校验和重新打开
- Planning Memory preview、append 和类别校验
- Approval-gated create/analyze/plan
- 第二次 Memory approval
- Recovery 不自动批准
- 未知资源、只读 API、无 subprocess
- Quality Gate 6.0 边界和 API contract

扩展专项覆盖：

- Dashboard problem/status/candidate/impact/evaluation/plan/quality 展示
- 空状态、高风险状态和候选数量边界
- read-only badge 和无 button/link/form 控件保证
- 输入对象不被渲染过程修改
- BridgeClient Simulation、Evaluation、Plan、Quality 和 Memory GET 路径
- URL 编码和 read-only 响应字段
- 不存在 apply/execute/approve/mutation 方法

当前环境未启动 Bridge 或开发服务；Chrome/Chromium 不可用，因此未执行真实浏览器视觉自动化。扩展编译、测试和 MV3 构建均已完成。

## 9. Phase 15 Proposal

仅提出建议，不实施 Phase 15：**Governed Implementation Batches**。

可在确认后考虑将已批准 Engineering Plan 拆分成带独立风险、回滚点和测试证据的实施批次；每个批次仍必须经过：

```text
Plan Batch
  ↓
Risk Re-evaluation
  ↓
Approval Queue
  ↓
Human Approval
  ↓
Existing Executor
```

Phase 14 到此结束，不进入 Phase 15，等待确认。
