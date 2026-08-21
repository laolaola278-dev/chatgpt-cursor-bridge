# Phase 21 Completion Report · Autonomous Engineering Governance Layer

Phase 21 已完成。系统现在可以长期观察工程健康、发现架构漂移、管理技术债、生成治理建议并记录工程演化历史；仍然不能自动修改代码、自动执行或绕过人工审批。

## 1. Engineering Health Monitor

新增 `local-bridge/app/governance/health.py`：

- `EngineeringHealthManager` 对 8 类信号做只读聚合：成功/失败率、回滚频率、失败韧性、测试稳定性、变更风险、Agent 表现、执行循环与验证记录。
- 输出 `EngineeringHealthReport`：`project / healthScore / riskLevel / trends / warnings / recommendations`，全部标记 `readOnly: true`。
- 生成可解释的告警（如 `test_stability_low`、`failure_frequency_high`、`rollback_frequency_high`）与建议（如 `improve_test_stability`、`gate_high_risk`）。

API：`GET /governance/health/{project}`（LEVEL_0，只读；每次读取写入健康快照供趋势对比）。

## 2. Architecture Drift Detection

新增 `local-bridge/app/governance/architecture/`：

- `ArchitectureDriftDetector` 将当前代码现实（文件/模块布局、导入边）与 Engineering Knowledge Graph 记录对比，检测 5 类漂移：
  - `unrecorded_dependency`（未记录依赖）
  - `module_boundary_change`（模块边界变化）
  - `circular_dependency`（循环依赖）
  - `design_decision_drift`（已批准设计决策无实现证据）
  - `deprecated_component_usage`（废弃组件仍被引用）
- 输出 `ArchitectureDriftReport`：`driftScore`（0-100）、`issues`（每条含 `type / severity / location / evidence / recommendation`）、`riskLevel`。

API：`GET /governance/drift/{project}`（LEVEL_0，只读；不修复、不阻止执行）。

## 3. Technical Debt Management

新增 `local-bridge/app/governance/debt/`：

- `DebtManager` 管理技术债 Item 生命周期（严格顺序状态机）：

  ```text
  OPEN → ANALYZING → PROPOSED → APPROVED → RESOLVED → VERIFIED
  ```

- 字段：`category / severity / source / affected_components / estimated_cost / risk`；非法跳转（如 `OPEN → APPROVED`）被拒绝。

API：

- `GET /governance/debt/{project}`（LEVEL_0，只读）
- `POST /governance/debt/create`（LEVEL_1，ApprovalStore）
- `POST /governance/debt/{debt_id}/transition`（LEVEL_1，ApprovalStore）

所有状态变化都通过 ApprovalStore 执行，不自动批准。

## 4. Engineering Policy Engine

新增 `local-bridge/app/governance/policy/`：

- `PolicyEngine` 注册 5 条确定性策略：`high_risk_change_requires_review`、`test_coverage_drop_warning`、`architecture_drift_approval_required`、`rollback_frequency_investigation`、`debt_growth_warning`。
- 每条策略只输出 `pass / warning / approval_required`；**不能自动阻止执行**，最多产生审批要求，仍需人工通过 ApprovalStore 批准。
- 输入信号键白名单校验，未知键拒绝。

API：

- `GET /governance/policies`（LEVEL_0，只读，含历史评估事件）
- `POST /governance/policy/evaluate`（LEVEL_1，ApprovalStore）

## 5. Governance Timeline

新增 `local-bridge/app/memory/governance/`：

- `GovernanceMemory` 按白名单分类保存到 `memory/governance/<project>/`：`health-reports.md`、`drift-reports.md`、`debt-history.md`、`policy-events.md`。
- 写入流程：Memory Proposal → Human Approval → Append（`append_after_approval` 只在批准后调用）。
- `GovernanceStorage`（SQLite）额外持久化 health / drift 快照、debt items 与 policy events。

API：

- `GET /governance/timeline?project=`（LEVEL_0，只读：最近快照 + memory 文档列表）
- `POST /governance/timeline/append`（LEVEL_1，ApprovalStore）

## 6. Governance Dashboard（Extension）

新增 `browser-extension/src/governance/`：

- `governance-dashboard.ts` 渲染只读面板：Engineering Health Score、Risk Trend、Architecture Drift、Technical Debt、Policy Events、Recommendation、Quality Gate 9.0 与 Governance Timeline。
- 纯只读：无 Fix / Apply / Execute 按钮；`BridgeClient` 仅暴露 6 个 GET 方法（health / drift / debt / policies / timeline / quality/v9），不暴露任何治理写方法。
- 面板数据随既有 Context 刷新周期拉取。

## 7. API 汇总

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/governance/health/{project}` | LEVEL_0 | 工程健康评分、风险、趋势、告警与建议 |
| GET | `/governance/drift/{project}` | LEVEL_0 | 架构漂移报告与 Issue 列表 |
| GET | `/governance/debt/{project}` | LEVEL_0 | 技术债列表（可按 status 过滤） |
| GET | `/governance/policies` | LEVEL_0 | 策略注册表与历史评估事件 |
| GET | `/governance/timeline` | LEVEL_0 | 治理时间线（快照 + memory） |
| POST | `/governance/debt/create` | LEVEL_1 | 创建记录型技术债，需审批 |
| POST | `/governance/debt/{debt_id}/transition` | LEVEL_1 | 技术债状态转移，需审批 |
| POST | `/governance/policy/evaluate` | LEVEL_1 | 评估策略并记录事件，需审批 |
| POST | `/governance/timeline/append` | LEVEL_1 | 追加治理记忆，需审批 |
| GET | `/quality/v9/{workflow_id}` | LEVEL_0 | Quality Gate 9.0 综合评分 |

## 8. Quality Gate 9.0

新增 `local-bridge/app/quality/gate9.py`：

- `QualityGate9Evaluator` 聚合 `healthScore / architectureRisk / debtScore / policyViolations` 输出 `recommendations` 与 `blockingIssues`，并计算 0-100 的 `quality` 分。
- 与既有 Gate 4-8 兼容：输出为增量只读评分，不自行 gate 或阻止执行。

## 9. Security Review

- 治理 GET 端点全部 `readOnly: true` 并写入 Audit；多次读取不修改任何源码（测试以 SHA-256 断言）。
- 治理 POST 全部返回 202 + `requestId`，必须经 `/permission/approve` 才执行；批准前不产生任何副作用。
- 4 个治理 action（`governance_debt_create` / `governance_debt_transition` / `governance_policy_evaluate` / `governance_memory_append`）全部映射 LEVEL_1。
- `EngineeringHealthManager` / `ArchitectureDriftDetector` / `DebtManager` / `PolicyEngine` / `GovernanceStorage` 源码不含 `subprocess` / `shell` / 批准改写路径；Policy Engine 只能产生 Warning 或 Approval Requirement。
- 未新增 Shell、外部模型调用、自动批准、自动执行或权限提升。

## 10. Tests

新增：

- `local-bridge/tests/test_phase21_governance.py`（51 个用例）：health 评分与告警、drift 5 类检测、debt 严格生命周期与非法跳转、policy 规则与白名单校验、ApprovalStore 集成（202 → approve → 执行 → 只读列表）、Governance Timeline memory 流程、Quality Gate 9.0、安全回归（源码不可变、无自动执行、LEVEL_1 映射、审计、无执行入口）。

新增扩展测试：

- `browser-extension/tests/governance-dashboard.test.ts`（110 个用例）：只读面板渲染、无按钮、BridgeClient GET 端点与 URL 编码、readOnly 保留、不暴露治理写方法。

验证结果：

- Backend full suite：**1565 passed**
- Extension full suite：**913 passed**（19 个测试文件）
- TypeScript：0 errors
- MV3 production build：通过
- Python `compileall`：通过
- `git diff --check`：通过

## 11. 接线说明

本阶段将此前已存在但未注册的 `register_governance_routes` 接入 `app/main.py` 的 `create_app()`，使全部 10 个治理端点实际可用；审批执行器 `_execute_action` 与 `ACTION_LEVELS` 对 4 个治理 action 的支持此前已具备，本次经测试验证。

## 12. Limitations

- 健康评分与漂移检测是确定性聚合分析，不进行预测性（ML）建模。
- 策略引擎不阻断执行链路，只能产生告警或审批要求；这符合安全边界，但意味着高风险信号需依赖人工审批流程落地。
- Governance Memory 为追加式，暂不支持编辑或删除条目。
- 扩展面板只读，治理写操作需通过 Local Bridge API 手动发起。

## 13. Phase 22 Proposal

- **Predictive Health Trending**：基于历史快照的回归趋势预测，标记「预计 30 天内进入 high risk」的项目。
- **Governance Report 导出**：将 health / drift / debt / policy 聚合为可导出的季度治理报告（复用 Artifact Export 管线）。
- **跨项目治理聚合**：多项目健康排行与风险对比视图（Extension 只读面板扩展）。
- **治理策略自定义**：允许用户在固定模板内调整阈值（仍由审批门控），不开放任意规则执行。
