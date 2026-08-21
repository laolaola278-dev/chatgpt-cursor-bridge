import { db } from "@/db";
import { sql } from "drizzle-orm";

export const dynamic = "force-dynamic";

const modules = [
  ["app/git/manager.py", "Git status / diff / commit；固定 argv、shell=False"],
  ["app/git/models.py", "GitStatus 与 GitCommitResult 类型模型"],
  ["app/git/policy.py", "commit message 与 workflow/stage 绑定校验"],
  ["app/test_runner/runner.py", "白名单测试执行、超时、输出截断、安全 cwd"],
  ["app/test_runner/policy.py", "300s 超时与 64KB 总输出策略"],
  ["app/security/command_policy.py", "三命令白名单、Shell 注入与环境修改拦截"],
  ["app/workflow/rollback.py", "执行前快照、按时间逆序 Stage 恢复"],
  ["app/workflow/manager.py", "测试结果绑定 TESTING 报告、工具绑定校验"],
  ["app/context/service.py", "Project Context API、Context Snapshot 与只读恢复上下文"],
  ["app/context/intelligence/", "确定性 Context 压缩、摘要与 context_index.db 搜索"],
  ["app/session/", "持久化 Agent Session 生命周期与 Workflow/Stage/Approval 绑定"],
  ["app/hardening/maintenance.py", "Health、Audit rotation、Backup、Recovery"],
  ["app/dashboard.py", "只读 Local Bridge Developer Dashboard"],
  ["app/model_router/", "Provider abstraction、能力注册表与任务分类"],
  ["app/agent/", "Planner / Architect / Coder / Tester / Reviewer 持久化运行时"],
  ["app/workflow/quality_gate.py", "Review → Test → Risk → Human Approval 质量门禁"],
  ["app/runtime/", "持久化 Runtime 生命周期、Recovery 与 proposal-only Scheduler"],
  ["app/task/", "SQLite Task Queue 与严格状态机"],
  ["app/event/", "带 checksum 的 JSONL Event Bus 与 Audit 同步"],
  ["app/quality/", "Git diff、测试、风险和 Memory 的 Quality Gate 2.0 + 多 Agent Quality Gate 3.0"],
  ["app/collaboration/", "Agent Team、Coordinator、Negotiation、Conflict Resolution；只产生 Proposal"],
  ["app/task/dependency.py", "Task Dependency Graph、depends_on / blocks / requires_review 与循环检测"],
  ["app/memory/intelligence/context_router.py", "按 Planner / Architect / Coder / Tester / Reviewer 角色只读路由 Context"],
  ["app/metrics/", "AgentMetrics 统计，不改变权限"],
  ["app/code_intelligence/", "只读扫描、AST/正则符号解析、SQLite files/symbols/dependencies 索引"],
  ["app/project_intelligence/", "ProjectProfile：语言、框架、架构摘要、模块数与复杂度"],
  ["app/knowledge_graph/", "Module / Service 节点与 depends_on 关系的 SQLite 知识图谱"],
  ["app/impact/", "基于依赖关系的变更影响与风险分析"],
  ["app/memory/project.py", "Architecture / Decisions / Bugs / Changes 的审批后项目记忆"],
  ["app/quality/gate4.py", "Architecture Impact、Change Risk、Regression Risk、Historical Stability"],
];

const commands = [
  ["pytest", '["pytest"]'],
  ["npm test", '["npm", "test", "--"]'],
  ["cmake build", '["cmake", "--build", "build"]'],
];

const endpoints = [
  ["GET", "/git/status", "LEVEL_0", "分支、修改、未跟踪、暂存状态"],
  ["GET", "/git/diff", "LEVEL_0", "Working tree / staged diff"],
  ["POST", "/git/commit", "LEVEL_1", "必须绑定 workflow/stage，先预览"],
  ["POST", "/test/run", "LEVEL_1", "仅 TESTING stage，先审批"],
  ["POST", "/workflow/{id}/stage/rollback", "LEVEL_1", "Stage 级逆序恢复，先预览"],
  ["GET", "/context/project", "LEVEL_0", "恢复当前 workflow、tasks、tests、Git"],
  ["GET", "/context/search", "LEVEL_0", "跨项目关键词与日期过滤，只读"],
  ["GET", "/session/list", "LEVEL_0", "读取持久化 Agent Session 状态"],
  ["POST", "/permission/reconfirm", "—", "恢复审批重新确认，不执行"],
  ["GET", "/system/health", "LEVEL_0", "memory / database / workspace / workflow / approval"],
  ["GET", "/dashboard", "LEVEL_0", "只读 Developer Dashboard"],
  ["GET", "/agent/status", "LEVEL_0", "只读 Agent 状态与模型选择"],
  ["GET", "/model-router/route", "LEVEL_0", "确定性任务分类与模型能力路由"],
  ["POST", "/agent/message", "LEVEL_1", "消息审计，先审批后落盘"],
  ["POST", "/workflow/{id}/quality-gate", "LEVEL_1", "Review/Test/Risk 质量门禁"],
  ["POST", "/code/index", "LEVEL_1", "扫描并写入 Code Index，必须审批"],
  ["GET", "/project/profile", "LEVEL_0", "只读 Project Profile 与复杂度"],
  ["GET", "/project/graph", "LEVEL_0", "只读 Architecture Knowledge Graph"],
  ["GET", "/impact/analyze", "LEVEL_0", "只读 affected modules 与风险"],
  ["GET", "/context/query", "LEVEL_0", "按 Agent 角色检索项目上下文"],
  ["POST", "/memory/project/propose", "LEVEL_1", "Project Memory Proposal，必须审批"],
  ["GET", "/quality/v4/{id}", "LEVEL_0", "Quality Gate 4.0 综合评分"],
];

const checks = [
  "拒绝 ; && || | > < ` $(...) 与换行",
  "拒绝 PATH / PYTHONPATH / NODE_OPTIONS / LD_PRELOAD 修改",
  "拒绝任意 Shell 脚本与非白名单参数",
  "subprocess 全部参数数组 + shell=False",
  "cwd 必须由 Project Sandbox 解析",
  "测试强制超时，stdout + stderr 总量限制",
  "Git commit / Test / Rollback 全部 Preview → Approval → Execution",
  "LEVEL_2 不随 Workflow Stage 批量批准",
  "恢复请求只进入 RECOVERED，必须重新确认后才能进入执行审批",
  "Context Search、Dashboard、Session 查询均无写入入口",
  "Agent role permissions 固定 allowlist，模型路由不调用外部 Provider",
  "Agent 创建、消息、Stage 绑定和 Quality Gate 全部 Preview → Approval → Execution",
  "Code Index 写入与 Project Memory Proposal 经过同一 ApprovalStore，GET 查询只读",
  "Scanner 不执行项目代码；Context、Graph、Impact 与 Metrics 不创建执行入口",
];

const testRows = [
  ["Command Policy", "27+", "注入、非法命令、环境修改、固定 argv"],
  ["Test Runner", "10", "shell=False、失败、超时、输出、cwd、审批、stage 限制"],
  ["Git", "9", "status、diff、commit 审批、绑定、clean tree、审计"],
  ["Rollback", "6", "文件恢复、无快照、目录隔离、新文件、多动作逆序、审计"],
  ["Extension Protocol", "13", "git.diff、workflow.status、test.run Schema 与路由"],
];

export default async function HomePage() {
  await db.execute(sql`select 1`);
  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,#dbeafe,transparent_34%),linear-gradient(135deg,#f8fafc,#eef2ff_48%,#f8fafc)] px-6 py-10 text-slate-950">
      <div className="mx-auto flex max-w-7xl flex-col gap-8">
        <section className="rounded-[2rem] border border-white/70 bg-white/85 p-8 shadow-[0_30px_90px_rgba(15,23,42,.12)] md:p-12">
          <p className="text-sm font-semibold uppercase tracking-[.22em] text-blue-700">Phase 12 · Project Intelligence Layer</p>
          <h1 className="mt-5 text-4xl font-black tracking-tight md:text-6xl">ChatGPT Cursor Bridge</h1>
          <p className="mt-6 max-w-4xl text-lg leading-8 text-slate-700">系统现在具备受人工监督的 Project Intelligence Layer：只读 Scanner 建立 Code Symbol Index 与依赖关系，Project Profile、Architecture Knowledge Graph、Context Query、Impact Analysis 和 Quality Gate 4.0 为 Planner、Architect、Coder、Tester 与 Reviewer 提供长期项目理解。索引写入和 Project Memory Proposal 仍然遵循 Proposal → Risk Evaluation → Approval Queue → Human Approval → Execution；系统不开放通用 Shell、自动修改或自动重构。</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <span className="rounded-full bg-emerald-100 px-4 py-2 text-sm font-semibold text-emerald-800">Phase 12 · Code Intelligence + Graph</span>
            <span className="rounded-full bg-blue-100 px-4 py-2 text-sm font-semibold text-blue-800">shell=False · Fixed argv</span>
            <span className="rounded-full bg-rose-100 px-4 py-2 text-sm font-semibold text-rose-800">No arbitrary shell</span>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
            <h2 className="text-2xl font-black">完成模块</h2>
            <div className="mt-5 space-y-3">{modules.map(([file, desc]) => <div key={file} className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><p className="font-mono text-xs font-bold text-blue-800">{file}</p><p className="mt-1 text-sm leading-6 text-slate-700">{desc}</p></div>)}</div>
          </article>
          <div className="flex flex-col gap-6">
            <article className="rounded-3xl bg-slate-950 p-7 text-white shadow-lg">
              <h2 className="text-2xl font-black">唯一允许的测试命令</h2>
              <div className="mt-5 space-y-3">{commands.map(([alias, argv]) => <div key={alias} className="rounded-xl bg-white/10 p-4"><p className="font-bold text-blue-200">{alias}</p><code className="mt-1 block text-xs text-slate-300">{argv}</code></div>)}</div>
              <p className="mt-4 text-xs leading-6 text-slate-400">不接受额外参数，不调用 shell，不执行脚本。</p>
            </article>
            <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
              <h2 className="text-2xl font-black">安全检查</h2>
              <ul className="mt-5 space-y-3">{checks.map(item => <li key={item} className="flex gap-3 text-sm text-slate-700"><span className="font-black text-emerald-600">✓</span><span>{item}</span></li>)}</ul>
            </article>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
          <h2 className="text-2xl font-black">Toolchain API</h2>
          <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200"><table className="w-full text-left text-sm"><thead className="bg-slate-100"><tr><th className="p-3">Method</th><th className="p-3">Endpoint</th><th className="p-3">Permission</th><th className="p-3">说明</th></tr></thead><tbody>{endpoints.map(([m,e,l,d]) => <tr key={e} className="border-t border-slate-200"><td className="p-3 font-mono font-bold text-blue-700">{m}</td><td className="p-3 font-mono text-xs">{e}</td><td className="p-3">{l}</td><td className="p-3 text-slate-700">{d}</td></tr>)}</tbody></table></div>
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
            <h2 className="text-2xl font-black">Workflow Tool Binding</h2>
            <pre className="mt-5 overflow-x-auto rounded-2xl bg-slate-950 p-5 font-mono text-xs leading-6 text-slate-200">{`Workflow → TESTING Stage → test.run
   ↓ Preview (argv / cwd / timeout / output limit)
Permission Approval
   ↓ subprocess.run([...], shell=False)
Test Result
   ↓
TESTING Report Draft
## Coverage
## Results
## Gaps
   ↓ User reviews and approves Stage`}</pre>
          </article>
          <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
            <h2 className="text-2xl font-black">Enhanced Rollback</h2>
            <pre className="mt-5 overflow-x-auto rounded-2xl bg-slate-950 p-5 font-mono text-xs leading-6 text-slate-200">{`Before Execution
  → snapshot file / memory / git HEAD
  → ROLLBACK_ROOT/<workflow>/<stage>/

Rollback Request
  → Preview affected Actions
  → User Approval
  → Restore in reverse execution order

Existing file → original bytes
Created file  → remove
Memory append → original document
Git commit    → git reset --mixed previous HEAD`}</pre>
          </article>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
          <h2 className="text-2xl font-black">测试结果</h2>
          <div className="mt-5 grid gap-3 md:grid-cols-2">{testRows.map(([name,count,coverage]) => <div key={name} className="rounded-2xl border border-slate-200 p-4"><div className="flex justify-between"><b>{name}</b><span className="font-bold text-emerald-700">{count}</span></div><p className="mt-2 text-xs leading-6 text-slate-600">{coverage}</p></div>)}</div>
          <p className="mt-5 rounded-2xl bg-emerald-50 p-4 text-sm font-semibold text-emerald-900">Python：390 passed · Extension：136 passed · TypeScript：0 errors · MV3 production build：通过</p>
        </section>

        <section className="rounded-3xl border border-amber-200 bg-amber-50 p-7 text-amber-950"><h2 className="text-2xl font-black">Phase 12 安全边界</h2><p className="mt-3 text-sm leading-7">Scanner 只读解析，不导入或执行项目代码；Code Index 写入、Project Memory Proposal 与任何既有副作用仍走 ApprovalStore。Context Query、Knowledge Graph、Impact Analysis、Quality Gate 和 Extension Project Intelligence 面板均无执行按钮，Phase 13 仅作为后续建议。</p></section>
      </div>
    </main>
  );
}
