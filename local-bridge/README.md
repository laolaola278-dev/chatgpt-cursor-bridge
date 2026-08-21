# Local Bridge Service (Phase 1 + Phase 3 + Phase 5 + Phase 6 + Phase 7 + Phase 8 + Phase 9 + Phase 10)

ChatGPT Cursor Bridge 的本地安全桥接服务。提供沙箱化的 workspace 访问、审批保护的写入能力、Patch 应用、审计日志、Phase 3 的项目级长期记忆系统，以及 Phase 5 的工程工作流编排。

**尚未包含**：通用命令执行、RAG / 向量检索、真实外部模型调用或 Agent 自动循环；Phase 9 仅提供受审批保护的 Agent 元数据与消息运行时。

## 环境要求

- Python 3.11+

## 安装

```bash
cd local-bridge
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

如果本机 `venv` 不带 pip，可使用：

```bash
pip3 install --target .pydeps -r requirements.txt
export PYTHONPATH=".pydeps:."
```

## 配置

所有路径均来自 `.env`，代码中不存在硬编码路径。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BRIDGE_HOST` | `127.0.0.1` | 监听地址，建议保持回环地址 |
| `BRIDGE_PORT` | `8765` | 监听端口 |
| `WORKSPACE_ROOT` | `../workspace/projects` | 沙箱根目录，所有文件操作被限制在其中 |
| `LOG_PATH` | `../workspace/logs` | JSONL 审计日志目录 |
| `MEMORY_ROOT` | `../workspace/memory` | 项目记忆根目录，每项目独立子目录 |
| `WORKFLOW_ROOT` | `../workspace/workflows` | Workflow JSON 持久化目录 |
| `CONTEXT_ROOT` | `../workspace/context` | Project Context 快照与 `context_index.db` 目录 |
| `BACKUP_ROOT` | `../workspace/backups` | Memory / Workflow / Approval 备份与恢复隔离目录 |
| `APPROVAL_DB_PATH` | `../workspace/approvals/approvals.db` | SQLite 持久化审批队列 |
| `APPROVAL_TTL_SECONDS` | `3600` | 审批请求有效期；过期后不可恢复 |
| `SESSION_ROOT` | `../workspace/sessions` | Persistent Agent Session JSON 目录 |
| `AGENT_ROOT` | `../workspace/agents` | Agent 元数据与消息 JSONL 目录 |
| `EVENT_ROOT` | `../workspace/events` | Phase 10 integrity-checked event JSONL |
| `MESSAGE_ROOT` | `../workspace/messages` | Phase 10 runtime agent messages |
| `RUNTIME_ROOT` | `../workspace/runtimes` | Persistent AgentRuntime JSON records |
| `TASK_DB_PATH` | `../workspace/tasks/task.db` | SQLite persistent task queue |
| `CODE_INDEX_DB_PATH` | `../workspace/code/code_index.db` | Phase 12 文件、符号与依赖索引 |
| `KNOWLEDGE_GRAPH_DB_PATH` | `../workspace/knowledge/knowledge_graph.db` | Phase 12 架构知识图谱 |
| `AUDIT_MAX_MB` | `5` | audit.jsonl 轮转阈值 |
| `BACKUP_INTERVAL_SECONDS` | `900` | 定期备份间隔（秒） |
| `MAX_FILE_SIZE_MB` | `5` | 单文件读写上限 |
| `MAX_MEMORY_APPEND_KB` | `64` | 单次 Memory 追加 / ADR 上限 |
| `MAX_TREE_DEPTH` | `6` | 项目树最大递归深度 |
| `MAX_TREE_ENTRIES` | `2000` | 项目树最大节点数 |
| `IGNORED_NAMES` | `node_modules,.git,...` | 扫描时忽略的目录名 |

相对路径以 `local-bridge/` 目录为基准解析。

## 启动

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8765
# 或
python -m app.main
```

交互式文档：`http://127.0.0.1:8765/docs`

## 测试

```bash
pytest
# 或（使用 --target 安装时）
PYTHONPATH=".pydeps:." python3 -m pytest
```

## API

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/health` | LEVEL_0 | 服务健康状态与配置摘要 |
| GET | `/system/health` | LEVEL_0 | memory / database / workspace / workflow / approval 分域健康状态 |
| GET | `/dashboard` | LEVEL_0 | 只读 Local Bridge Web Dashboard |
| GET | `/context/project?project=` | LEVEL_0 | ChatGPT 恢复上下文、Session 状态与快照 |
| GET | `/context/search?q=&project=&from=&to=` | LEVEL_0 | 跨项目 Context Intelligence 只读搜索 |
| POST | `/code/index` | LEVEL_1 | 扫描并更新符号/依赖索引，需审批 |
| GET | `/code/search?project=&q=` | LEVEL_0 | 查询已批准的符号索引 |
| GET | `/code/symbol/{name}?project=` | LEVEL_0 | 查找函数/类定义 |
| GET | `/project/profile?project=` | LEVEL_0 | 读取 Project Profile |
| GET | `/project/graph?project=&q=` | LEVEL_0 | 读取架构知识图谱 |
| GET | `/impact/analyze?project=&changed_file=` | LEVEL_0 | 只读变更影响分析 |
| GET | `/context/query?project=&q=&agent_role=` | LEVEL_0 | 角色化项目上下文检索 |
| POST | `/memory/project/propose` | LEVEL_1 | Project Memory Proposal，需审批 |
| GET | `/memory/project/history?project=` | LEVEL_0 | 读取项目记忆时间线 |
| GET | `/quality/v4/{workflow_id}` | LEVEL_0 | 读取 Quality Gate 4.0 综合评分 |
| GET | `/workspace/list` | LEVEL_0 | 列出 workspace 项目 |
| GET | `/project/tree?project_name=` | LEVEL_0 | 项目文件树（限深度、忽略隐藏目录） |
| GET | `/file/read?project=&path=` | LEVEL_0 | 读取 UTF-8 文本文件 |
| POST | `/file/create` | LEVEL_1 | 创建文件，返回待审批请求 |
| POST | `/file/write` | LEVEL_1 | 覆盖写入，返回待审批请求 |
| POST | `/patch/apply` | LEVEL_1 | 应用 unified diff，返回待审批请求 |
| GET | `/memory/list` | LEVEL_0 | 列出已初始化记忆的项目 |
| GET | `/memory/status?project=` | LEVEL_0 | 读取索引：文档与 ADR 列表 |
| GET | `/memory/read?project=&document=` | LEVEL_0 | 读取单个记忆文档 |
| POST | `/memory/init` | LEVEL_1 | 初始化记忆文档集，需审批 |
| POST | `/memory/append` | LEVEL_1 | 追加记忆（禁止覆盖），需审批 |
| POST | `/memory/decision` | LEVEL_1 | 写入 ADR，需审批 |
| POST | `/workflow/create` | LEVEL_1 | 创建 workflow |
| GET | `/workflow/list` | LEVEL_0 | 列出全部 workflow |
| GET | `/workflow/{id}` | LEVEL_0 | 读取 workflow 详情 |
| POST | `/workflow/{id}/stage/start` | LEVEL_1 | 开始一个 stage |
| POST | `/workflow/{id}/stage/report` | LEVEL_1 | 提交 stage 报告 |
| POST | `/workflow/{id}/stage/attach` | LEVEL_1 | 把 Action 绑定到 stage |
| POST | `/workflow/{id}/stage/approve` | LEVEL_1 | 生成 stage 审批请求 |
| POST | `/workflow/{id}/cancel` | LEVEL_1 | 取消 workflow 并作废挂起 Action |
| GET | `/git/status` | LEVEL_0 | Git 分支、修改、未跟踪、暂存状态 |
| GET | `/git/diff` | LEVEL_0 | 读取 working tree / staged diff |
| POST | `/git/commit` | LEVEL_1 | 预览后审批提交，必须绑定 workflow/stage |
| POST | `/test/run` | LEVEL_1 | 执行白名单测试，必须绑定 TESTING stage |
| POST | `/workflow/{id}/stage/rollback` | LEVEL_1 | 预览并审批 stage 反向恢复 |
| GET | `/permission/pending` | LEVEL_0 | 查看待审批与恢复审批队列 |
| POST | `/permission/reconfirm` | — | 显式重新确认恢复审批，不执行 |
| POST | `/permission/reject` | — | 拒绝指定请求并写入审计 |
| POST | `/permission/approve` | — | 批准并执行指定请求 |
| GET | `/session/list?project=` | LEVEL_0 | 读取持久化 Agent Session |
| GET | `/session/{id}` | LEVEL_0 | 读取 Session 详情与转移历史 |
| GET | `/agent/status?project=&task=` | LEVEL_0 | 读取 Agent 状态、消息摘要与模型选择 |
| GET | `/model-router/capabilities` | LEVEL_0 | 读取模型能力注册表 |
| GET | `/model-router/route?task=` | LEVEL_0 | 确定性任务分类与模型路由 |
| POST | `/agent/create` | LEVEL_1 | 创建 scoped Agent，需审批 |
| POST | `/agent/{id}/transition` | LEVEL_1 | Agent 生命周期转移，需审批 |
| POST | `/agent/message` | LEVEL_1 | 审计 Agent Message，需审批 |
| POST | `/workflow/{id}/stage/agent` | LEVEL_1 | 多 Agent Stage 绑定，需审批 |
| POST | `/workflow/{id}/quality-gate` | LEVEL_1 | Review/Test/Risk 门禁提交，需审批 |
| POST | `/session/create` | LEVEL_1 | 预览后审批创建 Session |
| POST | `/session/{id}/transition` | LEVEL_1 | 预览后审批 Session 状态转移 |
| GET | `/audit/log?limit=` | LEVEL_0 | 读取最近审计日志 |

## Phase 7 Developer Product

- **Workflow Dashboard**：扩展中显示项目、Workflow、Stage Timeline、待审批、测试、Git 与近期变更；所有展示为只读。
- **Context API**：`GET /context/project` 汇总当前 Workflow、Stage、任务、决策、测试结果和 Git 状态，并原子写入 `CONTEXT_ROOT/<project>/current.json`。
- **Context Snapshot**：同时维护 `CONTEXT_ROOT/current.json` 作为最近活动项目快照；Context 不提供任何 Memory 写入口。
- **Production Hardening**：启动恢复检查、审计轮转、启动/定期备份和 `/system/health`。
- **Web Dashboard**：`GET /dashboard` 是不带写操作按钮的本地只读页面，默认每 10 秒刷新。

备份中的 approval 数据只是人工恢复/审计快照，服务启动不会自动恢复或执行审批请求。

## Phase 8 Persistent Agent Runtime

- **Persistent Approval**：审批写入 `APPROVAL_DB_PATH`。启动时校验 TTL，将有效 `PENDING` 标为 `RECOVERED`；恢复请求必须经 `/permission/reconfirm` 后才能进入 `RECONFIRMED`，再由用户单独调用 `/permission/approve` 执行。恢复、重新确认、过期均写入审计日志。
- **Context Intelligence**：Context 读取仍不修改 Memory；派生记录写入 `CONTEXT_ROOT/context_index.db`，包含 documents、decisions、tasks 与 workflow history。`/context/search` 使用参数化查询，支持关键词、项目和日期过滤。
- **Session Runtime**：Session 持久化到 `SESSION_ROOT`，状态为 `CREATE → ACTIVE ↔ PAUSED → COMPLETED`，并可绑定 Workflow、Stage 与 Approval。所有创建和状态转移仍经过 Preview → Approval → Execution。
- **Extension Recovery UI**：面板读取恢复队列，显示 `RECONFIRM REQUIRED`；重新确认后仍显示独立的 `Approve execution`，绝不自动执行。Session 数量和 Context 状态同步刷新。

## Phase 10 Autonomous Development Runtime

Phase 10 adds a persistent runtime coordinator without adding an execution path:

- `app/runtime/` persists lifecycle state and converts interrupted `RUNNING` records to `RECOVERED` on startup; recovery never resumes or approves work.
- `app/event/` writes integrity-checked JSONL events and mirrors each event to `audit.jsonl`.
- `app/task/` stores a validated SQLite task state machine in `TASK_DB_PATH`.
- `app/memory/intelligence/context_builder.py` produces read-only role-specific context bundles.
- `app/quality/` evaluates diff size, test results, risk and memory recording deterministically.
- `GET /runtime/status`, `/runtime/events`, `/agent/runtime`, `/task/list`, `/quality/{workflow_id}` and `/context/bundle` are read-only.
- `POST /runtime/create`, `/task/create` and task transitions create approval requests; they do not mutate until `/permission/approve` is called.

The scheduler only emits an `ExecutionProposal`; `RuntimeScheduler.execute()` and `RuntimeExecutor.execute()` are intentionally blocked. The complete delivery report is [`docs/phase-10.md`](../docs/phase-10.md).

## Phase 9 Multi-Agent Intelligence

- **Model Router**：`app/model_router/` 提供 Architecture、Coding、Debugging、Testing、Review 分类和能力注册表；只做 metadata-only 路由，不调用外部模型。
- **Agent Runtime**：`app/agent/` 持久化 Planner、Architect、Coder、Tester、Reviewer，记录 session、role、memory scope、permissions、model 和生命周期。
- **Agent Message Protocol**：消息保存到 `AGENT_ROOT/messages.jsonl`，所有通信写入 Audit；消息不携带工具权限或 shell 内容。
- **Workflow Quality Gate**：Stage 支持多个 `agentIds` 和 `qualityGate`。绑定 Agent 的 Delivery Stage 必须完成 Review → Test Result → Risk Assessment，再由人单独审批。
- **安全边界**：Agent 创建、transition、消息、Stage 绑定和 Quality Gate 提交都先返回 Pending Approval，不存在自动执行或审批绕过。


### 写入流程

```text
POST /file/write
   ↓ sandbox 校验 + 权限判定
202 Accepted  { allowed:false, requireApproval:true, permissionLevel:"LEVEL_1", requestId, preview }
   ↓ 用户确认
POST /permission/approve { request_id }
   ↓ 执行并写审计日志
200 OK { allowed:true, status:"executed", result:{ file, size, diff } }
```

### 示例

```bash
curl "http://127.0.0.1:8765/health"

curl "http://127.0.0.1:8765/workspace/list"

curl "http://127.0.0.1:8765/project/tree?project_name=demo"

curl "http://127.0.0.1:8765/file/read?project=demo&path=src/main.py"

curl -X POST "http://127.0.0.1:8765/file/write" \
  -H "Content-Type: application/json" \
  -d '{"project":"demo","path":"README.md","content":"# demo\n","reason":"update docs"}'

curl -X POST "http://127.0.0.1:8765/permission/approve" \
  -H "Content-Type: application/json" \
  -d '{"request_id":"req_xxxxxxxxxxxxxxxx"}'
```

## 项目记忆系统（Phase 3）

Memory 保存项目事实，不保存聊天记录。每个项目完全独立：

```text
workspace/memory/<project>/
├ project.md        项目目标、技术栈、约束
├ architecture.md   架构设计、模块关系
├ decisions.md      ADR，追加式
├ tasks.md          当前任务
├ changelog.md      修改历史
└ memory.db         SQLite 索引（仅元数据）
```

文档名为固定白名单，无法创建任意文件。

### 追加语义

`/memory/append` 只追加，永不覆盖。每次追加写入一个带时间戳的分节：

```markdown
---

_Entry: 2026-01-01T00:00:00+00:00_

- [ ] implement memory system
```

### ADR 格式

`/memory/decision` 自动分配递增编号并写入 `decisions.md`：

```markdown
## ADR-001

Title: Use FastAPI for the bridge

Context: We need a typed local HTTP service.

Decision: Adopt FastAPI with Pydantic models.

Consequence: Automatic OpenAPI docs; Python runtime required.

Created: 2026-01-01T00:00:00+00:00
```

`title`、`context`、`decision`、`consequence` 四个字段全部必填。

### SQLite 索引

`memory.db` 只存索引，不存正文：

```sql
CREATE TABLE documents (
    id TEXT PRIMARY KEY,   -- "<project>:<document>"
    project TEXT NOT NULL,
    type TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE decisions (
    id TEXT PRIMARY KEY,   -- "ADR-001"
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

正文始终保留在 Markdown 中，便于人工审阅与 Git 版本化。测试会断言正文内容不出现在 `memory.db` 的字节流中。

### Memory 示例

```bash
# 初始化（需审批）
curl -X POST "http://127.0.0.1:8765/memory/init" \
  -H "Content-Type: application/json" -d '{"project":"demo"}'
curl -X POST "http://127.0.0.1:8765/permission/approve" \
  -H "Content-Type: application/json" -d '{"request_id":"req_xxx"}'

# 读取（无需审批）
curl "http://127.0.0.1:8765/memory/read?project=demo&document=project.md"

# 追加（需审批）
curl -X POST "http://127.0.0.1:8765/memory/append" \
  -H "Content-Type: application/json" \
  -d '{"project":"demo","document":"tasks.md","content":"- [ ] build memory"}'

# 写入 ADR（需审批）
curl -X POST "http://127.0.0.1:8765/memory/decision" \
  -H "Content-Type: application/json" \
  -d '{"project":"demo","title":"Use SQLite","context":"...","decision":"...","consequence":"..."}'
```

## 工程工作流（Phase 5）

Workflow 让 ChatGPT 从单次 Action 执行升级为完整开发流程编排。核心原则是 human-in-the-loop：

- 每个 stage 必须提交结构化报告
- 每个 stage 必须显式审批才能进入下一阶段
- 高风险（LEVEL_2）Action 不会随 stage 批量审批

### 阶段管线

```text
REQUIREMENT → ANALYSIS → ARCHITECTURE → IMPLEMENTATION → TESTING → DEBUG → DELIVERY
```

### 工作流状态机

```text
CREATED ──▶ ANALYZING ──▶ DESIGNING ──▶ WAITING_APPROVAL ──▶ IMPLEMENTING ──▶ TESTING ──▶ COMPLETED
   │           │            │                │                    │             │
   └─────────────────────── CANCELLED / FAILED ────────────────────────────────┘
```

Stage 状态：`PENDING` → `IN_PROGRESS` → `REPORTED` → `WAITING_APPROVAL` → `APPROVED` / `REJECTED`。

### 报告契约

每个 stage 的报告必须包含指定 `##` 小节，否则拒绝：

| Stage | 必填小节 |
| --- | --- |
| REQUIREMENT | Goal、Scope、Constraints |
| ANALYSIS | Findings、Risks、Assumptions |
| ARCHITECTURE | Technology、Modules、Risks、Trade-offs |
| IMPLEMENTATION | Summary、Files Touched、Follow-ups |
| TESTING | Coverage、Results、Gaps |
| DEBUG | Symptom、Root Cause、Fix |
| DELIVERY | Outcome、Artifacts、Next Steps |

### Stage 批量审批

Stage 审批走 `/permission/approve`，动作名 `workflow_stage_approval`：

1. 通过 `/workflow/{id}/stage/attach` 把 Action 请求 ID 绑定到 stage
2. 提交 stage 报告后调用 `/workflow/{id}/stage/approve` 生成一条待审批请求
3. 用户通过 `/permission/approve` 一次批准：所有绑定的 **LEVEL_1** Action 自动执行，**LEVEL_2 Action 仍需单独确认**
4. Stage 拒绝时，绑定的挂起 Action 全部作废

### Memory 集成

`POST /workflow/{id}/stage/approve` 支持 `sync_memory: true`。系统会为每个 stage 推荐 memory 写入，并作为**常规审批请求**排队（不自动执行）：

| Stage | 建议写入 |
| --- | --- |
| REQUIREMENT | project.md、tasks.md |
| ANALYSIS | tasks.md |
| ARCHITECTURE | architecture.md、decisions.md（自动构造 ADR） |
| IMPLEMENTATION | changelog.md、tasks.md |
| TESTING / DEBUG | changelog.md |
| DELIVERY | changelog.md、tasks.md |

所有 memory 写入仍需 LEVEL_1 审批，绕不过既有权限系统。

### Workflow 示例

```bash
# 创建工作流
WF=$(curl -s -X POST http://127.0.0.1:8765/workflow/create \
  -H "Content-Type: application/json" \
  -d '{"project":"demo","name":"Ship memory","description":"end-to-end"}' | jq -r .id)

# 开始 REQUIREMENT
STG=$(curl -s -X POST http://127.0.0.1:8765/workflow/$WF/stage/start \
  -H "Content-Type: application/json" \
  -d '{"stage_type":"REQUIREMENT"}' | jq -r .id)

# 提交报告
curl -X POST http://127.0.0.1:8765/workflow/$WF/stage/report \
  -H "Content-Type: application/json" \
  -d "{\"stage_id\":\"$STG\",\"title\":\"Req\",\"body\":\"## Goal\n\n...\n\n## Scope\n\n...\n\n## Constraints\n\n...\n\"}"

# 请求 stage 审批
AWAIT=$(curl -s -X POST http://127.0.0.1:8765/workflow/$WF/stage/approve \
  -H "Content-Type: application/json" \
  -d "{\"stage_id\":\"$STG\",\"reason\":\"ready\"}" | jq -r .approval.requestId)

# 批准 stage（同一 approval 端点）
curl -X POST http://127.0.0.1:8765/permission/approve \
  -H "Content-Type: application/json" \
  -d "{\"request_id\":\"$AWAIT\"}"
```

## 工程工具链（Phase 6）

### Git

- `/git/status`、`/git/diff` 为 LEVEL_0 只读操作。
- `/git/commit` 为 LEVEL_1，要求 `message`、`workflow_id`、`stage_id`；请求先返回 status + diff 预览，批准后才执行 `git add --all` 与 `git commit --message`。
- Git 全部使用参数数组、`shell=False`，工作目录由项目沙箱解析。

### Test Runner

只允许三个精确命令别名：

| 输入 | 固定 argv |
| --- | --- |
| `pytest` | `["pytest"]` |
| `npm test` | `["npm", "test", "--"]` |
| `cmake build` | `["cmake", "--build", "build"]` |

拒绝 `;`、`&&`、`||`、管道、重定向、命令替换、换行、PATH/PYTHONPATH/NODE_OPTIONS/LD_PRELOAD 修改及任意脚本。执行始终 `shell=False`，默认超时 300 秒，stdout + stderr 总上限 64KB。

`/test/run` 必须绑定真实的 TESTING stage。执行结果会生成包含 Coverage / Results / Gaps 的 Stage Report 草稿，但不会自动批准 stage。

### Stage Rollback

绑定 workflow/stage 的文件、Memory、Git commit 在执行前写入 `ROLLBACK_ROOT/<workflow>/<stage>/` 快照。`/workflow/{id}/stage/rollback` 只生成恢复预览，批准后才按执行时间逆序恢复：

- 已存在文件：恢复原始字节
- 新建文件：删除
- Memory append / ADR：恢复写入前文件
- Git commit：`git reset --mixed <previous-head>`，保留工作树内容

Rollback 本身是 LEVEL_1 Approval Action，完整写入审计日志。

## 安全机制

1. **路径沙箱** (`app/security/sandbox.py`)
   - 拒绝绝对路径、`..` 穿越、空字节
   - `realpath` 解析后必须位于项目目录与 workspace 根目录内
   - 逐级检查祖先目录，拒绝符号链接逃逸
   - 项目名必须匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$`

2. **权限分级** (`app/security/permissions.py`)
   - LEVEL_0 读取类：自动执行
   - LEVEL_1 修改类：必须审批
   - LEVEL_2 删除/危险类：强制审批，Phase 1 未开放任何 LEVEL_2 端点

3. **审批流** — 待审批请求持久化到 SQLite，含操作类型、目标文件、diff 预览、风险等级、TTL 和原因；恢复请求必须重新确认。

4. **审计日志** (`app/audit/logger.py`) — 成功、失败、拒绝、恢复与待审批全部写入 `<LOG_PATH>/audit.jsonl`：

```json
{"timestamp":"2026-01-01T00:00:00.000+00:00","action":"file_write","path":"demo:README.md","permission":"LEVEL_1","approved":true,"result":"success"}
```

5. **载荷限制** — 单文件 5MB、patch 1MB、Memory 追加 64KB、仅 UTF-8 文本、项目树节点数上限。

5b. **Memory 隔离** — `validate_memory_path` 强制文档为扁平白名单文件名，拒绝 `..`、绝对路径、子目录与符号链接逃逸；项目 A 无法解析到项目 B 的 memory 目录。Memory 位于 `MEMORY_ROOT`，与代码项目目录物理分离，`/file/read` 无法访问。

6. **CORS** — 仅允许 ChatGPT 域名与 `chrome-extension://` 来源。

## 已知限制

- 审批请求本体已持久化，但恢复后的请求必须人工重新确认；系统不会自动恢复执行权限。
- 无鉴权 token，依赖仅监听回环地址。
- Patch 仅支持单文件、严格上下文匹配的 unified diff。
- 不支持二进制文件。
- `context_index.db` 是派生搜索索引，损坏时可重建；Memory Markdown 仍是事实来源。
- 未实现任意 Shell 执行；测试命令继续受 Phase 6 白名单与审批约束。
- Memory 为追加式，暂不支持编辑或删除已写入的条目。
- Context Intelligence 当前使用确定性的压缩与参数化关键词匹配，未实现向量检索。
- Memory 不会自动写入，全部需要显式审批。
