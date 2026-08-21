# Phase 28 · Engineering Intelligence Governance Layer

## 状态

Phase 28 在 Phase 27 的 Engineering Intelligence Validation Layer 之上增量实现，目标是让 Intelligence 从「可预测、可验证」进一步进入「可治理、可审计、可控风险」。本阶段不新增 Autonomous Agent，不扩大任何执行权限；Governance Layer 只能 Observe、Analyze、Evaluate、Measure、Classify、Recommend、Propose。

完整链路：

```text
Engineering Context
        ↓
Intelligence Prediction / Recommendation
        ↓
Evaluation
        ↓
Accuracy / Effectiveness
        ↓
Risk Analysis
        ↓
Governance Rules
        ↓
Quality Gate 14.0
        ↓
Governance Review Proposal
        ↓
ApprovalStore
        ↓
Human Review
```

Phase 演进：

```text
Phase 26  Engineering Intelligence Loop
        ↓
Phase 27  Engineering Intelligence Validation Layer
        ↓
Phase 28  Engineering Intelligence Governance Layer
```

## Architecture

新增/扩展的实际文件：

### Backend — `local-bridge/app/intelligence/governance/`

- `models.py`
  - `GovernanceRecord`：统一 Governance Core 记录，含 governance_id、source_kind/source_id、project_id、agent_id、model_id、policy_ids、risk_level、risk_score、confidence、evaluation_result、governance_result（PASS/WARNING/REVIEW_REQUIRED/BLOCKED）、reason、evidence、created_at、audit_request_id。
  - `RiskFinding`：Risk Analyzer 输出（risk_factors、similar_cases、reason）。
  - `PolicyViolation`、`ReviewProposal`（proposed/approved/rejected/executed）、`GovernanceMemoryRecord`（finding/risk/quality/policy_violation/review/history 白名单）、`GovernanceTrend`（deterministic trend_id = metric+period）。
  - `RiskLevel`（LOW/MEDIUM/HIGH/CRITICAL）、`GovernanceKind`（prediction/recommendation/decision/risk/model/context）、`PolicySeverity`（info/warning/blocking）。
- `storage.py`
  - `GovernanceStore`：SQLite 持久化 governance_records / risk_findings / policy_violations / review_proposals / governance_memory 五类记录，全部按 project_id 隔离。
- `risk.py`
  - `IntelligenceRiskAnalyzer`：确定性风险分类（低置信度、错误预测、高风险源、准确率下滑、相似高风险历史、模型不可靠、回归、敏感上下文等因子），分数 0-100，映射 LOW/MEDIUM/HIGH/CRITICAL；只分析、不处理。
- `rules.py`
  - `GovernanceRuleEngine` + `GovernancePolicyRegistry`：8 条确定性内置策略（confidence/accuracy/failure/regression/rejection/high-risk/sensitive-context/model-reliability）。策略只能产生 Warning 或 Approval Requirement（REVIEW_REQUIRED）；CRITICAL 风险仅标记 BLOCKED（供 Gate 14 阻断），引擎本身从不批准、执行或修改系统。
  - `PolicyRule`：版本化只读注册表；Intelligence 无任何改策略的端点。
- `trends.py`
  - `GovernanceTrendAnalyzer`：accuracy / effectiveness / decision_success / risk / confidence / model / agent 趋势，支持 daily/weekly/monthly；基于真实历史 Evaluation/Governance 记录，单一事件不产生确定性趋势；可识别 quality_degradation / regression / risk_escalation / model_degradation。
- `memory.py`
  - `GovernanceMemory`：只写 Governance Findings / Risk Findings / Quality Findings / Policy Violations / Review Outcomes / Historical Governance Decisions；写入必须走 Governance Proposal → ApprovalStore → Human Approval，禁止自动写 Memory。
- `review.py`
  - `GovernanceReviewEngine`：高风险 / Gate 失败 / 准确率下滑 / 回归 / 策略违规 / 模型退化时生成 Review Proposal；Proposal 只能进入 ApprovalStore → Human Review，无自动批准入口。
- `graph.py`
  - `GovernanceGraphBuilder`：只读 Governance Graph（Project → Agent → Prediction/Recommendation/Decision → Evaluation → Risk → Governance Finding），从不修改 Engineering Graph。
- `routes.py`
  - 注册 Phase 28 API（见下）。

### Backend — 其他

- `local-bridge/app/intelligence/phase28.py`
  - `build_phase28_snapshot()`：只读快照，汇总 records / risks / violations / reviews / memory / trends / signals / policies / graph / quality14。
- `local-bridge/app/quality/gate14.py`
  - `QualityGate14Evaluator`：Quality Gate 14.0，状态 PASS / WARNING / REVIEW_REQUIRED / BLOCKED；BLOCKED 必须阻断对应 Intelligence Proposal 的后续流程，Gate 本身不执行任何写入、不绕过权限边界。
- `local-bridge/app/main.py`
  - 新增受审批动作 `intelligence_governance_evaluate`、`intelligence_governance_review`（LEVEL_1），执行器在批准后写入记录 + 风险发现 + 违规 +（必要时）Review Proposal / Governance Memory。
- `local-bridge/app/models/request.py`
  - `IntelligenceGovernanceEvaluateRequest`、`IntelligenceGovernanceReviewRequest`。
- `local-bridge/app/security/permissions.py`
  - 两个 governance action 映射 LEVEL_1（元数据/审计写入，仍需人工审批）。

### Extension — `browser-extension/src/intelligence/`

- `models.ts`：Phase 28 类型（GovernanceRecord、RiskFinding、GovernancePolicy、PolicyViolation、GovernanceReviewProposal、GovernanceMemoryRecord、GovernanceTrend、GovernanceSignal、GovernanceGraph、IntelligenceQuality14、IntelligencePhase28Response）。
- `bridge/client.ts`：8 个只读 GET 方法（snapshot / risks / trends / policies / violations / reviews / quality-gate / graph）；无任何 governance 写方法。
- `intelligence-dashboard.ts`：只读 Governance Dashboard——Quality Gate 14 状态、风险分布、趋势与信号、策略违规、Review Proposals、Policy Registry、Governance Graph；无 Execute / Approve / Apply / Auto Fix / Auto Learn / Auto Govern 控件。
- `state/store.ts` / `content/controller.ts` / `ui/panel.ts`：接线 Phase 28 快照数据。

## API

### POST（全部经 ApprovalStore，返回 202 Pending）

| 端点 | 动作 | 说明 |
|---|---|---|
| `POST /intelligence/governance/evaluate` | `intelligence_governance_evaluate` | 治理评估（审批后写入记录 + 风险发现 + 违规 + 必要时 Review Proposal） |
| `POST /intelligence/governance/review` | `intelligence_governance_review` | 记录人工审查结果（审批后更新 Proposal + 追加 Governance Memory） |

### GET（全部只读、project-scoped）

- `GET /intelligence/governance`（快照）
- `GET /intelligence/governance/{id}`
- `GET /intelligence/governance/risk`（支持 risk_level / source_kind / agent_id 过滤）
- `GET /intelligence/governance/trends`（支持 period / agent / model）
- `GET /intelligence/governance/policies`
- `GET /intelligence/governance/violations`
- `GET /intelligence/governance/reviews`
- `GET /intelligence/governance/quality-gate`
- `GET /intelligence/governance/graph`
- `GET /quality/v14/{project}`

不存在 Execute / Shell / apply_patch / Auto Fix / Auto Approve / 策略修改端点。

## Security Boundary

严格保持：

- No automatic execution / approval / source modification / shell executor / permission escalation
- No automatic Memory write / Knowledge mutation / Governance mutation / Policy mutation
- Governance Layer 只 Observe / Analyze / Evaluate / Measure / Classify / Recommend / Propose
- Governance Memory 必须经 Governance Proposal → ApprovalStore → Human Approval
- 所有 Governance Review 可审计（audit_request_id 记录 + audit.jsonl）
- Project / Agent 隔离：所有查询与写入按 project_id 过滤，agent/model 可作过滤维度
- 不泄露 Secret / Authorization / API Key，不暴露内部敏感路径（sanitize_text 复用 Phase 25 边界）
- 不调用外部模型 / LLM / Provider API

## Quality Gate 14.0

`QualityGate14Evaluator` 检查项（任一不满足 → 对应状态）：

- BLOCKED：CRITICAL 风险 / risk_score ≥ 80 / benchmark < 0.4 / accuracy < 0.3 / blocking 违规 / 审计不完整
- REVIEW_REQUIRED：HIGH 风险 / accuracy < 0.5 / regression > 0.2 / benchmark < 0.6 / 存在违规
- WARNING：无数据或校准误差高
- PASS：全部通过

## Testing

### Backend（`local-bridge/tests/`）

- `test_phase28_governance.py` — Governance Core（记录生命周期、校验、隔离、过滤、持久化）
- `test_phase28_risk.py` — Risk Analyzer（因子、分数、等级、确定性、只读）
- `test_phase28_rules.py` — Rule Engine + Policy Registry（阈值边界、状态聚合、scope/版本、无批准能力）
- `test_phase28_quality_gate.py` — Quality Gate 14.0（四态、边界区间、优先级、只读）
- `test_phase28_trends.py` — Trend Analysis（方向、证据、单事件不判趋势、信号识别）
- `test_phase28_memory.py` — Governance Memory（白名单、审批后写入、隔离）
- `test_phase28_review.py` — Review Proposal（触发条件、生命周期、无自动批准）
- `test_phase28_graph.py` — Governance Graph（节点/边、去重、确定性、只读不改写）
- `security/test_phase28_governance_security.py` — 安全边界（无执行端点、审批门控、Project/Agent 隔离、Secret 隔离、Policy 不可变、审计、确定性、无外部调用）

结果：**Backend 277 passed（≥250）+ Security 66 passed（≥60）**，Phase 25–27 回归 737 项全部通过。

### Extension（`browser-extension/tests/intelligence-governance.test.ts`）

Governance Dashboard 只读渲染、8 个 client GET 方法、store 接线、类型契约、无写控件。结果：**129 passed（≥120）**，Extension 全量 1381 passed。

### 验证命令

- pytest（Phase 25–28 定向批次通过；完整套件受 180s 环境硬超时限制分批运行）
- TypeScript typecheck：0 errors
- MV3 build：通过
- Python compileall：通过
- `git diff --check`：通过

## 完成标准对照

- [x] Intelligence Governance Core（统一 GovernanceRecord，可追踪/审计/复现，Project/Agent 隔离）
- [x] Intelligence Risk Analyzer（7+ 因子、四级风险、确定性、只分析不处理）
- [x] Governance Rule Engine（8 条策略，只产生 Warning / Approval Requirement）
- [x] Intelligence Quality Governance（Quality Gate 14.0，BLOCKED 阻断 Proposal 流程）
- [x] Intelligence Trend Analysis（accuracy/effectiveness/decision/risk/confidence/model/agent）
- [x] Governance Memory（6 类白名单，全部 Proposal + ApprovalStore + Human Approval）
- [x] Governance Review Proposal（高风险自动生成 Proposal，仅入 ApprovalStore → Human Review）
- [x] Intelligence Governance API（POST 全部审批门控，GET 全部只读）
- [x] Governance Policy Registry（版本化只读，Intelligence 不可修改规则）
- [x] Governance Dashboard（只读，无 Execute/Approve/Apply/Auto Fix/Auto Learn/Auto Govern）
- [x] Engineering Graph 集成（只读 Governance Graph，不改写 Engineering Graph）
- [x] Security Boundary 测试（66 项）
- [x] Backend ≥250 / Extension ≥120 / Security ≥60 测试
- [x] 文档 `docs/phase-28.md` + README 更新

## Human-in-the-loop 边界（未破坏）

Prediction ≠ Action，Recommendation ≠ Execution，Governance ≠ Governance Mutation；无自动批准/执行/修复/学习/Memory 写入/Knowledge 突变/Policy 突变；所有持久化写入走 `Proposal → ApprovalStore → Human Approval → Controlled Write`。
