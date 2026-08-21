# Phase 7 Completion Report

项目：**ChatGPT Cursor Bridge**

Phase 7 将现有 Engineering Backend 提升为 Developer Product，重点覆盖 UI、Context、Observability 与 Reliability。Phase 8 不在本阶段实施。

## 1. UI 模块

### Browser Extension

- 新增 `src/workflow/`：Stage Timeline，按 REQUIREMENT → DELIVERY 展示状态、完成标记、当前阶段与 action 数量。
- 新增 `src/dashboard/`：Workflow Dashboard，展示当前项目、workflow、当前 stage、待审批数量、测试结果、Git 状态、Open Tasks 与 Recent Changes。
- 新增 `src/context/`：Project Context API 类型契约。
- Stage Report 使用原生折叠详情查看；Approval 状态与 action 数量只读展示。
- 每 10 秒刷新一次只读 Context；刷新不创建新的执行入口，不绕过审批系统。

## 2. Context 系统

- 新增 `GET /context/project?project=<name>`。
- 返回 current workflow/stage、recent decisions、open tasks、last test result、Git status、pending approvals 与 recent changes。
- 在 `CONTEXT_ROOT/<project>/current.json` 保存项目快照，同时维护 `CONTEXT_ROOT/current.json` 作为最近活动项目快照。
- 快照字段包括 `lastWorkflow`、`lastStage`、`activeTasks`、`recentDecisions`、`recentErrors`。
- Context 仅读取 Memory；快照写入 Context 目录，不允许通过 Context 修改 Memory。

## 3. Dashboard

- 新增 Local Bridge `GET /dashboard`。
- Dashboard 只读展示 Projects、Workflows、Approvals、Memory、Audit Stream 与 System Health。
- 前端只发起 GET 请求，10 秒自动刷新；所有修改仍走既有 Preview → Approval → Execution 流程。

## 4. Production Hardening

- 新增 `GET /system/health`，分别检查 memory、database、workspace、workflow、approval。
- `audit.jsonl` 超过 `AUDIT_MAX_MB` 后自动归档到 `LOG_PATH/archive/`。
- 启动时检查损坏的 workflow/context JSON 与 audit JSONL；损坏文件会被隔离到 `BACKUP_ROOT/recovery/`，有效数据保留。
- 启动时创建备份；后续请求按 `BACKUP_INTERVAL_SECONDS` 触发定期备份。
- 备份内容包括 memory、workflow JSON 与 approval inspection snapshot，且 approval 备份明确不可自动执行。
- Rollback snapshot 增加单调捕获序号，保证多次修改同一文件时按真实执行逆序恢复。

新增配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CONTEXT_ROOT` | `../workspace/context` | Context Snapshot 根目录 |
| `BACKUP_ROOT` | `../workspace/backups` | Backup / Recovery 根目录 |
| `AUDIT_MAX_MB` | `5` | audit.jsonl 轮转阈值 |
| `BACKUP_INTERVAL_SECONDS` | `900` | 定期备份间隔 |

## 5. 测试结果

- Local Bridge：`pytest -q` → **161 passed**。
- Browser Extension：`npm run typecheck` → **0 errors**。
- Browser Extension：`npm test -- --run` → **88 passed**。
- Browser Extension：`npm run build` → **通过**，生成 content/background MV3 bundles。
- Root Next.js：`npm run typecheck` → **通过**。
- 新增测试覆盖：Context API / snapshot、System Health、只读 Dashboard、Audit rotation、Workflow Dashboard、Stage Timeline。

## 6. Phase 8 建议（仅建议，不实施）

1. 为 Local Bridge 增加可选的持久化审批队列与恢复后的人工 re-validation，不自动恢复执行权限。
2. 增加跨项目搜索与可配置的 Context 压缩策略，保持 Memory 正文与索引隔离。
3. 增加 Dashboard 的本地鉴权/一次性会话保护和更细粒度的可观测指标导出。

> Phase 8 未开始，等待确认。
