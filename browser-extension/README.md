# ChatGPT Cursor Bridge — Browser Extension (Phase 2 + Phase 7 Dashboard + Phase 8–10 Runtime)

Chrome / Edge Manifest V3 扩展。负责连接 ChatGPT 网页端、注入 Shadow DOM UI、捕获 CCB Action 指令、与 Local Bridge 通信并展示审批流程。

**本阶段不包含**：自动执行、任何绕过用户审批的路径；Phase 9 的 Agent 状态和模型路由仅以只读方式展示。

## 环境要求

- Node.js 18+
- 已运行的 Local Bridge（Phase 1），默认 `http://127.0.0.1:8765`

## 安装与构建

```bash
cd browser-extension
npm install
npm run build      # 产出 dist/
npm test           # vitest
npm run typecheck
```

构建产物：

```text
dist/
├ manifest.json
├ content/content.js              自包含 IIFE
└ background/service-worker.js    自包含 IIFE
```

> MV3 内容脚本不支持 ESM `import`，因此两个入口分别打包为自包含 IIFE，不产生共享 chunk。

## 加载到浏览器

1. 打开 `chrome://extensions`（Edge 为 `edge://extensions`）
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `browser-extension/dist` 目录
5. 打开 `https://chatgpt.com`，右侧出现浮动面板
6. 点击 **Connect** 连接 Local Bridge

## 目录结构

```text
browser-extension/
├ src/
│  ├ background/service-worker.ts   MV3 后台，最小化，只做存储初始化与 ping
│  ├ content/
│  │   ├ content.ts                 内容脚本入口
│  │   ├ controller.ts              审批闭环编排
│  │   ├ dom-observer.ts            MutationObserver + 防抖 + 去重
│  │   ├ action-parser.ts           CCB 协议严格 Schema 校验
│  │   └ selectors.ts               DOM Selector Adapter│  ├ ui/
│  │  ├ shadow-root.ts             Shadow DOM 挂载
│  │  ├ panel.ts                   右侧浮动面板
│  │  ├ approval-card.ts           审批卡片
│  │  └ styles.css                 隔离样式
│  ├ dashboard/
│  │  └ workflow-dashboard.ts      Project Context / 状态 Dashboard
│  ├ workflow/
│  │  └ timeline.ts                Stage Timeline 与报告详情
│  ├ context/
│  │  └ types.ts                   Project Context API 类型
│  ├ bridge/
│  │   ├ client.ts                  Local Bridge HTTP 客户端
│  │   └ types.ts                   Bridge 契约类型
│  ├ models/action.ts               CCBAction 模型
│  ├ state/store.ts                 chrome.storage.local 状态与扩展日志
│  └ env.d.ts
├ tests/                            vitest + jsdom
├ manifest.json
├ vite.config.ts
├ vitest.config.ts
├ tsconfig.json
├ package.json
└ README.md
```

## Manifest 权限

| 项 | 值 | 理由 |
|---|---|---|
| `permissions` | `storage`、`scripting` | 仅用于持久化扩展状态与注入所需能力 |
| `host_permissions` | `https://chatgpt.com/*`、`https://chat.openai.com/*`、`http://127.0.0.1:8765/*` | 仅 ChatGPT 页面与本机 Bridge |
| `content_scripts.matches` | 同上两个 ChatGPT 域名 | 不注入其他站点 |
| CSP | `script-src 'self'; object-src 'self'` | 禁止远程脚本 |

未申请：`tabs`、`webRequest`、`cookies`、`<all_urls>`、`*://*/*`。

## CCB Action 协议

只有 `<ccb_action>` 标签内、通过完整 Schema 校验的 JSON 才会被采纳：

```text
<ccb_action>
{
  "version": "1.0",
  "action": "file.patch",
  "target": { "project": "demo", "path": "src/main.cpp" },
  "reason": "fix memory leak",
  "risk": "medium",
  "payload": { "patch": "@@ -1,2 +1,3 @@\n a\n+b\n c\n" }
}
</ccb_action>
```

支持的 `action`：`file.read`、`file.create`、`file.write`、`file.patch`、`memory.read`、`memory.append`、`memory.decision`、`git.status`、`git.diff`、`test.run`、`workflow.status`。
`risk`：`low` / `medium` / `high`。

Memory 动作以 `target.document` 寻址（白名单：`project.md`、`architecture.md`、`decisions.md`、`tasks.md`、`changelog.md`），不接受自由路径：

```text
<ccb_action>
{
  "version": "1.0",
  "action": "memory.append",
  "target": { "project": "demo", "document": "tasks.md" },
  "reason": "record current task",
  "risk": "medium",
  "payload": { "content": "- [ ] implement memory system" }
}
</ccb_action>
```

`memory.decision` 需要 `payload.title`、`context`、`decision`、`consequence` 四个字段。

校验规则：

- `version` 必须为 `1.0`
- `action` 必须在白名单内，未知类型直接忽略
- `target.project` 必须匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`
- `target.path` 拒绝 `..`、绝对路径、盘符、空字节
- `reason` 必填且 ≤ 500 字符
- `file.patch` 必须含 `@@` hunk；`file.create` / `file.write` 必须含 `payload.content`
- 模型给出的 `requiresApproval:false` 会被忽略，扩展始终强制为 `true`
- 普通聊天文本、`<action>` 等其他标签一律不解析

## Bridge 通信

`src/bridge/client.ts` 调用 Phase 1 API：

| 方法 | 端点 |
|---|---|
| GET | `/health` |
| GET | `/workspace/list` |
| GET | `/file/read` |
| POST | `/file/create` |
| POST | `/file/write` |
| POST | `/patch/apply` |
| GET | `/memory/read` |
| GET | `/memory/status` |
| GET | `/context/project` |
| GET | `/system/health` |
| GET | `/agent/status` |
| GET | `/model-router/route` |
| GET | `/permission/pending` |
| POST | `/memory/append` |
| POST | `/memory/decision` |
| POST | `/permission/reconfirm` |
| POST | `/permission/reject` |
| POST | `/permission/approve` |

连接失败（拒绝连接 / 超时）统一抛出 `BridgeUnavailableError`，面板显示：

```text
Local Bridge unavailable. Start it with: uvicorn app.main:app --port 8765
```

## 审批流程

```text
GPT 输出 <ccb_action>
   ↓ MutationObserver 捕获
   ↓ 严格 Schema 校验（失败即丢弃）
加入 Pending 队列（不发送 Bridge）
   ↓ 用户点击 Approve
POST /file/write | /file/create | /patch/apply  → 202 + requestId + diff 预览
   ↓ 用户已确认，立即
POST /permission/approve { request_id }         → 200 执行
   ↓
面板显示执行状态与结果
```

点击 **Reject** 只记录拒绝决定，不发起任何 Bridge 执行调用。

## Phase 7 Workflow Dashboard

连接成功后，扩展会读取 `/context/project` 并在浮动面板中显示：

- 当前项目、Workflow 状态、Current Stage、Pending Approval
- Test Result、Git Status、Recent Changes、Open Tasks
- REQUIREMENT → DELIVERY Stage Timeline
- 每个 Stage 的 Approval 状态、Action 数量和可折叠 Stage Report

Dashboard 每 10 秒刷新一次，只读，不调用任何执行或批准接口。它只复用既有审批卡片处理用户明确批准的 Action。

## Phase 8 Persistent Agent Runtime

- 连接成功后读取 `/permission/pending`，恢复状态为 `recovered` / `reconfirmed` 的请求会显示 `RECONFIRM REQUIRED`。
- 点击 **Reconfirm approval** 只调用 `/permission/reconfirm`，不会执行；之后仍需单独点击 **Approve execution**。
- `/context/project` 和 `/session/list` 只读刷新，Dashboard 显示 Agent Session 状态、Context 摘要与 Workflow 状态。
- Context 搜索通过 `GET /context/search`，Reject 生命周期通过 `/permission/reject` 记录到 Bridge 审计。

## Phase 10 Autonomous Runtime UI

- `src/runtime/` adds a read-only Runtime Dashboard for lifecycle state, active tasks, recent event records and Quality Gate 2.0 scores.
- The dashboard reads `/runtime/status`, `/runtime/events`, `/task/list` and `/quality/{workflow_id}` during the existing context refresh cycle.
- Recovered runtimes are highlighted as requiring attention; no runtime dashboard control can create tasks, approve proposals or execute actions.
- The existing approval cards remain the only user action surface, and every mutation still follows Preview → Risk Evaluation → Approval Queue → Human Approval → Execution.

## Phase 9 Multi-Agent Runtime UI

- Dashboard 读取 `/agent/status`，展示 Agent role、lifecycle status、bound model 和 selected model route。
- Router 结果显示 capability-aware 的模型选择；扩展不会调用模型，也不会替 Agent 创建、发送消息、执行工具或批准操作。
- Agent / Workflow Quality Gate 的所有写入仍由 Local Bridge 的 Preview → Approval → Execution 流程处理。

## 状态管理

`chrome.storage.local` 键 `ccb_state_v1`：

- `bridgeStatus`：`unknown` / `connected` / `offline` / `error`
- `bridgeOrigin`
- `currentProject`
- `pendingActions`
- `lastResult`
- `projectContext`：最近一次只读 Context API 响应
- `recoveredApprovals`：需要重新确认的 Bridge 审批
- `sessions`：当前项目的持久化 Session 状态
- `agents`：当前项目的只读 Agent 状态、角色和模型
- `modelSelection`：当前任务的只读 Model Router 选择
- `runtimes`：只读 AgentRuntime 生命周期记录
- `tasks`：只读 SQLite Task Queue 快照
- `runtimeEvents`：只读、带 checksum 的 Runtime Event 快照
- `qualityReport`：只读 Quality Gate 2.0 报告
- `lastContextRefresh`
- `log`：扩展侧操作日志（最多 200 条）

## 已知限制

- Bridge 地址目前通过状态中的 `bridgeOrigin` 配置，尚无独立设置页。
- 无 options / popup 页面，全部交互在注入面板中完成。
- 普通 Pending Action 的 Reject 仍只记录在扩展侧；恢复审批可通过 Bridge `/permission/reject` 记录生命周期。
- ChatGPT 大改版时需更新 `selectors.ts`。
