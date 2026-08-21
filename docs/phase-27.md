# Phase 27 · Engineering Intelligence Validation Layer

## 状态

Phase 27 在 Phase 26 的 Engineering Intelligence Loop 之上增量实现，目标是把 Intelligence 从「会预测、会建议」升级到「可验证、可量化、可持续评估」。本阶段不新增任何自动执行能力；所有具有持久化影响的写入仍必须经过现有 ApprovalStore 与人工批准。

核心闭环：

```text
Prediction
    ↓
Actual Outcome
    ↓
Evaluation
    ↓
Accuracy Metrics
    ↓
Knowledge Improvement Proposal
    ↓
Human Approval
    ↓
Next Prediction
```

Phase 26 → Phase 27 演进：

```text
Phase 26  Engineering Intelligence Loop
                    ↓
Phase 27  Engineering Intelligence Validation Layer
                    ↓
Prediction → Outcome → Evaluation → Metrics → Improvement
```

## Architecture

新增/扩展的实际文件：

### Backend — `local-bridge/app/intelligence/validation/`

- `models.py`
  - `EvaluationRecord`：统一 Evaluation Core 的记录模型，包含 prediction_id、evaluation_kind、input_context、prediction_result、expected_outcome、actual_outcome、evaluation_result、confidence、agent_id、model_id、project_id、decision_id、recommendation_id、evidence、时间戳。
  - `EvaluationResult`（correct / incorrect / partial / unknown）、`EffectivenessRecord`、`DecisionOutcomeRecord`、`BenchmarkRun`、`BenchmarkCaseResult`、`KnowledgeImprovement` 等数据模型。
- `storage.py`
  - `ValidationStore`：SQLite 存储（`settings.intelligence_db_path`），按 project_id 隔离 evaluations / effectiveness / decision_outcomes / benchmarks / improvements 五类记录；查询一律按 project 过滤。
- `accuracy.py`
  - `AccuracySystem`：只基于真实 Outcome 计算 accuracy / precision / recall / false_positive / false_negative / confidence_calibration / success_rate；没有 Outcome 时 counted=0，不伪造 benchmark。
  - 支持按 agent、project、prediction type、model、时间范围维度查询。
- `effectiveness.py`
  - `RecommendationEffectivenessEngine`：Recommendation → User Decision → Actual Outcome → Effectiveness。明确区分 rejected / incorrect / correct / partially_useful；「用户拒绝」不直接等同于「AI 错误」。
- `decision_outcome.py`
  - `DecisionOutcomeIntelligence`：Decision → Expected Outcome → Actual Outcome → Outcome Evaluation；按决策类型统计成功率（architecture / debugging / refactoring / test / dependency / risk）。
- `benchmark.py`
  - `BenchmarkRunner` + `builtin_datasets`：确定性可重复运行的 Benchmark System。数据集覆盖 Bug prediction、Failure prediction、Test failure prediction、Regression prediction、Refactoring/Testing/Architecture/Dependency recommendation、Project/Code/Dependency/Git diff understanding。
  - 同一数据集 + 同一预测输入，结果完全确定（无随机）。
- `knowledge.py`
  - `KnowledgeImprovementEngine`：只生成 Knowledge Update Proposal，禁止自动写 Memory / 自动 Knowledge Mutation。`apply_after_approval` 仅在人工审批通过后由受控执行器调用。
- `routes.py`
  - 注册 Phase 27 API（见下）。

### Backend — 其他

- `local-bridge/app/intelligence/phase27.py`
  - `build_phase27_snapshot()`：只读快照，汇总 evaluations / accuracy / failed predictions / effectiveness / decision outcomes / benchmarks / improvements / quality13，供 dashboard 使用。
- `local-bridge/app/quality/gate13.py`
  - `QualityGate13Evaluator`：Quality Gate 13.0。检查 Prediction / Evaluation / Outcome 可追踪、Accuracy 可计算、Recommendation Effectiveness 可计算、Benchmark 可运行、Knowledge Improvement 有审计记录、无自动知识写入、无权限绕过。检查失败时 gate 结果必须为 FAIL 并阻断发布。
- `local-bridge/app/main.py`
  - 新增受审批动作 `intelligence_evaluation_record`、`intelligence_benchmark_run`、`intelligence_knowledge_improvement`，全部注册进 `_register_pending` → `permission/approve` 流程（LEVEL_1）。
- `local-bridge/app/models/request.py`
  - 新增请求模型：`IntelligenceEvaluationRecordRequest`、`IntelligenceBenchmarkRunRequest`、`IntelligenceKnowledgeImprovementRequest`。

### Extension — `browser-extension/src/intelligence/`

- `models.ts`：新增 Phase 27 类型（IntelligenceValidationSnapshot、IntelligenceAccuracyReport、EffectivenessRecord、DecisionOutcomeRecord、BenchmarkRun、KnowledgeImprovement 等）。
- `bridge/client.ts`：新增只读客户端方法（accuracy / effectiveness / decision-outcomes / benchmarks / knowledge improvements / validation snapshot）。
- `intelligence-dashboard.ts`：Dashboard 新增只读展示区——Prediction Accuracy、Recommendation Effectiveness、Decision Success Rate、Benchmark Score、Confidence Calibration、Recent Evaluation、Failed Predictions、Knowledge Improvement Proposals。
- `ui/panel.ts` / `state/store.ts` / `content/controller.ts`：接线 Phase 27 快照数据。

## API

### POST（全部经 ApprovalStore，返回 202 Pending）

| 端点 | 动作 | 说明 |
|---|---|---|
| `POST /intelligence/evaluation` | `intelligence_evaluation_record` | 记录一次 Evaluation（审批后落库） |
| `POST /intelligence/benchmark/run` | `intelligence_benchmark_run` | 运行内置确定性 Benchmark（审批后落库） |
| `POST /intelligence/knowledge/improvements/propose` | `intelligence_knowledge_improvement` | 提交 Knowledge Improvement Proposal（审批后写入） |

### GET（全部只读、project-scoped）

- `GET /intelligence/evaluation/{id}`
- `GET /intelligence/accuracy`（支持 agent / project / type / model / time 维度）
- `GET /intelligence/effectiveness`
- `GET /intelligence/decision-outcomes`
- `GET /intelligence/benchmarks`、`GET /intelligence/benchmark/{id}`
- `GET /intelligence/knowledge/improvements`
- `GET /intelligence/validation`（Phase 27 只读快照）
- `GET /quality/v13/{project}`（Quality Gate 13.0）

不存在任何 Execute / Apply / Auto-fix / Auto-learn 端点。

## Security Boundary

保持严格不变：

- No automatic execution / approval / source modification / shell executor / permission escalation
- No automatic Memory write / Knowledge mutation
- 任何 Evaluation 只能 Observe、Evaluate、Measure、Recommend、Propose
- Knowledge Improvement 永远生成 Proposal，写入必须经 ApprovalStore + 人工批准
- Project / Agent 隔离：所有查询与写入均按 project_id 过滤；API 鉴权复用现有权限体系
- 不返回 Secret、Authorization、API Key，不暴露内部敏感路径
- 不调用外部模型 / LLM API（benchmark 使用确定性评分，模型可记录 model_id 元数据）

## Quality Gate 13.0

`QualityGate13Evaluator` 检查项（任一不满足 → FAIL 阻断）：

- Prediction 可追踪（prediction_id 存在且计数 > 0）
- Evaluation 可追踪（每条记录含 prediction_id 与 evaluation_result）
- Outcome 可追踪（expected + actual outcome 齐全）
- Accuracy 可计算（存在已计数样本）
- Recommendation Effectiveness 可计算
- Benchmark 可运行（内置数据集可用）
- Knowledge Improvement 有审计记录
- 无自动知识写入（no_auto_knowledge_write）
- 无权限绕过（no_permission_bypass）

空数据时与 Gate 11 约定一致返回 WARN（无证据不判 FAIL）。

## Testing

### Backend（`local-bridge/tests/`）

- `test_phase27_intelligence_evaluation.py` — Evaluation Core 记录/查询/审计
- `test_phase27_prediction_accuracy.py` — Accuracy / Precision / Recall / FP / FN / Calibration / 维度查询
- `test_phase27_recommendation.py` — Recommendation Effectiveness（rejected ≠ incorrect）
- `test_phase27_decision_outcome.py` — Decision Outcome Intelligence 与分类型成功率
- `test_phase27_benchmark.py` — Benchmark 确定性、数据集、评分
- `test_phase27_knowledge.py` — Knowledge Improvement Proposal（禁自动写入）
- `test_phase27_quality.py` — Quality Gate 13.0
- `security/test_phase27_intelligence_security.py` — 安全边界（Project/Agent 隔离、权限、Secret 隔离、禁止绕过 ApprovalStore、禁止 Knowledge mutation、无 Execute 能力）

结果：**Backend 223 passed（≥200）+ Security 50 passed（≥50）**，Phase 25–27 回归 737 项全部通过，无跳过、无删除失败测试。

### Extension（`browser-extension/tests/intelligence-validation.test.ts`）

Dashboard 只读视图、store/action 接线、client 端点调用。结果：**Phase 27 专项 100 passed（≥100）**，Extension 全量 1252 passed。

### 验证命令

- `pytest`（Phase 25–27 回归批次通过；完整套件受 180s 环境硬超时限制，分批运行）
- TypeScript typecheck：0 errors
- MV3 build：通过
- Python compileall：通过
- `git diff --check`：通过

## 完成标准对照

- [x] Intelligence Evaluation Core（统一 EvaluationRecord，含 agent/project/model 元数据）
- [x] Prediction Accuracy System（完整 Evaluation Record + 多维度统计，不伪造 benchmark）
- [x] Recommendation Effectiveness（rejected ≠ incorrect）
- [x] Decision Outcome Intelligence（分类型成功率）
- [x] Intelligence Benchmark System（确定性、可重复）
- [x] Knowledge Improvement Engine（仅 Proposal，经 ApprovalStore）
- [x] Quality Gate 13.0（失败阻断）
- [x] Intelligence API（POST 全部审批门控，GET 全部只读）
- [x] Extension 只读 Dashboard（无 Execute / Approve / Apply / Auto-fix / Auto-learn）
- [x] Security Boundary 测试（50 项）
- [x] Backend ≥200 / Extension ≥100 / Security ≥50 测试
- [x] 文档 `docs/phase-27.md` + README 更新

## Human-in-the-loop 边界（未破坏）

Prediction ≠ Action，Recommendation ≠ Execution；Evaluation 只读系统状态；所有持久化写入走 `Proposal → ApprovalStore → Human Approval → Controlled Write`。系统不会自动学习、自动写 Memory、自动修改 Knowledge 或自动修复。
