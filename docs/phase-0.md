# Phase 0：项目初始化

## 1. 完整项目目录结构

```text
chatgpt-cursor-bridge/
├ browser-extension/
│  ├ manifest.json
│  ├ src/
│  │  ├ content-script.ts
│  │  ├ background.ts
│  │  ├ injected-ui.ts
│  │  ├ action-parser.ts
│  │  ├ bridge-client.ts
│  │  └ approval-panel.ts
│  ├ assets/
│  ├ tests/
│  └ README.md
├ local-bridge/
│  ├ app/
│  │  ├ main.py
│  │  ├ api/
│  │  │  ├ health.py
│  │  │  ├ workspace.py
│  │  │  ├ project.py
│  │  │  ├ files.py
│  │  │  ├ patches.py
│  │  │  ├ permissions.py
│  │  │  └ memory.py
│  │  ├ core/
│  │  │  ├ config.py
│  │  │  ├ security.py
│  │  │  ├ path_guard.py
│  │  │  ├ command_policy.py
│  │  │  └ audit_log.py
│  │  ├ services/
│  │  │  ├ workspace_service.py
│  │  │  ├ project_service.py
│  │  │  ├ file_service.py
│  │  │  ├ patch_service.py
│  │  │  ├ git_service.py
│  │  │  └ memory_service.py
│  │  ├ models/
│  │  │  ├ requests.py
│  │  │  ├ responses.py
│  │  │  └ permissions.py
│  │  └ utils/
│  ├ tests/
│  ├ pyproject.toml
│  ├ .env.example
│  └ README.md
├ workspace/
│  ├ projects/
│  ├ memory/
│  │  ├ project.md
│  │  ├ architecture.md
│  │  ├ decisions.md
│  │  ├ tasks.md
│  │  ├ changelog.md
│  │  └ memory.db
│  ├ permissions/
│  │  ├ policy.json
│  │  └ approvals.jsonl
│  └ logs/
│     └ audit.jsonl
├ docs/
│  ├ phase-0.md
│  ├ api-contract.md
│  ├ security-model.md
│  └ extension-protocol.md
├ scripts/
│  ├ dev-local-bridge.sh
│  └ package-extension.sh
└ README.md
```

### 目录职责

| 目录 | 职责 |
| --- | --- |
| `browser-extension/` | Chrome / Edge 插件，负责 ChatGPT 页面注入、指令捕获、审批交互、本地服务调用。 |
| `local-bridge/` | Python FastAPI 本地服务，负责 API、安全、文件、Patch、Git、Memory、日志和权限。 |
| `workspace/projects/` | 用户本地项目根目录。所有文件操作必须限制在此目录或用户显式配置的项目目录内。 |
| `workspace/memory/` | 结构化长期记忆，Phase 1 以 Markdown 为主，后续补 SQLite 索引。 |
| `workspace/permissions/` | 权限策略、审批记录、临时授权状态。 |
| `workspace/logs/` | 审计日志，采用 JSONL，便于追加写入和后续分析。 |
| `docs/` | API、协议、安全模型和阶段报告。 |
| `scripts/` | 本地开发、测试、打包辅助脚本。 |

## 2. 技术选型说明

### Browser Extension Layer

- **Manifest V3**：符合 Chrome / Edge 当前扩展规范。
- **TypeScript**：降低内容脚本、消息通信、Action 解析中的类型错误。
- **Content Script + Shadow DOM**：向 ChatGPT 页面注入按钮和审批面板，同时减少样式污染。
- **MutationObserver**：监听 ChatGPT 输出区域，发现 `<action>...</action>` 指令。
- **chrome.runtime messaging**：Content Script 与 Background Service Worker 通信。
- **fetch localhost**：调用 `http://127.0.0.1:<port>` 上的 Local Bridge。

### Local Bridge Service

- **Python 3.11+**：生态成熟，适合文件、Git、测试命令和跨平台脚本编排。
- **FastAPI**：类型友好、文档自动生成、易测试。
- **Pydantic**：请求/响应模型校验。
- **Uvicorn**：本地 ASGI 服务。
- **pytest**：API 与服务层测试。
- **GitPython 或 subprocess git**：Phase 6 决定，MVP 可先用受控 subprocess。
- **SQLite**：Memory 元数据与审批记录的轻量持久化；Phase 1 可先落 Markdown 与 JSONL。

### Workspace Layer

- **Markdown 结构化记忆**：优先可读、可审查、可版本化。
- **JSONL 审计日志**：追加写入简单，便于按行读取、流式查看和导入分析系统。
- **路径沙箱**：所有文件路径必须 canonicalize 后校验，避免 `../` 越界和符号链接逃逸。

## 3. 开发路线图

### Phase 0：项目初始化

- 明确目录结构、技术选型、风险和 Phase 1 计划。
- 不实现功能代码。
- 产出阶段报告。

### Phase 1：基础桥接 Local Bridge MVP

- 初始化 `local-bridge/` FastAPI 项目。
- 实现基础 API：健康检查、workspace 列表、项目树、文件读写、文件创建/删除、Patch 应用。
- 建立日志系统。
- 建立初版权限判定模型。
- 添加单元测试和 README。

### Phase 2：浏览器插件 MVP

- 创建 Manifest V3 插件。
- 识别 ChatGPT 页面并注入 UI。
- 解析 `<action>` JSON 指令。
- 展示审批信息。
- 将已批准请求发送到 Local Bridge。

### Phase 3：项目记忆系统

- 创建 Memory 文件模板。
- 支持读写 `project.md`、`architecture.md`、`decisions.md`、`tasks.md`、`changelog.md`。
- 增加 SQLite `memory.db`，保存索引、时间戳、来源和关联任务。
- 暂不引入向量数据库或复杂 RAG。

### Phase 4：权限审批系统

- 实现 Level 0/1/2 权限模型。
- 增加审批 API 和审批记录。
- 插件端展示风险等级、目标文件、内容摘要和原因。
- 默认拒绝危险命令和沙箱外路径。

### Phase 5：Agent 工作流支持

- 定义阶段状态机：需求、分析、架构、审批、编码、测试、修复、报告。
- 每阶段写入 Memory。
- 支持任务恢复和阶段报告生成。

### Phase 6：工程化增强

- Git diff 查看、commit 建议。
- 测试命令自动识别：`npm test`、`pytest`、`cmake build` 等。
- 命令白名单和危险命令识别。
- 更完善的日志检索、错误诊断和安全策略。

## 4. 风险分析

| 风险 | 等级 | 说明 | 缓解策略 |
| --- | --- | --- | --- |
| 本地文件误改/误删 | 高 | GPT 输出可能包含错误路径或破坏性修改。 | 沙箱路径校验、权限分级、Patch 预览、删除强制确认、审计日志。 |
| 命令执行安全 | 高 | 任意命令可导致数据泄露或系统破坏。 | Phase 1 不开放命令执行；Phase 6 引入白名单、超时、环境隔离和危险命令拦截。 |
| ChatGPT 页面 DOM 变化 | 中 | 网页结构变化会影响插件监听。 | 使用稳健选择器、MutationObserver 降级策略、手动粘贴 Action 面板。 |
| CORS 与本地服务连接 | 中 | 插件访问 localhost 需权限配置。 | manifest 中明确 host permissions；Bridge 配置受限 CORS origin。 |
| Action 指令注入 | 高 | 页面中恶意文本可能伪造成 `<action>`。 | 插件端只处理模型最新输出区域；Bridge 端仍要求权限审批和 schema 校验。 |
| 路径穿越与符号链接逃逸 | 高 | `../` 或 symlink 可能访问 workspace 外文件。 | 使用真实路径解析、根目录包含校验、拒绝沙箱外路径。 |
| 长期记忆污染 | 中 | 错误内容进入 Memory 后影响后续决策。 | Memory 写入需要来源、时间、任务 ID；关键决策进入 ADR；允许用户回滚。 |
| 跨平台兼容 | 中 | Windows/macOS/Linux 路径、权限和命令差异。 | pathlib、平台适配测试、命令抽象层。 |
| 日志包含敏感信息 | 中 | 文件内容、路径或错误堆栈可能泄露隐私。 | 日志分级、内容摘要、可配置脱敏、用户可清理。 |
| 功能膨胀 | 中 | 过早加入 Agent 框架、RAG 或云服务导致复杂度上升。 | 严格 Phase MVP，先完成本地安全闭环。 |

## 5. 第一阶段实现计划

### Phase 1 目标

实现一个可运行、可测试、默认安全的 Local Bridge MVP，让浏览器插件或 curl 能通过本地 API 完成基础项目文件操作。

### Phase 1 API 范围

| 方法 | 路径 | 权限等级 | 说明 |
| --- | --- | --- | --- |
| GET | `/health` | Level 0 | 服务健康检查。 |
| GET | `/workspace/list` | Level 0 | 列出 workspace 下项目。 |
| GET | `/project/tree` | Level 0 | 获取项目文件树。 |
| GET | `/file/read` | Level 0 | 读取沙箱内文件。 |
| POST | `/file/write` | Level 1 | 覆盖写入文件，需要确认。 |
| POST | `/file/create` | Level 1 | 创建文件，需要确认。 |
| POST | `/file/delete` | Level 2 | 删除文件，强制确认。 |
| POST | `/patch/apply` | Level 1 | 应用 unified diff 或受控 patch，需要确认。 |

### Phase 1 模块拆分

1. **配置模块**
   - 读取 workspace 根路径、服务端口、允许来源、日志路径。
   - 提供 `.env.example`。

2. **路径安全模块**
   - 标准化路径。
   - 校验目标路径是否在 workspace 内。
   - 拒绝绝对路径、路径穿越和符号链接逃逸。

3. **审计日志模块**
   - 写入 `workspace/logs/audit.jsonl`。
   - 每条记录包含：timestamp、action、file、user_confirm、result、reason、request_id。

4. **权限模块**
   - 实现 Level 0/1/2 分类。
   - Phase 1 可先通过请求字段 `approved: true` 表示用户已确认，后续由插件审批面板驱动。

5. **文件服务模块**
   - 项目树扫描。
   - 读文件。
   - 创建、写入、删除文件。
   - Patch 应用。

6. **测试模块**
   - 使用临时 workspace。
   - 覆盖路径沙箱、读写、删除、日志写入、审批拒绝场景。

### Phase 1 验收标准

- `uvicorn app.main:app --reload` 可启动。
- `/health` 返回正常。
- 所有 API 有 Pydantic schema 和错误处理。
- 所有操作产生审计日志。
- 沙箱外路径访问被拒绝。
- 未批准的 Level 1/2 操作被拒绝。
- pytest 通过。
- README 包含安装、启动、测试、API 示例。

### Phase 1 输出报告模板

完成 Phase 1 后输出：

- 完成报告
- 文件列表
- 架构变化
- API 列表
- 安全策略
- 测试结果
- 已知限制
- 下一阶段计划
