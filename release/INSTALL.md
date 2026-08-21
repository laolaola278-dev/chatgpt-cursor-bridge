# AI Assistant · 安装指南（Phase 33 Release）

本文件说明如何把 `AI-Assistant-extension.zip` 安装到 Chrome / Edge，并让它连上本机
Local Bridge。全部步骤都在你自己的机器上完成，不需要发布到应用商店。

> **安全前提**：安装扩展不会获得任何执行权限。扩展只能"提出建议"，任何文件写入、
> 补丁应用、命令执行仍然必须经过 Tool Proposal → ApprovalStore → 人工批准。
> 本文件不包含任何真实 API Key，也永远不要把真实 Key 写进文档或截图。

## 0. 准备

| 需要 | 版本 / 说明 |
|---|---|
| Chrome 或 Edge | Chrome 114+（`manifest.json` 的 `minimum_chrome_version`） |
| Python | 3.11+（运行 Local Bridge） |
| Release 包 | `release/AI-Assistant-extension.zip` |

如果仓库里还没有 ZIP，先自己构建一个：

```bash
cd browser-extension
npm install
npm run release          # 等价于 bash ../release/build-release.sh
```

构建流程为 Clean → TypeScript Build → MV3 Build → Validate Manifest →
Validate Required Files → Security Audit → Generate ZIP → Inspect ZIP，
任何一步失败都会以非 0 退出码结束，不会产出可发布的包。

## 1. 安装 12 步

1. **下载 ZIP**：取得 `release/AI-Assistant-extension.zip`。
2. **解压 ZIP**：解压到一个稳定目录，例如 `~/ccb-extension/`。Chrome 加载的是
   解压后的目录，删除或移动该目录扩展就会失效。
3. **打开扩展页**：地址栏输入 `chrome://extensions`（Edge 为 `edge://extensions`）。
4. **打开开发者模式**：右上角 **Developer mode / 开发者模式** 开关打开。
5. **点击 Load unpacked**：左上角 **Load unpacked / 加载已解压的扩展程序**。
6. **选择目录**：选择 **包含 `manifest.json` 的那一层目录**（不是它的父目录，
   也不要选 ZIP 文件本身）。解压后的结构应当是：

   ```text
   ccb-extension/
     manifest.json
     content/content.js
     background/service-worker.js
   ```

7. **启动 Local Bridge**：

   ```bash
   cd local-bridge
   pip install -r requirements.txt
   uvicorn app.main:app --host 127.0.0.1 --port 8765
   ```

8. **打开扩展**：访问 `https://chatgpt.com/`，页面右侧出现
   **ChatGPT Cursor Bridge** 浮动面板。首屏即 User Mode 的 AI Assistant Chat。
9. **进入 Settings**：面板下方的 **Provider Settings**。
10. **配置 Provider**：选择 Provider（`openai` / `anthropic` / `deepseek` / `local`）、
    Model，把 API Key 粘进 **API Key** 密码框，点击 **Save**。
    保存是审批动作：Bridge 返回 202 pending，需要人工批准后才真正生效
    （详见 [`CONFIG.md`](CONFIG.md)）。
11. **测试连接**：点击 **Test Connection**。状态只会是固定词表中的一项：
    `Connected` / `Not configured` / `Invalid API key` / `Rate limit reached` /
    `Provider unavailable` / `Backend unreachable` / `Provider rejected the request`。
12. **开始对话**：在输入框提问并 **Send**。流式输出中可随时 **Stop**；
    Stop 只停止本次输出，**绝不自动重试、绝不自动重发**。

## 2. 常用操作

### 重新加载扩展

改动代码或换了新 ZIP 之后：`chrome://extensions` → 找到 **ChatGPT Cursor Bridge**
→ 点击 **↻ Reload**，然后刷新 `chatgpt.com` 页面。换新 ZIP 时先解压覆盖旧目录再 Reload。

### 查看错误

| 位置 | 看什么 |
|---|---|
| `chrome://extensions` → **Errors** | manifest / 加载期错误 |
| `chrome://extensions` → **service worker** | 后台 Service Worker 控制台 |
| `chatgpt.com` 页面 DevTools Console | Content Script 错误 |
| Local Bridge 终端输出 | 后端请求日志 |

日志中不会出现 API Key、Authorization Header 或 Provider 原始响应体。

### 确认 Bridge 在运行

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/provider/status
curl http://127.0.0.1:8765/models
```

`/health` 返回服务信息，`/provider/status` 返回每个 Provider 的
`connected` / `not_configured` / `failed`（**不含** Key、Header 或内部异常），
`/models` 返回可选模型。面板顶部的 **Bridge:** 行显示 `Connected` 即为正常。

## 3. 故障排查

界面上只会出现下表右侧的固定文案。**不会**出现 stack trace、文件绝对路径、
内部异常类型、SQL、Provider 原始响应体、API Key 或 Authorization Header。

| 现象 | 界面文案 | 处理 |
|---|---|---|
| Bridge 没启动 | `Local Bridge unavailable. Start it with: uvicorn app.main:app --port 8765` | 在 `local-bridge/` 下启动 uvicorn，再点面板的 **Connect / Refresh** |
| 后端连不上（端口占用 / 防火墙 / 改过端口） | `Backend unreachable` | 确认 `curl http://127.0.0.1:8765/health` 可达；端口必须是 8765，因为 `manifest.json` 的 `host_permissions` 只允许 `http://127.0.0.1:8765/*` |
| Provider 没配置 | `Not configured`（Test Connection 后）/ `LLM provider is not configured` | 在 Settings 填 Provider + API Key 并 **Save**，然后完成人工批准 |
| API Key 错误（HTTP 401/403） | `Invalid API key` | 重新粘贴 Key 并 Save；旧 Key 用 **Forget stored key** 删除（同样需要批准） |
| 触发限流（HTTP 429） | `Rate limit reached` | 等待后重试，或换用更低配额消耗的模型。系统**不会**自动重试 |
| Provider 服务异常（HTTP 5xx） | `Provider unavailable` | 稍后重试或切换 Provider；这是上游故障，不是本机配置问题 |
| 流式输出中断 / 用户点了 Stop | `Streaming stopped` / `Streaming stopped or interrupted` | 已产出的内容保留，界面停在安全状态。需要继续时**由你**再发一条消息——系统绝不自动重发 |
| Provider 拒绝请求（其他 4xx） | `Provider rejected the request` | 检查 Model 名称是否属于该 Provider（见 [`CONFIG.md`](CONFIG.md)） |
| 面板不出现 | — | 确认在 `https://chatgpt.com/` 或 `https://chat.openai.com/`；这是 `content_scripts.matches` 的全部范围 |
| Load unpacked 报 manifest 错误 | — | 你选错了目录层级：必须选**直接包含 `manifest.json`** 的目录 |

## 4. 这个包里有什么 / 没有什么

ZIP 里 **只有** 三个运行时文件：

```text
manifest.json
content/content.js
background/service-worker.js
```

ZIP 里**没有**：`.env`、API Key、任何 Secret、SQLite 数据库、workspace 数据、
测试文件、TypeScript 源码、Source Map、开发配置（`vite.config.ts` / `tsconfig.json` /
`package.json`）、调试日志。这一点由 `release/build-release.sh` 在打包前后各审计一次，
并由 `local-bridge/tests/test_phase33_release.py` 在测试里复用同一套规则再验证一遍。

扩展申请的权限是最小集：`permissions: ["storage", "scripting"]`，
`host_permissions` 只有 `https://chatgpt.com/*`、`https://chat.openai.com/*`、
`http://127.0.0.1:8765/*`。**没有 `<all_urls>`**，没有任何通配主机。

## 5. 边界

- 扩展**不执行**任何命令，没有 Shell / Terminal / Run / Execute / Apply / Auto Fix 控件。
- 模型返回的 Tool Call 只作为 **Tool Proposal** 展示（Developer Mode 才显示），
  状态恒为 `Waiting Approval`，`toolCallsExecuted` 恒为 `false`。
- 任何写入（Provider 配置、Key 删除、偏好修改、文件改动）都返回 202 pending，
  必须由人在 ApprovalStore 里批准。
- Web Context 只在你点击 **Ask AI** 时采集，**采集 ≠ 发送**，且只随你的下一条消息
  发送一次；没有后台抓取，没有自动上传。
