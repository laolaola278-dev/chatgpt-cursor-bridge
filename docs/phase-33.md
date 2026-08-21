# Phase 33 · Release & Real-world Validation

## 状态

Phase 33 把 Phase 32 的 AI Assistant 产品化成果变成 **可发布版本**：Release Package、安装文档、Provider 配置文档、Release Security Audit、可选的真实 Provider 验证与本地性能基线。本阶段 **不新增任何执行能力**，权限模型与 Phase 8 的 ApprovalStore 完全一致。

- ✅ `release/`：`AI-Assistant-extension.zip` / `INSTALL.md` / `CONFIG.md` / `build-release.sh`
- ✅ 8 步 Release Build（Clean → TypeScript → MV3 → Manifest → Required Files → Security Audit → ZIP → Inspect ZIP），任一步失败退出码非 0
- ✅ Release Security Audit：`.env` / API Key / Secret / Authorization / SQLite DB / Workspace / Tests / Source Map 全部拦截，且**区分"变量名"与"真实密钥值"**
- ✅ Manifest Audit：MV3、最小权限（`storage` + `scripting`）、无 `<all_urls>`、无开发期配置
- ✅ 可选真实 Provider 验证（`local-bridge/tests/real/`），**默认 SKIP**，需 `OPENAI_API_KEY` + `REAL_LLM_RUN=1` 双开关
- ✅ 本地性能基线（后端 4 项 + 扩展 3 项），只记录本机 elapsed / average / max
- ❌ 不新增 Autonomous Agent / Agent Loop / Auto Tool Execution / Auto Approval / Auto Fix / Auto Patch / Shell / Terminal
- ❌ 不新增 Intelligence / Governance / Graph / Memory Evolution 能力，不做权限提升，不绕过 ApprovalStore
- ❌ 不开始 Phase 34

完整发布链路：

```text
Source Repository
  ↓ npm run release（= bash release/build-release.sh）
Production Build（tsc --noEmit → Vite × 2 entry）
  ↓ Manifest Audit + Required Files + Security Audit
Release Package（release/AI-Assistant-extension.zip）
  ↓ release/INSTALL.md（Chrome / Edge chrome://extensions）
Installation → First Launch（默认 User Mode，首屏即 Chat）
  ↓ release/CONFIG.md
Provider Configuration（202 pending → 人工审批）
  ↓ POST /provider/test
Provider Test（固定安全词表）
  ↓
Chat / Streaming
  ↓ 可选：Ask AI Web Context / 只读 Developer Context
Tool Proposal（executed=false）
  ↓ ApprovalStore
  ↓ Human Approval
Controlled Tools（既有受控执行器）
```

## Release Package

| 文件 | 说明 |
|---|---|
| `release/AI-Assistant-extension.zip` | 可安装的 MV3 扩展包，53,226 bytes，**仅 3 个运行时文件** |
| `release/INSTALL.md` | 12 步安装流程、重新加载、查看错误、确认 Bridge、配置 Provider、常见错误 |
| `release/CONFIG.md` | OpenAI / Anthropic / DeepSeek 配置与 API Key 安全承诺 |
| `release/build-release.sh` | 8 步发布构建脚本，复用既有 `npm run build` 与 `app.release` 审计器 |

ZIP 内容（`unzip -l` 独立复核）：

```text
     4520  background/service-worker.js
   279172  content/content.js
      785  manifest.json
---------
   284477  3 files
```

不包含：`.env`、API Key、Secret、SQLite DB、Workspace Data、测试、源码、Source Map、开发期配置、调试日志。

## Release Build（8 步）

```bash
cd browser-extension && npm run release
# 或
bash release/build-release.sh
SKIP_NPM_BUILD=1 bash release/build-release.sh   # 复用已有 dist/ 重新打包
```

| 步骤 | 内容 | 失败行为 |
|---|---|---|
| 1 Clean | 删除 `dist/` 与旧 ZIP | `set -euo pipefail` |
| 2 TypeScript Build | `npx tsc --noEmit` | 退出码 1 |
| 3 MV3 Build | `CCB_TARGET=content/background npx vite build` | 退出码 1 |
| 4 Validate Manifest | `python -m app.release audit --manifest` | 退出码 1 |
| 5 Validate Required Files | `manifest.json` / `content/content.js` / `background/service-worker.js` | 退出码 1 |
| 6 Security Audit | `python -m app.release audit --dir` | 退出码 1 |
| 7 Generate ZIP | `python -m app.release package`（写前审计 + 写后审计，任一失败删除 ZIP） | 退出码 1 |
| 8 Inspect ZIP | `python -m app.release audit --zip` | 退出码 1 |

脚本只读取仓库，只写 `browser-extension/dist/` 与 `release/AI-Assistant-extension.zip`；不上传、不发布、不安装、不执行扩展（无 `curl` / `wget` / `scp` / `npm publish` / `git push`）。

## Release Security Audit（`local-bridge/app/release/`）

| 模块 | 职责 |
|---|---|
| `audit.py` | `secret_findings()` / `forbidden_path_findings()` / `audit_directory()` / `audit_zip()` / `audit_manifest()` |
| `package.py` | 用 `zipfile` 生成 ZIP（本机无 `zip` 可执行文件），写前写后各审计一次 |
| `__main__.py` | `audit` / `package` 子命令，避免 `runpy` 双导入告警 |

审计器是 **stdlib-only**：不 import `httpx` / `requests` / `urllib` / `socket` / `smtplib` / `ftplib`，不 import `subprocess`，不含 `os.system(` / `eval(` / `exec(` / `.approve(` / `ApprovalStore`。它只能报告，不能执行、不能批准、不能上传。

**变量名 ≠ 密钥值**：`SECRET_RULES` 的每条正则都要求"值"侧的 token，因此文档里的 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / `Authorization:` 说明文字不会误报，而 `sk-` 开头的真实长串、`Bearer <token>`、`.env` 文件与 `SQLite format 3` 头会被拦截。

## Manifest Audit

```json
"manifest_version": 3,
"permissions": ["storage", "scripting"],
"host_permissions": ["https://chatgpt.com/*", "https://chat.openai.com/*", "http://127.0.0.1:8765/*"],
"background": { "service_worker": "background/service-worker.js" },
"content_scripts": [{ "js": ["content/content.js"], "matches": ["https://chatgpt.com/*", "https://chat.openai.com/*"] }]
```

无 `<all_urls>`、无 `://*/*`、无 `optional_permissions`、无 `webRequestBlocking` / `declarativeNetRequest` / `chrome.debugger`，bundle 内无 `child_process` / `new Function(`。

## User Mode 发布体验

发布版默认 `uiMode === "user"`，首屏即 AI Assistant Chat，Surface 仅 `chat / model_selector / context / history / settings`。普通用户默认看不到 Governance / Intelligence / Engineering Graph / Metrics / Developer Context，也看不到任何 Execute / Approve / Apply / Auto Fix / Auto Patch / Run / Terminal / Shell 控件；Developer Mode 保留全部只读高级面板。后端能力一个都没删——User Mode 只是"简化展示"。

## Provider 状态

`GET /provider/status`（单数，返回 `{"providers": [...], "readOnly": true}`）为 OpenAI / Anthropic / DeepSeek 各返回一条记录，Settings 页渲染 Connected / Not configured / Failed 三态，并只显示掩码尾部（`****cdef`）或 `no key stored`。**绝不**返回 API Key、Authorization Header、Provider Secret、内部异常或本地路径。

## 真实 Provider 验证（可选，默认 SKIP）

```bash
# 默认：一个 token 都不花，一个出网连接都不开
python -m pytest tests/real -q          # → 13 skipped

# 显式双开关才会真正执行
OPENAI_API_KEY=<your key> REAL_LLM_RUN=1 python -m pytest tests/real -q
```

覆盖：Streaming、≥100 条消息会话（只发送有界尾部）、固定 ~8 KB 长上下文、错误 Key 的 401、**mock transport** 的 429 / 5xx、Secret Leak 断言。

两处刻意的取舍：

- **绝不制造 429**：规范禁止"为触发限流而发起滥用流量"，因此 429 与 5xx 走 `httpx.MockTransport`，不发真实突发请求。
- **绝不回显**：断言只比对固定安全词表与"密钥不存在"，测试消息里没有密钥、没有 `Authorization` Header、没有 Provider 原始响应体，**失败报告本身不会变成泄漏**。

## 性能基线（仅本机）

后端 `tests/test_phase33_performance.py`：

| 测量 | 内容 | 预算（宽松） |
|---|---|---|
| `conversation_round_trip_100` | 100 条消息 SQLite 往返 | total 30 s / avg 0.30 s |
| `concurrent_writes_100` | 8 线程并发写入 100 条，无丢行、ID 不重复 | total 30 s / avg 0.30 s |
| `long_conversation_300` | 300 × ~2 KB 长会话，`limit` 生效（读回恰好 200） | total 90 s / avg 0.30 s |
| `stream_events_100` | 99 delta + 1 done，按 SSE 路由的写法序列化 | total 2 s / avg 0.02 s |

扩展 `tests/phase33-release.test.ts`：100 turn 渲染 < 4000 ms、100 token 累积 < 1500 ms、100 次 Chat 状态更新 < 4000 ms。

每项记录 elapsed / average / max，并有一条测试断言这些名字**不包含** `openai` / `anthropic` / `deepseek` / `throughput`——这是本机基线，**不代表任何 Provider 的生产容量**。

## 测试

| 套件 | 数量 | 结果 |
|---|---|---|
| `tests/test_phase33_release.py` | 66 | passed |
| `tests/security/test_phase33_release_security.py` | 27 | passed |
| `tests/test_phase33_performance.py` | 9 | passed |
| `tests/real/test_phase33_openai_real.py` | 13 | **skipped（默认）** |
| `browser-extension/tests/phase33-release.test.ts` | 21 | passed |
| Extension 全量 `vitest run` | 1712（29 文件） | passed |
| Phase 31/32 + Phase 8 + security + health 定向回归 | 299 | passed |

## 安全边界（本阶段复核，未改动）

- `LLM Gateway ≠ Tool Runtime`：`toolCallsExecuted` 永远 `false`，Tool Call 只是提案
- `NEVER_AVAILABLE`（后端 `app/assistant/service.py` 与扩展 `src/assistant/types.ts` 一字不差）：`execute` / `approve_from_chat` / `apply_patch` / `auto_fix` / `auto_approve` / `shell`
- Provider 写入 / Key 删除仍是 `202 pending` → `POST /permission/approve` → 人工批准；Phase 8 审批端点仍在（有测试正向断言它存在）
- 后端错误只用固定安全词表；Bridge 不可达时 UI 只显示 `Local Bridge unavailable. Start it with: uvicorn app.main:app --port 8765`，无 stack trace、无文件路径、无内部异常
- Stop 只结束本次流式输出，不自动重试、不自动重发（`controller.ts` 内无 `setTimeout` / `setInterval` / `retry`）

## 已知限制

- `npm run build` 的脚本用的是 POSIX 环境变量语法（`CCB_TARGET=content vite build`），在 Windows 的 `cmd.exe`（npm 默认 script shell）下无法执行；`bash release/build-release.sh` 走同一命令则正常，`npm run release` 因此可用。
- 本仓库当前没有 `.git` 目录，`git diff --check` 无法执行（记为 not applicable，不记为通过）。
- 真实 Provider 验证需要人工提供凭据，CI 默认不跑；429 / 5xx 仅 mock 覆盖。
- 性能数字只在本机有意义，不构成任何生产容量承诺。

## Human-in-the-loop

发布不改变权限模型：安装扩展**不授予任何执行权限**。模型能做的最多是提出提案，任何写操作都停在 `202 pending`，直到人在审批队列里点批准，再由既有受控执行器执行。

## 当前 Phase

Phase 33 - Release & Real-world Validation。Phase 34 未开始。
