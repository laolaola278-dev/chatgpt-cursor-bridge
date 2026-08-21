# Phase 8 Completion Report

项目：**ChatGPT Cursor Bridge**  
版本：**0.8.0**

Phase 8 将系统从 Developer Product 升级为可重启的 Persistent Agent Runtime。所有有副作用的操作仍保持：

```text
Preview → Approval → Execution
```

服务不会自动批准、自动执行恢复请求，也没有新增通用 Shell 或 UI 直写数据库的入口。

## 1. Persistent Approval

- `ApprovalStore` 改为 SQLite 持久化，默认路径为 `APPROVAL_DB_PATH`。
- 审批记录包含 payload、预览、TTL、Workflow/Stage/Session 绑定和执行结果，因此可跨进程重启及系统重启保留。
- 生命周期包含 `PENDING`、`EXPIRED`、`RECOVERED`、`RECONFIRMED`、`APPROVED`、`REJECTED`，并兼容既有 `EXECUTED` / `FAILED` 终态。
- 启动时先校验过期时间，再把仍有效的 `PENDING` 请求标记为 `RECOVERED`；恢复只恢复队列可见性，不恢复执行权限。
- `RECOVERED` 必须先由用户调用 `POST /permission/reconfirm`，然后用户还要单独调用 `POST /permission/approve` 才会执行。
- 新增 `POST /permission/reject`，拒绝结果与 Workflow Stage 拒绝均会持久化并写入审计。
- `approval_recovered`、`approval_reconfirmed`、`approval_expired` 和 `approval_rejected` 审计事件保留 request id 与项目路径。

关键配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APPROVAL_DB_PATH` | `../workspace/approvals/approvals.db` | SQLite 审批队列 |
| `APPROVAL_TTL_SECONDS` | `3600` | 审批有效期 |

## 2. Context Intelligence

- 新增 `app/context/intelligence/`，提供确定性的 Context 压缩、相关内容选择和项目摘要生成。
- Context 继续仅读取 Memory、Workflow、Git、Audit 与 Session；不会提供直接修改 Memory 的 API。
- 派生索引保存到 `CONTEXT_ROOT/context_index.db`，按项目记录 documents、decisions、tasks 和 workflow history。
- 新增只读接口：

```text
GET /context/search?q=<keyword>&project=<name>&from=<iso-date>&to=<iso-date>
```

- 搜索使用参数化 SQLite 查询，支持关键词、项目过滤、日期范围和结果上限；不接受 SQL 片段或写操作。
- `GET /context/project` 继续原子写入 `<project>/current.json` 与根 `current.json`，并刷新派生索引。

## 3. Session Runtime

- 新增 `app/session/`，将 Agent Session 持久化到 `SESSION_ROOT/<session-id>.json`。
- 生命周期为：

```text
CREATE → ACTIVE ↔ PAUSED → COMPLETED
```

- Session 可绑定 Project、Workflow、Stage 和 Approval；绑定不匹配会被拒绝。
- 创建和状态转移都先生成 Preview，再通过审批执行；Session 本身不执行命令。
- 所有创建与状态转移写入 Audit，Session history 保留每次状态变化的时间和前后状态。
- `/session/list`、`/session/{id}` 为只读读取接口。

## 4. Extension / Dashboard

- 扩展恢复审批卡显示 `RECONFIRM REQUIRED`。
- Reconfirm 后仍必须点击独立的 `Approve execution`，不会因为刷新、重连或恢复自动执行。
- Workflow Dashboard 增加 Context 刷新、Session 状态、Workflow/Stage Timeline、Approval 状态、Action 数量、Stage Report、测试结果、Git 状态、Open Tasks 与 Recent Changes。
- Context 与恢复审批每 10 秒只读刷新；刷新只调用 GET，不新增执行入口。
- `BridgeClient` 暴露 `/context/search`、`/session/list`、`/permission/reconfirm` 和 `/permission/reject` 协议。

## 5. Security Verification

- 没有自动批准或自动执行恢复审批的启动路径。
- `/context/project`、`/context/search`、Session 查询与 Dashboard 均为只读查询。
- Context Index 是派生索引，不能替代或直接修改 Memory Markdown。
- 不开放通用 Shell；命令策略继续拒绝 Shell 展开、重定向、环境注入和任意脚本。
- Workflow、Stage、Approval、Session 的关系在创建、绑定和执行前验证项目及标识符。
- 所有恢复、重新确认、拒绝、Session 转移和执行结果写入审计。

## 6. 测试结果

- Local Bridge：`pytest -q` → **168 passed**（含 Phase 8 Recovery、Context Search、Session 生命周期和重启模拟测试）。
- Python：`python3 -m compileall -q local-bridge/app` → **通过**。
- Browser Extension：`npm run typecheck` → **通过**。
- Browser Extension：`npm test -- --run` → **89 passed**。
- Browser Extension：`npm run build` → **通过**，生成 content/background MV3 bundles。
- Root Next.js：当前环境未完成可用的根目录 TypeScript 依赖验证；未启动 Next.js 服务。
- Chrome/Chromium 不在当前环境，因此未执行真实浏览器视觉交互验证。

## 7. Phase 9 Recommendation

仅提出建议，不实施：

1. 增加跨设备/跨用户的审批身份与短期会话鉴权，保持恢复审批的人工确认语义。
2. 将 Context Index 的确定性关键词搜索升级为可解释的增量全文检索，并增加索引重建命令。
3. 增加 Session 事件流与指标导出，支持长时间 Agent Runtime 的诊断和容量规划。

> Phase 9 未开始，等待确认。
