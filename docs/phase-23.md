# Phase 23 Completion Report · Organization Graph Intelligence

Phase 23 已完成：在 Phase 22 组织级工程智能之上增加**组织图谱推理层**。系统现在可以对组织知识图谱做只读推理（祖先/后代/归属/影响分析）、为非层级关系建模、向 AI 注入稳定的组织上下文，并对图谱做版本化快照与校验恢复；仍然不能自动修改代码、自动执行或绕过人工审批。

## 1. Graph Reasoning

新增 `local-bridge/app/organization_graph/reasoning.py`：

- `GraphReasoningEngine` 全部为纯只读遍历与分析；缺失节点抛 `ResourceNotFound`（404）。
- `get_ancestors(node_id)`：最近优先的祖先链（parent → grandparent → …），带环保护。
- `get_descendants(node_id)`：任意深度的全部后代（parent_id 广度优先）。
- `get_descendants_by_type(node_id, type)`：按实体类型过滤后代（如只取 `INCIDENT`）。
- `find_owner(node_id)`：最近 owning team；无 team 时回退到 company；未知返回 `owner: null`。
- `impact_analysis(node_id)`：沿**非层级边**做方向感知的影响分析——`IMPACTS` 按 source→target、`CAUSED_BY` 与 `DEPENDS_ON` 按 target→source（a 依赖 b 意味着 b 变化影响 a）、`RELATED_TO` 无向；输出 `direct` / `transitive` / `impacted`。
- `detect_cycles()`：Johnson-lite DFS 检测有向环，过滤自环与长度 ≤ 2 的平凡环。

## 2. 非层级 Edge 模型

新增 `local-bridge/app/organization_graph/models.py`：

- `EdgeType`：`RELATED_TO` / `IMPACTS` / `CAUSED_BY` / `DEPENDS_ON` 四类非层级关系。
- `OrgEdge.is_hierarchy` 恒为 `False`：层级只通过 `parent_id` 表达，关系边永不视为层级边。
- `PARENT_TYPE_CHAIN`：`TEAM→COMPANY / PROJECT→TEAM / SERVICE·REPOSITORY·ARCHITECTURE_DECISION·INCIDENT→PROJECT` 严格层级保留；旧数据兼容（parent_id 仍是真相来源，不追溯强制）。
- `canonical_graph_json()`：节点按 id、边按 (source, target, relation) 排序的确定性 JSON 序列化，供快照 checksum 使用；`checksum_of()` 输出 SHA-256。

## 3. AI Context Injection

新增 `local-bridge/app/organization_graph/context.py`：

- `OrganizationContextBuilder.build_context(node_id)` 输出**稳定结构**：
  `node / owner / hierarchy / related_architecture / incidents / ancestorChain / readOnly`。
- `related_architecture` 收集与节点直接相邻的架构节点与边；`incidents` 聚合项目下（或节点自身）的 Incident；`ancestorChain` 为名字链（company → team → … → node）。
- 纯只读：构建上下文不写任何存储。

## 4. Snapshot Versioning

新增 `local-bridge/app/organization_graph/snapshot.py` + `storage.py`：

- `organization_graph_snapshots` 表（`CREATE TABLE IF NOT EXISTS`，迁移安全）。
- `GraphSnapshotManager.create()` 生成 canonical JSON + SHA-256 checksum 快照；`list()` 只读列出。
- `restore()` 先校验 checksum（不匹配拒绝恢复），再经单事务 `BEGIN → 全量替换 → COMMIT`，失败 `ROLLBACK`——恢复失败不污染当前图。

## 5. API

新增 `local-bridge/app/organization_graph/routes.py`（9 个端点，全部经 `_register_pending` → `/permission/approve`）：

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/organization-graph/ancestors?node_id=` | LEVEL_0 | 祖先链（只读） |
| GET | `/organization-graph/descendants?node_id=&type=` | LEVEL_0 | 后代 / 按类型过滤（只读） |
| GET | `/organization-graph/owner?node_id=` | LEVEL_0 | 归属查询（只读） |
| GET | `/organization-graph/impact?node_id=` | LEVEL_0 | 影响分析（只读） |
| GET | `/organization-graph/context?node_id=` | LEVEL_0 | AI 上下文注入（只读） |
| GET | `/organization-graph/snapshot/list` | LEVEL_0 | 快照列表（只读） |
| POST | `/organization-graph/sync` | LEVEL_1 | 把 Phase 22 org 实体同步进推理图（ApprovalStore） |
| POST | `/organization-graph/snapshot/create` | LEVEL_1 | 创建校验快照（ApprovalStore） |
| POST | `/organization-graph/snapshot/restore` | LEVEL_1 | 校验后事务性恢复（ApprovalStore） |

配套接线：

- `app/models/request.py`：新增 3 个请求模型（sync / snapshot create / snapshot restore）。
- `app/config.py`：新增 `organization_graph_db_path`。
- `app/security/permissions.py`：3 个 action 全部映射 **LEVEL_1**。
- `app/main.py`：注册 `register_organization_graph_routes` 并支持 3 个 action 的审批执行。

## 6. Security Review

- 6 个 GET 端点全部 `readOnly: true` 并写入 Audit；多次读取不修改任何存储（测试断言）。
- 3 个 POST 全部返回 202 + `requestId`，批准前零副作用（快照表为空、图不变）。
- 3 个 action 全部映射 LEVEL_1，必须人工经 ApprovalStore 批准。
- `GraphReasoningEngine` / `OrganizationContextBuilder` / `GraphSnapshotManager` / `OrganizationGraphStorage` 源码不含 `subprocess` / `shell` / 批准改写路径；恢复仅替换图谱元数据，不触及项目源码与 Memory。
- 未新增 Shell、外部模型调用、自动批准、自动执行或权限提升。

## 7. Tests

新增 `local-bridge/tests/test_phase23_organization_intelligence.py`（**33 个用例**）：

- Reasoning：祖先链、BFS 后代、按类型过滤、owner（team 优先 / company 回退 / unknown）、方向感知影响分析（direct/transitive）、环检测、缺失节点 404。
- Context：稳定字段结构、owner/hierarchy/ancestorChain、related_architecture 与 incidents 聚合。
- Snapshot：canonical JSON 确定性（乱序输入同 checksum）、create/list、restore 成功、checksum 篡改拒绝、恢复事务不污染当前图、快照 404。
- API：GET 只读契约 + 审计、POST 202 → approve → 持久化、LEVEL_1 映射。
- 安全回归：源码不可变（SHA-256 断言）、无自动执行、无执行入口、GET 不改写存储。

验证结果：

- Backend full suite：**1635 passed**（Phase 22 为 1602，新增 33，无回归）
- Python `compileall`：通过
- `git diff --check`：通过

## 8. Limitations

- 推理基于确定性图遍历（层级 parent_id + 非层级边），无语义/向量检索。
- 影响分析只覆盖已登记的非层级边；未建模的隐式依赖不会出现在结果中。
- 快照恢复是元数据级（组织图本身），不恢复项目源码、Memory 或审批队列。
- 扩展端未被 Phase 23 触碰（无新增面板）；治理/组织面板仍为 Phase 21/22 的只读面板。

## 9. Phase 24 Proposal

- **Semantic Graph Query**：基于 metadata 的向量索引（不调用外部模型）提升组织图检索召回率。
- **Impact-aware Approval**：影响分析结果作为审批预览的一部分展示给人类审批者。
- **Snapshot Scheduling**：定期自动创建快照（仍审批门控），支持时间点对比。
- **Graph Visualizer**：扩展端只读组织图可视化（层级 + 非层级边）。
