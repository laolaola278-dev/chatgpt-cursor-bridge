# Phase 29 · Advanced Developer Context & Read-only Code Intelligence

## 状态

Phase 29 在 Phase 28 的 Engineering Intelligence Governance Layer 之上增量实现，目标是给 AI 助手提供**只读的开发者上下文**：项目、文件、符号、依赖、Git、测试/构建六类上下文按需组装成受预算约束的 Context Bundle，供 Assistant 理解工程现状、生成更准确的 Proposal / Recommendation。

本阶段不新增执行能力、不扩大权限；一切上下文读取都是：

```text
Observe (只读)  →  Budget 限制  →  Security 过滤  →  Bundle 输出
```

完整链路：

```text
Engineering Context
        ↓
Developer Context Bundle（Project / File / Symbol / Dependency / Git / Test-Build）
        ↓
Assistant Understanding
        ↓
Proposal / Recommendation
        ↓
ApprovalStore
        ↓
Human Approval
```

Phase 演进：

```text
Phase 26  Engineering Intelligence Loop
        ↓
Phase 27  Engineering Intelligence Validation Layer
        ↓
Phase 28  Engineering Intelligence Governance Layer
        ↓
Phase 29  Advanced Developer Context & Read-only Code Intelligence
```

## Architecture

新增/扩展的实际文件：

### Backend — `local-bridge/app/context/dev/`

- `models.py`
  - 六类只读上下文模型：`DevProjectContext`（语言分布 / 文件数 / 包管理器 / git / 测试构建状态）、`DevFileContext`（路径 / 语言 / 大小 / 行数 / 内容 / 符号 / imports / 是否导出）、`DevSymbolContext`、`DevDependencyContext`、`DevGitContext`（branch / clean / changed / untracked / staged / diff / commits）、`DevTestBuildContext`（testStatus / buildStatus）。
  - `DevContextBundle`：聚合六类上下文的总包，带 `source="context/dev"`、`securityFiltering=True`、`truncated`、`size`。
- `budget.py`
  - `ContextBudget`：每文件读取上限（默认 256 KB）、符号数（500）、依赖数（200）、文件列表数（200）、diff 大小（64 KB）、总 bundle 大小（512 KB）、commit 数（10）、manifest 文件数（20）；超限一律截断并标记 `truncated=True`，绝不静默全量返回。
- `security.py`
  - `is_sensitive_path`：`.env` / key 材料 / credential 存储 / 证书 / `.git/` 等敏感路径永不进入上下文。
  - `redact_secrets`：对放行的文本做赋值脱敏、Bearer token 脱敏、secret 关键字脱敏（`***REDACTED***`）。
- `bundle.py`
  - `ContextBundleEngine`：组装六类上下文为总 bundle；复用 Phase 12 `CodeScanner`、`CodeIndex`，以及现有 `GitManager` / `WorkflowManager`。
- `symbols.py`
  - `SymbolContextService`：复用 Phase 12 `CodeIndex` 作为权威符号存储（function/class/interface/type/enum/variable），imports 从索引依赖边推导，export 从文件文本推导。
- `dependencies.py`
  - `DependencyContextService`：纯文本解析 package.json / requirements.txt / pyproject.toml / Cargo.toml / go.mod / pom.xml / Gemfile / build.gradle，**从不安装、升级、运行包管理器**。
- `git_context.py`
  - `GitContextService`：复用 `GitManager` 读 status/diff，commit 历史走固定参数沙箱化 git 调用；**从不 stage / commit / push / 修改工作树**。
- `tests.py`
  - `TestBuildContextService`：只读取 workflow 历史里最近一次测试结果与构建状态，**从不执行测试或构建**。
- `routes.py`
  - 注册 Phase 29 API（见下）；全部 GET 只读，全部经 `validate_project_name` / `validate_path` 沙箱校验。

### Backend — 其他

- `local-bridge/app/code_intelligence/parser.py`
  - 符号解析**增量扩展**：新增 `interface` / `type` / `enum` / `variable` 四类正则（严格追加，不修改既有模式的匹配结果；Phase 12 回归实测通过）。
- `local-bridge/app/main.py`
  - 注册 `register_dev_context_routes(app)`；本阶段无任何新审批动作、无新执行动作。

### Extension — `browser-extension/src/context/`

- `types.ts`：Phase 29 类型（`DevContextResponse`、`DevProjectContext`、`DevFileEntry`、`DevSymbol`、`DevDependency`、`DevGitContext`、`DevTestStatus`、`DevStatusResponse`）。
- `context-dashboard.ts`：只读 Developer Context Dashboard——项目 / 文件 / 符号 / 依赖 / Git / 测试构建摘要 + Context Preview 选择器（用户勾选要附带到下一条消息的上下文项，**不会自动发送**）；无 Execute / Apply / Fix / Approve / Auto 控件。
- `bridge/client.ts`：10 个只读 client 方法（bundle / project / files / file / symbols / symbol / dependencies / git / tests / status），全部 GET。
- `content/controller.ts` / `ui/panel.ts` / `state/store.ts`：接线 devContext 快照与选择状态（无项目时清空）。
- `ui/styles.css`：Dashboard 样式。

## API

### GET（全部只读、project-scoped、LEVEL_0）

| 端点 | 说明 |
|---|---|
| `GET /context/dev/bundle?project=&agent=` | 完整 Developer Context Bundle |
| `GET /context/dev/project?project=` | 项目上下文（语言 / 文件数 / 包管理器 / git / 测试构建） |
| `GET /context/dev/files?project=&limit=` | 文件清单（路径 / 语言 / 大小） |
| `GET /context/dev/file/{path}?project=&max_file_kb=` | 单文件内容（截断 + 脱敏 + 符号/imports/export） |
| `GET /context/dev/symbols?project=&q=&limit=` | 符号搜索（支持 q 过滤） |
| `GET /context/dev/symbol/{id}?project=` | 符号详情 |
| `GET /context/dev/dependencies?project=&limit=` | 依赖清单（纯文本解析，不运行包管理器） |
| `GET /context/dev/git?project=` | Git 只读状态（branch / changed / diff / commits） |
| `GET /context/dev/tests?project=` | 最近测试/构建状态（只读历史） |
| `GET /context/dev/status?project=` | 上下文可用性汇总 |

不存在任何 POST / execute / apply / approve / 写文件 / 安装依赖 / 运行测试端点。

## Security Boundary

严格保持：

- 只读：全部端点 GET，无执行、无源码修改、无 git 变更、无包管理操作、无测试/构建执行
- 预算约束：所有读取受 `ContextBudget` 限制，超限截断并标记，不静默全量返回
- 敏感路径过滤：`.env`、key 材料、credential 存储、证书、`.git/` 永不进入上下文
- 文本脱敏：`redact_secrets` 脱敏赋值 / Bearer / secret 关键字
- 沙箱校验：`validate_project_name` / `validate_path`（project 必须落在 workspace 内）
- 审计：每次读取记录 audit.jsonl（action / path / permission=LEVEL_0 / result）
- 无自动批准、无自动执行、无 Shell 执行器、无权限提升；Human-in-the-loop 边界不受影响

## Testing

### Backend（`local-bridge/tests/`）

- `test_phase29_context.py` — Project / File / Symbol / Dependency / Git / Test-Build / Bundle 各类上下文（预算截断、脱敏、符号搜索、沙箱校验、只读保证）
- `security/test_phase29_context_security.py` — 敏感路径拒绝、secret 脱敏、无写端点、无执行端点、project 沙箱、审计记录

结果：**54 passed**（含安全测试）。

### Extension（`browser-extension/tests/context-dev.test.ts`）

Developer Context Dashboard 只读渲染、10 个 client GET 方法、store 接线、类型契约、选择器不自动发送。结果：**29 passed**；Extension 全量 1410 passed。

### 验证命令

- pytest：Phase 29 定向 54 passed；Phase 25–28 回归 810 项通过；Phase 12（parser 相关）回归通过
- TypeScript typecheck：0 errors
- MV3 build：通过
- Python compileall：通过
- `git diff --check`：通过

## 完成标准对照

- [x] Developer Context Bundle（Project / File / Symbol / Dependency / Git / Test-Build 六类）
- [x] 显式预算（ContextBudget）与截断语义
- [x] 安全过滤（敏感路径 + secret 脱敏 + 沙箱校验 + 审计）
- [x] 只读 API（10 个 GET，无 POST / execute / approve）
- [x] 复用 Phase 12 CodeIndex / CodeScanner、GitManager、WorkflowManager（不重复造轮子）
- [x] 符号解析增量扩展（interface / type / enum / variable），Phase 12 无回归
- [x] Extension 只读 Dashboard + 选择器（不自动发送上下文）
- [x] 测试（Backend 54 + Security 专项 + Extension 29）
- [x] 文档 `docs/phase-29.md` + README 更新

## Human-in-the-loop 边界（未破坏）

上下文只是「读」，不做任何「写」；没有自动批准、自动执行、自动修复、源码修改、Shell 执行器、权限提升；一切 Proposal / 写入仍走 `Proposal → ApprovalStore → Human Approval → Controlled Write`。
