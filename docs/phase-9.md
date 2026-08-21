# Phase 9 Completion Report

项目：**ChatGPT Cursor Bridge**  
版本：**0.9.0**

Phase 9 将 Phase 8 的 Persistent Agent Runtime 增量升级为可审计、可路由、可人工审批的 Multi-Agent Intelligence Runtime。模型路由和 Agent 协作只产生受控元数据；任何有副作用的动作仍保持：

```text
Preview → Approval → Execution
```

本阶段未启动服务，未实施 Phase 10。

## 1. Architecture

新增后端模块：

- `local-bridge/app/model_router/`：Provider abstraction、能力注册表、任务分类和确定性模型选择。
- `local-bridge/app/agent/`：Agent 角色、生命周期、持久化存储、权限边界和消息协议。
- `local-bridge/app/workflow/quality_gate.py`：Review → Test Result → Risk Assessment → Human Approval 质量门禁。

运行时关系：

```text
Session
  └── Agent (role + memory scope + permissions + model)
        └── Workflow Stage (multiple agent ids)
              └── Quality Gate
                    └── Human Approval
```

Model Router 是 provider-agnostic 的 metadata-only 层；Phase 9 不调用外部模型，也不新增 API key 或第三方服务依赖。

## 2. Agents

内置角色：

- `PLANNER`
- `ARCHITECT`
- `CODER`
- `TESTER`
- `REVIEWER`

每个 Agent 持久化：

- `session_id`
- `role`
- `memory_scope`
- `permissions`
- `model_id`
- Project / Workflow / Stage 绑定
- 生命周期和 transition history

Agent 生命周期为：

```text
CREATED → ACTIVE ↔ PAUSED → COMPLETED
                    └──────→ FAILED
```

角色权限采用固定 allowlist，创建时拒绝越权权限。Agent 不拥有 Shell、文件写入或自动执行权限。

## 3. Agent Message Protocol

`AgentMessage` 包含：

- `message_id`
- `from_agent`
- `to_agent`
- `task`
- `context_reference`
- `created_at`

消息保存为 append-only JSONL 元数据，并写入 Audit。消息内容不能携带隐式工具权限或执行入口；API 发送消息仍先进入 ApprovalStore，批准后才会落盘。

新增只读状态接口：

```text
GET /agent/status?project=<name>&task=<task>
GET /model-router/capabilities
GET /model-router/route?task=<task>
```

## 4. Router

支持任务分类：

- Architecture
- Coding
- Debugging
- Testing
- Review

默认注册本地 provider metadata：Architect、Coder、Tester、Reviewer 四类模型描述。路由结果包含分类、置信度、触发信号和选中的模型能力；preferred model 只有在满足任务能力时才会生效。

## 5. Workflow Integration and Quality Gate

Workflow Stage 新增：

- `agentIds`：同一 Stage 可绑定多个 Agent。
- `qualityGate`：审查、测试和风险评估结果。

新增审批边界：

- `POST /agent/create`
- `POST /agent/{id}/transition`
- `POST /agent/message`
- `POST /workflow/{id}/stage/agent`
- `POST /workflow/{id}/quality-gate`

这些接口都只创建 Pending Approval；只有用户明确调用 `/permission/approve` 后，Agent metadata、消息、Stage 绑定或质量门禁才会持久化。

当 Delivery Stage 已绑定 Agent 时，不能跳过完整质量门禁。必须先提交并批准：

```text
Review Agent approved
  ↓
Tester result passed
  ↓
Risk assessment recorded
  ↓
Human approves Delivery Stage
```

旧的无 Agent Workflow 仍保持 Phase 1–8 的兼容路径。

## 6. Security Verification

- 没有自动执行、自动批准或隐藏 Agent action。
- Model Router 不执行模型调用，也不授予工具权限。
- Agent role permissions 是固定 allowlist，Coder 无法声明 `shell_command` 等越权权限。
- Agent message、创建、transition、Stage 绑定和 quality gate 提交都共享 ApprovalStore 与 Audit。
- Workflow Stage 批准仍不会批准 LEVEL_2 操作。
- Context、Agent Status、Model Router 和 Dashboard 读取接口均为只读。
- 保持 `shell=False`、固定 argv、白名单命令和 workspace sandbox。
- Extension 只显示 Agent 状态和模型选择，不增加执行按钮或数据库写入口。

## 7. Tests

验证结果：

- Local Bridge：`pytest -q` → **173 passed**（Phase 1–8 回归 + Phase 9 tests）。
- Phase 9 backend coverage：Model Router 分类/能力选择、Agent lifecycle、权限隔离、消息审计、Quality Gate、Approval-gated Agent creation。
- Browser Extension：`npm run typecheck` → **通过**。
- Browser Extension：`npm test -- --run` → **90 passed**。
- Browser Extension：`npm run build` → **通过**，生成 content/background MV3 bundles。
- Python：`python3 -m compileall -q local-bridge/app` → **通过**。
- Chrome/Chromium 当前不可用，因此未执行真实浏览器视觉交互验证。

## 8. Future Roadmap (Phase 10 recommendation only)

仅提出建议，不实施：

1. 增加真实 Provider Adapter 与凭据隔离，但保持每一次模型工具调用都必须产生 Approval。
2. 增加 Agent 事件流、并发调度和可取消的长任务恢复机制。
3. 增加基于能力和风险的可解释成本/延迟策略与离线模型包管理。
4. 增加跨设备 Agent 身份、消息签名和更细粒度的 Context 访问审计。

> Phase 10 未开始，等待确认。
