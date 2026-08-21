# Phase 17 Completion Report · Engineering Intelligence Graph

Phase 17 已完成，停止于 Phase 17，未进入后续阶段。

## 1. Engineering Graph

新增 `local-bridge/app/engineering_graph/`：

- `models.py`：Project、Workflow、Task、Decision、ExecutionLoop、Agent、Memory、Verification 节点和关系模型
- `storage.py`：SQLite 持久化，节点/边使用幂等 upsert
- `manager.py`：从既有 Loop、Task、Decision、Agent、Memory、Verification 数据重建工程图谱

支持关系：

- `depends_on`
- `created_by`
- `verified_by`
- `failed_by`
- `supersedes`

图谱重建属于元数据写入，必须通过 `ApprovalStore`；图谱查询为只读。

## 2. Failure Intelligence

新增 `local-bridge/app/failure_intelligence/`：

- 执行失败
- Rollback
- Task 失败
- Test/Verification 失败
- High-risk block

分析器只读取现有 Execution Loop、Task、Execution Result 和 Verification 数据，不执行 Action、不修改源码、不写入 Memory。

## 3. Engineering Timeline

新增 `local-bridge/app/memory/evolution/`：

- Decision
- Execution
- Failure
- Learning

`GET /memory/evolution/history` 可读取已批准记录与派生时间线。

`POST /memory/evolution/append` 只生成 Pending Approval；只有用户通过 `/permission/approve` 后才会追加 `evolution.jsonl`。

## 4. Agent Capability Metrics

新增 `app/metrics/capability.py`，提供只读指标：

- Success rate
- Review score
- Average quality
- Rollback rate
- Failure patterns

指标不会修改权限、Risk Level、Approval 状态或 Agent 能力边界。

## 5. Extension Dashboard

新增 `browser-extension/src/engineering-graph/`，展示：

- Engineering Graph nodes/relations
- Failure Patterns
- Engineering Timeline
- Agent Capability Metrics

面板标记为 `READ ONLY`，没有 Execute、Apply、Rollback、Auto Fix 或 Approval 按钮。

## 6. API

新增：

- `POST /engineering-graph/rebuild` — Level 1，生成图谱重建 Approval
- `GET /engineering-graph`
- `GET /engineering-graph/{project}`
- `GET /failure-intelligence/patterns?project=...`
- `GET /memory/evolution/history?project=...`
- `POST /memory/evolution/append` — Level 1，生成 Memory Approval
- `GET /agent/{agent_id}/capability-metrics`
- `GET /engineering/agent-metrics`

既有 Phase 16 Execution Loop API 和唯一执行入口保持兼容。

## 7. Security Review

已验证：

- Proposal → Approval → Execution → Verification → Learning 链路保持不变
- 图谱重建与 Evolution Memory 写入均经过 ApprovalStore
- Failure Intelligence、Graph Query、Timeline Query、Metrics Query 均为只读分析
- 无自动执行、自动批准、Shell、外部模型调用或权限提升
- Failure Intelligence 不修改 Loop、Task、Result 或 Memory
- Extension 没有新增执行入口
- Metrics 不参与权限决策

## 8. Tests

- Phase 17 Engineering Graph focused backend：**188 passed/collected**
- Backend full suite：**1347 tests collected and passed**
- Extension Engineering Graph focused：**81 passed**（目标 ≥80）
- Extension full suite：**641 passed**
- TypeScript：**0 errors**
- MV3 build：通过
- `python -m compileall`：通过
- `git diff --check`：通过

未启动预览服务；当前环境没有 Chrome/Chromium，因此未进行真实浏览器视觉检查。

## 9. Completion Boundary

Phase 17 已完成。未实现自动修复、自动执行、自动批准或任何 Phase 18 能力。
