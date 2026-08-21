# Phase 26 · Engineering Intelligence 2.0 & Predictive Engineering

## 状态

Phase 26 已在 Phase 25 的只读 Intelligence 基础上增量实现。它提供证据驱动的趋势、关联、影响预测、依赖风险、推荐排序、历史评估和证据图；不提供执行器，也不改变工程源码或依赖。

最终链路：

```text
Engineering Events
        ↓
Observation
        ↓
Pattern
        ↓
Trend / Correlation
        ↓
Impact Prediction / Risk Prediction
        ↓
Recommendation Ranking
        ↓
Human Decision
        ↓
Outcome
        ↓
Evaluation
        ↓
Knowledge Proposal → ApprovalStore → Human Approval → Memory
```

## Architecture

新增或扩展的实际文件：

### Backend

- `local-bridge/app/intelligence/confidence.py`
  - `ConfidenceBreakdown` 与 `derive_confidence()`。
  - 由 evidence count、historical similarity、freshness、outcome validation、pattern consistency 计算有界分数；不使用随机值。
- `local-bridge/app/intelligence/trends/`
  - `TrendResult`、`TrendStore`、`EngineeringTrendEngine`。
  - 支持 test/build failure、error、dependency、performance、risk、code change、regression 指标以及 daily/weekly bucket。
- `local-bridge/app/intelligence/correlation/`
  - `CorrelationResult`、`CorrelationStore`、`FailureCorrelationEngine`。
  - 只记录 temporal association；输出明确的 `correlation_only` 和 `causation_claim: false`。
- `local-bridge/app/intelligence/impact_prediction/`
  - `ImpactPrediction`、`ImpactPredictionStore`、`ChangeImpactPredictionEngine`。
  - 根据 changed files/symbols、dependency paths、historical failure observations 给出 affected files/modules/tests、risk、confidence 和 `why_risky`。
- `local-bridge/app/intelligence/dependency/`
  - `DependencyRisk`、`DependencyRiskStore`、`DependencyRiskAnalyzer`。
  - 识别版本变化、breaking/major/removal/vulnerability signal、transitive dependency、concentration、coupling 和历史失败证据。
- `local-bridge/app/intelligence/recommendation.py`
  - 保留 Phase 13/25 recommendation API，并增加 `RankedRecommendation`、`RecommendationRanking`、`RecommendationRanker`。
  - 排序不等于选择，不生成执行请求。
- `local-bridge/app/intelligence/evaluation/`
  - `PredictionEvaluation`、`RecommendationEvaluation`、`EvaluationStore`。
  - `PredictionEvaluator` 只有在存在真实 Outcome 时才计算 accuracy/precision/recall/FP/FN；没有 Outcome 时不伪造 benchmark。
- `local-bridge/app/intelligence/evidence_graph/`
  - `IntelligenceEvidenceGraph`、node/edge models。
  - 支持 `OBSERVED_FROM`、`CORRELATED_WITH`、`SUPPORTS`、`PREDICTS`、`RECOMMENDS`、`DECIDED_BY`、`RESULTED_IN`、`LEARNED_FROM` 等 provenance relations。
- `local-bridge/app/intelligence/phase26.py`
  - 只读项目聚合 facade，组合 Phase 25/26 数据供 API 和 Extension 使用，不执行写入。
- `local-bridge/app/memory/intelligence/knowledge.py`
  - 在原有 `patterns`、`predictions`、`strategies`、`outcomes` 之外增加 `trends`、`correlations`、`recommendations`、`evaluations` 类别。
  - 仍然只能通过 `Knowledge Proposal → ApprovalStore → Human Approval → append_after_approval` 写入。

### Extension

- `browser-extension/src/intelligence/models.ts`
  - 增加 Trend、Correlation、Impact、Dependency、Evaluation、Ranking、Evidence Graph 类型。
- `browser-extension/src/bridge/client.ts`
  - 增加 Phase 26 GET-only client methods。
- `browser-extension/src/content/controller.ts` / `src/state/store.ts`
  - 增加 project-scoped Phase 26 read-only state refresh。
- `browser-extension/src/intelligence/intelligence-dashboard.ts`
  - 增加 Engineering Intelligence 2.0 区域：trend、correlation、impact、dependency、ranking、accuracy、graph summary。
- `browser-extension/src/ui/panel.ts` / `src/ui/styles.css`
  - 接入只读 Phase 26 面板样式。

## Trend Engine

`EngineeringTrendEngine` 首先按 daily/weekly bucket 聚合 Observation。只有至少两个时间 bucket 才能形成 TrendResult，避免根据单次事件声明趋势。每条结果包含：

- `trend_id` / `project_id`
- `metric` / `period`
- `direction`: `increasing`、`decreasing`、`stable`、`volatile`
- `change_rate` / bounded `confidence`
- `evidence` observation IDs
- confidence breakdown 和 explanation

结果可以显式通过 `TrendStore` 写入 SQLite；HTTP GET 默认只读分析，不自动保存。

## Correlation Engine

Correlation engine 只比较同一项目内、时间窗口内的 Observation。例如：

```text
Dependency Change → Test Failure
Test Failure      → Build Failure
Code Change       → Regression signal
```

输出关系是 temporal association，不是 causation。没有证据时不输出因果结论；所有 events/evidence 都保留 observation IDs。

## Impact Prediction

`ChangeImpactPredictionEngine` 接受 changed files、changed symbols、dependency paths 和历史 Observation，输出：

- affected files / modules / tests
- `LOW` / `MEDIUM` / `HIGH` / `CRITICAL`
- confidence 与 confidence sources
- evidence chain
- `why_risky`

它没有 patch、file write、dependency update、lockfile update 或 executor 分支。

## Dependency Intelligence

依赖分析只读取 Dependency Change Observation。它可以标记：

- version change、major/breaking/removal/vulnerability signal
- transitive dependency
- historical failure match
- dependency concentration / coupling

它不会修改 `package.json`、requirements、lockfile，也不会调用供应商漏洞或 LLM API。

## Recommendation Ranking

Ranking 使用显式的 evidence strength、bounded confidence、estimated effort 和 risk reduction 计算 deterministic priority。响应同时提供：

- `ranked`
- `recommendedAction`（仅文本排序结果）
- `alternativeActions`
- reason/evidence/confidence
- `humanDecisionRequired: true`

`recommendedAction` 不是自动选择，更不是执行命令；真实 Strategy/Decision/Execution 仍需要原有人工审批链。

## Prediction Evaluation

`PredictionEvaluator` 只对真实 Outcome 进行回看。支持：

- `accuracy`
- `precision`
- `recall`
- `false_positive_rate`
- `false_negative_rate`

没有历史 Outcome 时数量为零，系统不会生成伪造 benchmark。`RecommendationOutcomeEvaluator` 记录 recommendation、human decision 和 Outcome 的成功关系，但不会自行调整推荐规则。

## Evidence Graph

`IntelligenceEvidenceGraph` 是内存中的只读 graph projection。节点包括 Observation、Pattern、Trend、Correlation、Prediction、Impact Prediction、Recommendation、Decision、Outcome、Evaluation、Knowledge；边保留来源 IDs 和关系类型。

Graph builder：

- 过滤 project，不跨项目连接 evidence
- 脱敏 label/metadata/path
- 去重 edge
- 不写工程 Graph、不执行 Action、不写 Memory

## Confidence Model

Confidence 范围为 `0.0–0.95`，不是确定性概率声明。解释字段说明：

- evidence count
- historical similarity
- data freshness
- outcome validation
- pattern consistency

缺少 evidence 时 confidence 为 `0.0`。所有 Trend、Impact、Dependency、Prediction、Recommendation 和 Evaluation 都保留可追溯 evidence。

## API

Phase 26 新增 GET-only endpoints，全部要求 `project`，并返回 `readOnly: true`：

```text
GET /intelligence/trends?project={project}&metric={metric}&period={daily|weekly}
GET /intelligence/correlations?project={project}
GET /intelligence/impact?project={project}&changed_file=...
GET /intelligence/dependencies?project={project}
GET /intelligence/recommendations?project={project}
GET /intelligence/recommendations/ranking?project={project}
GET /intelligence/evaluations?project={project}
GET /intelligence/evidence?project={project}
GET /intelligence/evidence/graph?project={project}
```

`GET /intelligence/evidence` 保留 Phase 25 evidence bundle，并附带 graph projection。Phase 26 没有 `/execute`、`/apply`、`/auto-fix`、自动批准或自动 provider API。

## Intelligence Memory 2.0

新增知识类别：

- `trends`
- `correlations`
- `recommendations`
- `evaluations`

旧类别保持兼容。HTTP 读取不会写 Memory；所有 proposal 仍经：

```text
Knowledge Proposal
        ↓
ApprovalStore
        ↓
Human Approval
        ↓
append_after_approval
```

## Security Boundary

Phase 26 明确保持：

- no automatic execution
- no automatic approval
- no automatic repair
- no source modification
- no shell executor
- no dependency or lockfile mutation
- no privilege escalation
- no external LLM/provider calls
- no automatic Memory evolution
- no correlation-as-causation claim
- no cross-project evidence links
- secrets、Authorization、API keys、absolute internal paths 均在 Observation 和所有 derived outputs 中脱敏

## Testing

新增 backend tests：

- `tests/test_phase26_trends.py`
- `tests/test_phase26_correlation.py`
- `tests/test_phase26_impact_prediction.py`
- `tests/test_phase26_dependency_risk.py`
- `tests/test_phase26_recommendation.py`
- `tests/test_phase26_evaluation.py`
- `tests/test_phase26_evidence_graph.py`
- `tests/test_phase26_confidence.py`
- `tests/test_phase26_api.py`
- `tests/security/test_phase26_intelligence_security.py`

当前专项收集数量：**314 个 backend tests，118 个 security tests**。覆盖 trend calculation、correlation disclaimer、impact explainability、dependency risk、ranking、historical evaluation、evidence provenance、confidence determinism、API isolation、secret/path security 和 approval boundary。

另外新增 `browser-extension/tests/intelligence-2.test.ts`，覆盖 Phase 26 dashboard、GET client、URL encoding 和无 mutation helper；本次 Extension Vitest 实测 **1152 passed**，TypeScript `tsc --noEmit` 通过，MV3 content/background production build 通过。

验证命令还包括：Python `compileall` 通过，`git diff --check` 通过。后端回归按批次实测通过（基础/Phase 7–13、Phase 14–18、Phase 19–25、Phase 26 与 security 回归均无失败）。

## Limitations

Phase 26 不是生产级预测准确率保证，也不是 Autonomous Agent：

- 预测依赖本地 Observation 与真实 Outcome 的质量和数量
- 没有足够时间 bucket 时不会声明 Trend
- correlation 不代表 causation
- evaluation 不会在缺少真实 Outcome 时填充结果
- Ranking 只提供可解释排序，Human 仍必须决定是否提出 Strategy
- Evidence Graph 是只读 projection，不是新的工程执行图

后续阶段如果要引入更复杂模型，必须先设计独立的模型安全边界、数据治理、可复现 benchmark、审批和回滚方案。
