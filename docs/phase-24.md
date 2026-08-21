# Phase 24 Completion Report · Organization Engineering Strategy

Phase 24 已完成：在 Phase 22/23 组织级工程智能与组织图谱推理之上增加**组织工程战略层**。系统现在可以对多项目组织做跨项目影响分析、风险传播分析、工程策略生成与评估、战略建议、组织决策与决策模拟，并把战略对象（策略 / 决策 / 模拟）回写进 Organization Graph；仍然不能自动修改代码、自动执行、自动批准或绕过人工审批。

## 1. 模块结构

新增 `local-bridge/app/organization_strategy/`：

- `models.py`：`OrganizationImpactReport` / `OrganizationRiskReport` / `EngineeringStrategy` / `StrategyEvaluation` / `StrategicRecommendation` / `OrganizationDecision` / `OrganizationStrategySimulation` / `StrategyType` / `StrategyStatus` / `DecisionStatus` 与 `DECISION_TRANSITIONS`。
- `storage.py`：SQLite 持久化（strategies / decisions / simulations / memory 文档），全部写操作与既有存储隔离，不触碰组织图之外的任何数据。
- `analyzer.py`：Cross-Project Impact Analyzer（只读）。
- `risk.py`：Organization Risk Engine（只读）。
- `strategy.py`：Engineering Strategy Generator + Strategy Evaluator（只读生成，不自动选择）。
- `recommendation.py`：Strategic Recommendation Generator（只读）。
- `decision.py`：`OrganizationDecisionManager` 决策生命周期。
- `simulation.py`：确定性策略模拟（无随机、不调用外部模型）。
- `memory.py`：组织级 Memory 文档（只读查询 + 审批后追加）。
- `manager.py`：`OrganizationStrategyManager` 聚合入口。
- `routes.py`：9 个只读 GET + 5 个 POST（全部 ApprovalStore）。

## 2. Cross-Project Impact Analysis

`analyzer.py` 从 Organization Graph（层级 parent_id + 非层级边 + Phase 24 策略边）分析单个源节点的影响：

- **Direct / Indirect / Dependency Impact**：`IMPACTS` 按 source→target、`CAUSED_BY` / `DEPENDS_ON` 按 target→source、`RELATED_TO` 无向，BFS 收集 transitive 影响。
- **Team / Service / Architecture Impact**：沿层级聚合 affected teams / services / projects。
- **Dependency Paths**：输出经过共享 Repository / Service 的具体传播路径。
- **Incident Risk**：Incident 感知的聚合（源节点或下游项目上的 Incident 计入风险）。
- 输出 `OrganizationImpactReport`（impact_score / risk_level / confidence / blocking_issues）；缺失节点 404；**纯只读，测试断言多次调用不改写图**。

## 3. Risk Propagation Engine

`risk.py` 分析一个工程风险如何在组织中传播：

- 输入 `(node_id, severity, likelihood)`；沿非层级边传播，severity 每跳衰减。
- 输出 `OrganizationRiskReport`：`propagation_path`（含 `via` 边类型）、`affected_nodes`、`affected_projects/teams`、`impact`、`confidence`、`recommendations`。
- 非法 severity / likelihood 拒绝（400）；缺失节点 404；high severity 传播到共享仓库会生成 "Require human approval" 类建议。
- 只分析、不阻断；`confidence` 全确定性推导，测试断言无随机源。

## 4. Engineering Strategy Generator

`strategy.py` 根据 Organization Health / Technical Debt / Architecture Drift / Failure Intelligence / Risk Propagation / Cross-Project Impact / Organization Graph 生成候选策略，支持全部 7 类：

1. `REFACTOR`（由技术债/低健康触发）
2. `MIGRATION`（由缓存类失败模式触发）
3. `STANDARDIZATION`（由重复失败模式触发）
4. `DEPRECATION`（由架构漂移触发）
5. `TEST_IMPROVEMENT`（由低健康分触发）
6. `RISK_REDUCTION`（由高 Incident 触发）
7. `ARCHITECTURE_ALIGNMENT`（由架构漂移触发）

每个策略包含 problem / affected_projects / affected_teams / benefits / risks / estimated_effort / confidence / priority / alternatives / evidence（证据来自真实信号，测试断言）。空信号生成空列表。

**Evaluator**：多准则加权评估（criteria 权重和 = 1，测试断言），输出 `StrategyEvaluation`，只标记 `recommended`，**不自动 SELECTED**（测试断言）。

## 5. Organization Decision & Simulation

- `decision.py`：`OrganizationDecision` 生命周期 `PROPOSED → EVALUATING → APPROVAL_REQUIRED → APPROVED → ACTIVE → COMPLETED`（含 `CANCELLED` / `SUPERSEDED` 终态），全部状态迁移经 `DECISION_TRANSITIONS` 白名单并记录 history；非法迁移拒绝。
- `simulation.py`：确定性模拟（`MIGRATION` 扰动最高，测试断言），输出 risk / cost / maintainability / complexity / effort 预测；不可经 API 修改（测试断言）。

## 6. Organization Graph Integration

Phase 24 把战略对象**回写进 Organization Graph**（只写元数据，不碰项目源码）：

- `organization_strategy_create` → 创建 `STRATEGY` 节点 + `AFFECTS` 边（关联 affected projects）。
- `organization_strategy_evaluate` → 创建 `SIMULATION` 节点 + `EVALUATES` 边。
- `organization_strategy_decision_create` → 创建 `ORGANIZATION_DECISION` 节点 + `SELECTS` 边（标记策略 SELECTED）；`SUPERSEDED` 决策增加 `SUPERSEDES` 边。
- 严格层级（`PARENT_TYPE_CHAIN`）不被策略节点触碰；旧图数据在新增关系后仍可读（测试断言）。
- `context.py` 基础结构不变，新增只读信号字段：`organization_health / active_risks / cross_project_impacts / active_strategies / pending_decisions / technical_debt / architecture_drift / recommendations`。

## 7. Quality Gate 10.0 升级

`gate10.py` 保持 Phase 22 行为（旧参数与输出不变，测试断言），新增策略维度：

- `strategy_risk` / `architecture_risk` / `policy_violations` / `risk_propagation` 输入。
- 输出新增：`strategyScore` / `policyViolations` / `blockingIssues`（策略违规、架构风险、风险传播、低策略置信度可进入 blocking）。
- 无策略信号时保持原评分（兼容旧调用）。

## 8. API

`routes.py` 注册于 `main.py`：

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/organization/impact/{node_id}` | LEVEL_0 | 跨项目影响分析（只读） |
| GET | `/organization/risk/{node_id}?severity=&likelihood=` | LEVEL_0 | 风险传播分析（只读） |
| GET | `/organization/strategies/{project}` | LEVEL_0 | 策略列表（只读） |
| GET | `/organization/strategy/{strategy_id}` | LEVEL_0 | 策略详情（只读） |
| GET | `/organization/decision/{decision_id}` | LEVEL_0 | 决策详情（只读） |
| GET | `/organization/simulation/{simulation_id}` | LEVEL_0 | 模拟详情（只读） |
| GET | `/organization/recommendations` | LEVEL_0 | 战略建议（只读） |
| GET | `/organization/context` | LEVEL_0 | 组织战略上下文（只读） |
| GET | `/quality/v10/{org}?strategy_risk=&architecture_risk=&policy_violations=` | LEVEL_0 | Gate 10 策略维度 |
| POST | `/organization/strategy/create` | LEVEL_1 | 创建策略（ApprovalStore） |
| POST | `/organization/strategy/evaluate` | LEVEL_1 | 评估 + 模拟（ApprovalStore） |
| POST | `/organization/strategy/decision/create` | LEVEL_1 | 创建决策（ApprovalStore） |
| POST | `/organization/strategy/decision/transition` | LEVEL_1 | 决策状态迁移（ApprovalStore） |
| POST | `/organization/memory/append` | LEVEL_1 | 组织记忆追加（ApprovalStore） |

接线：`app/models/request.py` 新增请求模型；`app/security/permissions.py` 5 个 action 全部映射 **LEVEL_1**；`app/main.py` 注册路由并支持审批执行；`app/config.py` 新增存储路径。

## 9. Extension Dashboard

`browser-extension/src/organization/` 只读面板新增（`OrganizationDashboardData` 兼容旧字段，新字段可选）：

- **Cross-Project Impact**：impact_score / risk / confidence / dependency paths / blocking issues。
- **Risk Propagation**：severity/likelihood、传播路径、受影响节点、建议。
- **Active Strategies**：策略类型 / 状态 / 置信度。
- **Pending Decisions**：来自 context 的待审批决策。
- **Strategic Recommendations**：问题 → 建议 → 收益/风险。

纯只读：面板无任何 button/input，测试断言不出现 execute / apply / fix / rollback / auto approve 文案；`BridgeClient` 只暴露 GET 方法，无任何策略写入方法（测试断言 `organizationStrategyCreate` 等不存在）。

## 10. Security Review

- 9 个 GET 全部 `readOnly: true` 并写 Audit；测试断言多次读取不改写图、存储与项目。
- 5 个 POST 全部返回 202 + requestId，批准前零副作用（测试断言未审批的 create/evaluate/decision/memory 不产生任何写入）。
- 5 个 action 全部 LEVEL_1（测试断言无 LEVEL_2、无自动批准）。
- `OrganizationStrategyManager` 从不调用 `ControlledExecutor`（源码断言）；`strategy` 模块无 executor；routes 无隐藏执行路径。
- 安全回归：graph poisoning via reads 不可能、跨项目数据泄漏被阻断、权限提升不可能、模拟不可经 API 修改、confidence 无随机源。

## 11. Tests

新增 `local-bridge/tests/test_phase24_organization_strategy.py`（**167 个用例**）：

- Impact：direct/transitive、共享仓库路径、team 聚合、404、确定性、置信度边界、风险阈值、不改写图、自环忽略、Incident 感知。
- Risk：传播、severity 衰减、非法参数拒绝、影响等级、置信度、确定性、只读契约、高影响门控建议。
- Generator：7 类策略全覆盖、团队映射、证据真实、确定性、置信度、备选方案、优先级、必填字段。
- Evaluation：准则权重和 = 1、composite 边界、推荐最优、确定性、不自动选择。
- Decision：终态、非法迁移拒绝、history、持久化、策略/报告绑定、置信度钳制。
- Simulation：预测键/边界、确定性、持久化、只读标志。
- Recommendation：来自 health / risk / impact / debt / drift / simulation 的信号、空信号、证据真实。
- Memory：文档只读查询、审批后追加写文件、非法类别/空 org 拒绝、history 追加。
- Graph 集成：策略/模拟/决策节点与边同步、层级不受污染、旧数据兼容、context 信号字段。
- Gate 10：Phase 22 行为保留、新字段默认、违规阻断。
- API：GET 只读契约 + Audit、404、Gate 10 新旧参数兼容。
- Approval 集成：所有 POST 需审批、LEVEL_1、批准前零副作用、全链路 pipeline。
- 安全回归：无 executor、无隐藏执行、无自动批准、只读、无随机、不调用 ControlledExecutor、图毒化不可能、数据泄漏阻断、权限提升不可能。

验证结果：

- Phase 24 专项：**167 passed**
- Phase 22 + 23 回归：**70 passed**（无回归）
- Phase 21 Governance + Security 回归：**67 passed**
- Python `compileall`：通过
- `git diff --check`：通过
- Extension：`bun run typecheck` 0 错误；vitest **1103 passed**（含 Phase 24 只读面板与只读 client 断言）

## 12. Limitations

- 影响/风险/策略全部基于确定性图遍历与已登记信号（health / debt / drift / failure patterns），无语义/向量检索、无外部模型。
- 策略是**候选建议**，SELECTED 只能由人类决策产生；系统不自动选择、不自动执行。
- 模拟为确定性启发式，不替代真实迁移演练。
- 组织记忆为追加式文档，仅经审批写入，无自动提炼。

## 13. Phase 25 Proposal

- **Strategy Execution Tracking**：把已 APPROVED 的决策接入既有 Execution Loop（仍走 Proposal → Approval → ControlledExecutor），跟踪策略落地与收益回测。
- **Impact-aware Approval**：跨项目影响/风险报告作为审批预览的一部分呈现给人类审批者。
- **Pattern Library 战略映射**：Engineering Pattern Library 中的成功/失败模式自动关联到候选策略的证据链。
- **Graph Visualizer**：扩展端只读组织图可视化（层级 + 非层级 + 策略边）。
