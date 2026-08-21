# Phase 13 Completion Report

## 1. 新增模块

Phase 13 在 Phase 12 Code Intelligence 之上增加了 `local-bridge/app/intelligence/`：

- `models.py`：Insight、Proposal、Decision、RiskFactors 以及可持久化状态枚举。
- `analyzer.py`：读取 Code Index 的文件、符号和依赖元数据，生成架构、依赖、测试、代码气味、安全和维护性洞察。
- `risk.py`：基于影响范围、修改文件、依赖数、测试覆盖率、回滚可用性和安全敏感度的确定性 0–100 风险评分。
- `recommendation.py`：把洞察转成不可执行的工程 Proposal。
- `decision.py`：ADR-like 工程决策模型与严格状态机。
- `storage.py`：SQLite `intelligence.db`，持久化 insights、proposals、decisions。
- `manager.py`：协调索引读取、分析、建议和决策创建。
- `quality/gate5.py`：Quality Gate 5.0，输出质量、风险、技术债和决策置信度。

新增 `memory/intelligence/project_memory.py`，将已获批的长期工程知识追加到：

- `architecture-insights.md`
- `engineering-decisions.md`
- `risk-history.md`

这些文件位于 `workspace/memory/project/intelligence/<project>/`，并且只通过独立的 ApprovalStore 请求写入。

扩展新增 `browser-extension/src/intelligence/`：

- Engineering Overview
- Risk signals / heatmap-style severity display
- Active proposals
- Pending decisions
- Quality and technical-debt summary

面板保持纯只读，没有执行、应用、批准或重构控件。

## 2. Architecture Changes

数据流现在是：

```text
Phase 12 Code Index / Graph / Impact / Quality
                    ↓
          Engineering Analyzer (read-only)
                    ↓
              Insight records
                    ↓
          Recommendation Engine
                    ↓
             Proposal records
                    ↓
             Human Decision Review
                    ↓
         ApprovalStore (explicit approval)
                    ↓
     Decision metadata + separate Memory Proposal
                    ↓
      Second explicit approval before Memory append
```

分析器只访问已建立的代码索引，不执行项目代码、不调用外部模型 API、不启动 Shell，也不修改源文件。工程建议是记录，不是 Action。

SQLite 表：

- `insights`：项目、类型、严重度、标题、位置、证据和建议。
- `proposals`：洞察引用、目标、预期收益、风险分数和生命周期状态。
- `decisions`：Proposal 引用、选项、推荐项、状态和状态历史。

## 3. Decision Flow

支持的 Decision 状态：

```text
DRAFT → REVIEWING → APPROVED → IMPLEMENTED → ARCHIVED
  └──────────────→ REJECTED → ARCHIVED
```

非法跳转会被拒绝。创建 Decision 的 API 只返回待审批请求；审批之后仅写入决策元数据，不执行代码、不提交 Git、不直接写 Memory。完成 Decision 元数据后，系统创建一个独立的 `intelligence_memory_append` Memory Proposal，用户仍需再次明确审批。

## 4. API List

### Read-only

- `GET /intelligence/insights`
- `GET /intelligence/proposals`
- `GET /intelligence/decisions`
- `GET /intelligence/decision/{decision_id}`
- `GET /quality/v5/{workflow_id}`
- 既有 Phase 12 `/code/*`、`/project/*`、`/impact/analyze`、`/context/query` 和 `/memory/project/history` 保持兼容。

### Approval-gated

- `POST /intelligence/analyze`：生成待审批的分析请求（LEVEL_1）。审批后才把洞察和 Proposal 写入 SQLite。
- `POST /intelligence/decision/create`：生成待审批的决策创建请求（LEVEL_1）。审批后只创建 Decision 元数据，并排队独立 Memory Proposal。
- `POST /permission/approve`：唯一执行入口；仍由既有 ApprovalStore 处理。

所有读取 API 返回 `readOnly: true`（Quality API 也返回 `readOnly: true`），并写入 Audit。

## 5. Security Review

已验证并保持：

- 没有新增 Shell 或命令执行入口。
- Analyzer、Risk、Recommendation、Quality Gate 和 Context 读取均为确定性只读操作。
- Index 数据不会改变 PermissionLevel，也不能批准 Proposal。
- Proposal 不是 Action，不能被 Scheduler 或 Agent 直接执行。
- Analyze 和 Decision Create 通过现有 ApprovalStore 进入队列，不会自动批准。
- 重启恢复的 approval 仍必须 `RECONFIRMED`，不会自动继续。
- Decision Memory 使用第二个、独立的 ApprovalStore 请求；拒绝或未审批时不生成 Memory 文件。
- 不引入外部模型 API，不执行自动重构，不自动提交 Git，不自动更新 Memory。
- 扩展 dashboard 仅展示数据，不提供一键修复、应用建议或审批按钮。
- Phase 1–12 的 Permission、Risk、Rollback 和旧 API 路径未被移除。

## 6. Tests

本次验证：

- Local Bridge 全量：**510 collected / 510 passed**
- Phase 13 后端专项：**120 collected / 120 passed**
- Browser Extension 全量：**226 passed**
- Extension TypeScript：**0 errors**
- MV3 content/background build：**通过**
- Python `compileall`：**通过**
- `git diff --check`：**通过**

Phase 13 后端覆盖 Analyzer、风险边界、每类 Insight、Proposal 持久化与过滤、Decision 状态机、非法迁移、Memory 双重审批、恢复安全、SQLite 重开、API 只读标记、无 Shell/外部模型调用等场景。扩展覆盖 Dashboard 数据展示、严重度、Proposal/Decision 状态、Quality/Technical Debt、GET-only Bridge methods、项目编码和无执行控件保证。

根目录 Next.js TypeScript 检查未执行：当前验证环境没有根项目依赖。Chrome 视觉自动化未执行：当前环境没有 Chrome。未启动服务，也未进入 Phase 14。

## 7. Phase 14 Proposal

Phase 14 可在确认后考虑 **Governed Engineering Change Plans**：把已批准的 Decision 转换为可审阅的分步 Change Plan、逐步风险评估和可回滚批次；每个批次仍必须走 Proposal → Risk → Approval → Execution，且不增加隐式执行路径。

本次实现停留在 Phase 13，等待确认后再规划 Phase 14。
