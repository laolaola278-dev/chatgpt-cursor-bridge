# Phase 12 Completion Report

项目：**ChatGPT Cursor Bridge**  
阶段：**Project Intelligence Layer**  
状态：**已完成；未启动服务，未进入 Phase 13**

Phase 12 在 Phase 11 的 Runtime、Workflow、Multi-Agent Collaboration 和 Approval Governance 之上增加长期项目理解能力。所有分析默认只读；需要写入索引或项目记忆时，仍然进入既有审批队列。

```text
Proposal
  ↓
Risk Evaluation
  ↓
Approval Queue
  ↓
Human Approval
  ↓
Execution
```

本阶段没有新增 Shell 执行能力、外部模型 API、自动批准、自动重构、自动删除历史或权限升级路径。

## 1. Code Intelligence Architecture

新增 `local-bridge/app/code_intelligence/`：

- `scanner.py`：在 Project Sandbox 内枚举受支持的源文件，跳过 `.git`、`node_modules`、虚拟环境、隐藏目录和配置的 ignored names；计算 SHA-256，不修改项目文件。
- `parser.py`：Python 使用 `ast` 解析类、函数和 import；TypeScript/JavaScript、Go、Rust 等使用确定性的声明/import 解析。解析从不 import 或执行项目代码。
- `index.py`：协调扫描、解析和数据库写入；Python module 名称在可能时映射到实际项目相对路径。
- `storage.py`：SQLite `files`、`symbols`、`dependencies` 表与参数化查询。
- `dependency.py`：根据依赖边反向计算受影响模块。
- `analyzer.py`：基于已建立索引生成语言、框架、架构摘要、模块数量和复杂度建议。

索引数据库默认位置：`workspace/code/code_index.db`。Code Index 写入由 `POST /code/index` 生成 Pending Approval；批准前只做预览扫描，不写索引。

## 2. Symbol Index

SQLite 表：

```sql
files(id, project, path, language, hash, updated_at)
symbols(id, file_id, type, name, signature, line_start, line_end)
dependencies(id, project, source, target, type)
```

支持的只读查询：

- `GET /code/search?project=&q=`：按符号名、签名或文件路径搜索。
- `GET /code/symbol/{name}?project=`：查找函数/类定义。
- `GET /project/profile?project=`：读取项目画像。
- `GET /project/graph?project=&q=`：读取已构建的架构图。

所有查询均使用参数化 SQLite 查询并写入 Audit；索引数据不参与 Permission Level 或审批判定。

## 3. Knowledge Graph

新增 `local-bridge/app/knowledge_graph/`，默认存储于 `workspace/knowledge/knowledge_graph.db`。

节点类型：

- `Module`：项目源文件。
- `Service`：无法映射到项目文件的外部依赖。
- 可由后续阶段扩展到 Database、API、Agent、Workflow，但本阶段不产生执行入口。

当前关系：`depends_on`。图构建作为已批准的 Code Index 更新的一部分执行；`GET /project/graph` 只读返回节点、边和 `readOnly: true`。

## 4. Project Profile

`ProjectProfileService` 从索引生成建议性画像：

```json
{
  "projectId": "demo",
  "languages": {"Python": 12, "TypeScript": 8},
  "frameworks": ["FastAPI/Python", "TypeScript/JavaScript"],
  "architectureSummary": "layered",
  "moduleCount": 20,
  "complexityScore": 54,
  "readOnly": true
}
```

画像不是权限来源，也不会触发重构或自动 Memory 更新。需要把画像写入 Project Memory 时，调用方必须单独创建 Memory Proposal 并等待用户批准。

## 5. Context Engine

新增 `app/memory/query_engine.py`，并以只读方式组合：

- Code Symbol Index 搜索结果。
- Project Memory history。
- 可选的 Impact Analysis。
- Agent 角色和当前查询。

`GET /context/query?project=&q=&agent_role=&changed_file=` 支持 Planner、Architect、Coder、Tester、Reviewer 的上下文请求。它不会修改 Memory、Workflow、Task 或 Approval。

角色目标由调用方提供，Context Query 仅返回资料，不代表 Agent 获得工具权限或执行授权。

## 6. Impact Analysis

新增 `app/impact/analyzer.py`：

```json
{
  "project": "demo",
  "changedFiles": ["src/auth.py"],
  "affectedModules": ["src/api.py", "tests/test_auth.py"],
  "risk": "medium",
  "readOnly": true
}
```

分析沿 `dependencies` 反向遍历，防止只报告直接依赖而遗漏传递影响。风险按受影响模块数量分级，用于 Quality Gate 建议；它不写代码、不运行测试、不创建审批以外的执行路径。

API：`GET /impact/analyze?project=&changed_file=`。

## 7. Engineering Memory Upgrade

新增 `app/memory/project.py`，使用：

```text
workspace/memory/project/<project>/
├ architecture/
├ decisions/
├ bugs/
└ changes/
```

- `GET /memory/project/history?project=`：只读时间线。
- `POST /memory/project/propose`：创建 `project_memory_append` Pending Approval。
- 只有 `/permission/approve` 成功后，才会写入 Markdown 记录。
- 内容经过现有控制字符、大小和 Project Name 校验；采用唯一时间戳文件名，避免同秒覆盖。

这条路径不提供 Memory 编辑、删除或直接数据库修改入口。Project Memory 不会因为 Code Index、Context Query 或 Agent 查询而自动更新。

## 8. Quality Gate 4.0

新增 `app/quality/gate4.py`，输出：

- `score`
- `risk`
- `architectureImpact`
- `changeRisk`
- `regressionRisk`
- `historicalStability`
- `affectedModules`
- `blockingIssues`
- `recommendation`

API：`GET /quality/v4/{workflow_id}`。它是只读评估端点；它不会替代既有 Review → Test → Risk → Human Approval 门禁，也不会自动批准 Workflow。

## 9. API 列表

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/code/index` | LEVEL_1 | 扫描并写入索引与图，需审批 |
| `GET` | `/code/search` | LEVEL_0 | 搜索已建立的符号索引 |
| `GET` | `/code/symbol/{name}` | LEVEL_0 | 查找符号定义 |
| `GET` | `/project/profile` | LEVEL_0 | 项目画像 |
| `GET` | `/project/graph` | LEVEL_0 | 架构知识图谱 |
| `GET` | `/impact/analyze` | LEVEL_0 | 变更影响分析 |
| `GET` | `/context/query` | LEVEL_0 | 角色化上下文检索 |
| `POST` | `/memory/project/propose` | LEVEL_1 | 项目记忆 Proposal |
| `GET` | `/memory/project/history` | LEVEL_0 | 项目记忆时间线 |
| `GET` | `/quality/v4/{workflow_id}` | LEVEL_0 | Quality Gate 4.0 |

新增配置项：

- `CODE_INDEX_DB_PATH`，默认 `../workspace/code/code_index.db`。
- `KNOWLEDGE_GRAPH_DB_PATH`，默认 `../workspace/knowledge/knowledge_graph.db`。

没有新增密钥、外部服务或 API Token 要求。

## 10. Extension UI

新增 `browser-extension/src/project-intelligence/`：

- Project Overview：模块数、复杂度、架构摘要、框架。
- Code Map：图节点和关系摘要。
- Impact Analysis：风险与受影响模块。
- Memory Timeline：项目记忆记录。
- `READ ONLY` 标记和空索引提示。

面板、Bridge Client、Controller Store 和刷新流程已接入；所有 Project Intelligence 客户端方法使用 GET。该面板没有 Execute、Approve、Write、Refactor 或 Delete 按钮。

## 11. Security Review

已验证：

1. Scanner 只读取文件字节和 AST，不执行项目代码，不修改源文件。
2. Code Index 数据不参与权限计算；索引写入必须通过 `ApprovalStore`。
3. Context Query、Project Profile、Graph、Impact 和 Quality Gate 是只读路径。
4. Project Memory 仅由审批后的 `project_memory_append` action 写入。
5. 既有 `PermissionLevel`、Risk、Rollback、Scheduler 和 Conflict 安全逻辑未被替换。
6. 没有新增 Shell、subprocess、外部模型或隐藏 Agent action。
7. 恢复审批和既有 Workflow 的人工确认规则继续生效。

## 12. Test Report

本地验证结果：

- Local Bridge 全量：**390 passed**。
- Phase 12 后端专项：**97 collected / passed**。
- Python `compileall`：通过。
- Browser Extension 全量：**136 passed**，10 个测试文件。
- Extension TypeScript：通过，0 errors。
- MV3 build：通过（content + background）。
- `git diff --check`：通过。
- Root Next.js TypeScript：当前环境未安装根项目依赖，未执行。
- Chrome/Chromium 视觉验证：当前环境未安装 Chrome，未执行。

## 13. Phase 13 Recommendation

建议 Phase 13 在用户确认后再开始，方向可以是：

- 增量索引和文件变更事件，而不是每次全量扫描。
- 更精确的跨语言符号解析和调用关系。
- 人工审核后的 Architecture Evolution 时间线。
- 受审批保护的 Context 质量反馈闭环。

本报告不启动 Phase 13。
