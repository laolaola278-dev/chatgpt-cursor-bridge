# AI Assistant · Provider 配置指南（Phase 33 Release）

配置入口：ChatGPT 页面右侧面板 → **Provider Settings**。
需要填四项：**Provider**、**Model**、**API Key**、**Base URL**（可留空用默认端点）。

> 本文件不包含任何真实 API Key。示例里的 Key 一律写成占位符，
> 请勿把真实 Key 写进文档、截图、Issue、测试快照或提交记录。

## 1. API Key 的处理方式（最重要的一节）

你粘贴的 API Key：

- **不会**保存在 Extension 的内部状态（`ExtensionState`）里；
- **不会**写入 `chrome.storage`，也不写 `localStorage` / `sessionStorage`；
- **不会**写进任何日志（浏览器 Console、Bridge 终端、`audit.jsonl` 都没有）；
- **不会**出现在 URL、Query String 或 Path 里（只走 POST body）；
- **不会**被返回给 Chat、Response、Context、Export 或任何界面文案；
- **只**作为 Settings 密码框的瞬时值存在，点击 **Save** / **Test Connection**
  后输入框立刻被清空。

Backend 侧使用**加密存储**：Key 一进 Bridge 就用 **AES-256-GCM** 加密后落盘，
界面上只能看到掩码尾巴（例如 `****cdef`）和指纹，永远拿不回明文。

固定链路：

```text
Settings 密码框（瞬时值）
  ↓ POST /provider/config （body，不是 URL）
Local Bridge
  ↓ AES-256-GCM
Encrypted Credential Store
  ↓ 仅在发请求那一刻解密
Authorization: Bearer …（只存在于对 Provider 的出站请求头里）
```

Extension 侧还有一道兜底：`browser-extension/src/state/store.ts` 会在
`update()` 与 `hydrate()` 两处剥掉任何键名含
`apikey` / `api_key` / `secret` / `authorization` / `credential` / `bearer` /
`token` / `password` 的字段，所以即使将来有人误传，也进不了持久化状态。

写入是审批动作：`POST /provider/config` 与 `POST /provider/forget` 都返回
**202 pending**，需要人工在 ApprovalStore 里批准后才生效。明文 Key 在加密那一步
就被消费掉了，**不会**进入审批载荷、审计日志或任何响应体。

## 2. OpenAI

| 字段 | 值 |
|---|---|
| Provider | `openai` |
| Model | `gpt-5` / `gpt-5-mini` / `gpt-4o` / `gpt-4.1` / `gpt-4-turbo` |
| API Key | 你在 OpenAI 控制台生成的 Key（形如 `sk-…`，本文不给真实值） |
| Base URL | 留空即用 `https://api.openai.com/v1`；自建代理时填你的地址 |
| 环境变量（可选） | `OPENAI_API_KEY` |

## 3. Anthropic

| 字段 | 值 |
|---|---|
| Provider | `anthropic` |
| Model | `claude-4-sonnet` / `claude-3-7-sonnet` / `claude-3-5-sonnet` / `claude-3-5-haiku` |
| API Key | Anthropic Console 生成的 Key |
| Base URL | 留空即用 `https://api.anthropic.com/v1` |
| 环境变量（可选） | `ANTHROPIC_API_KEY` |

## 4. DeepSeek

| 字段 | 值 |
|---|---|
| Provider | `deepseek` |
| Model | `deepseek-chat` / `deepseek-reasoner` |
| API Key | DeepSeek 平台生成的 Key |
| Base URL | 留空即用 `https://api.deepseek.com` |
| 环境变量（可选） | `DEEPSEEK_API_KEY` |

## 5. local（离线模拟，不需要 Key）

| 字段 | 值 |
|---|---|
| Provider | `local` |
| Model | `local/simulator-v1` / `local/architect-v1` |
| API Key | 不需要 |

`local` 是默认 Provider，用于在完全不联网、不配置任何 Key 的情况下验证安装是否成功。
它的回复带 `simulated: true`。

## 6. 环境变量 vs 加密存储

两种来源，加密存储优先：

1. **加密存储**（推荐）：Settings 里保存 → AES-256-GCM 落盘 → 人工批准后生效。
2. **环境变量**：启动 Bridge 前 `export OPENAI_API_KEY=…`。适合 CI 或临时验证。

不要把 Key 写进仓库里的 `.env` 并提交——Release 审计会把 `.env`
和"值形态"的 Key 赋值当成 finding 直接让构建失败。

## 7. Test Connection 的返回文案

`POST /provider/test` 只会返回固定词表中的一项，绝不返回 Provider 原始错误、
stack trace、内部路径、Key 或 Authorization Header：

| 状态 | 文案 | 含义 |
|---|---|---|
| `connected` | `Connected` | Key 可用，模型可访问 |
| `not_configured` | `Not configured` | 还没有可用的 Key |
| `failed` | `Invalid API key` | Provider 返回 401 / 403 |
| `failed` | `Rate limit reached` | Provider 返回 429 |
| `failed` | `Provider unavailable` | Provider 返回 5xx 或其他上游故障 |
| `failed` | `Backend unreachable` | 连不上 Provider 或连不上 Bridge |
| `failed` | `Provider rejected the request` | 其他 4xx（例如模型名不属于该 Provider） |

Settings 里的 Provider 列表同时展示每个 Provider 的
`Connected` / `Not configured` / `Failed`，以及"是否存了 Key"的掩码提示。

## 8. 删除已存的 Key

Settings → **Forget stored key**。这同样是审批动作（202 pending），
批准后加密记录被删除。删除不会影响环境变量来源的 Key。

## 9. 相关端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/user/settings` | GET | 非敏感设置（模式、Provider、Model、Surface 列表） |
| `/provider/status` | GET | 各 Provider 状态 + 可选模型，无 Key |
| `/provider/test` | POST | 连接测试，返回固定安全词表 |
| `/provider/config` | POST | 保存 Provider 配置，**202 pending** |
| `/provider/forget` | POST | 删除已存 Key，**202 pending** |
| `/user/settings` | POST | 更新非敏感偏好，**202 pending** |
| `/context/status` | GET | Context 能力标志（不含任何内容） |
| `/assistant/chat` | POST | 一次性对话 |
| `/assistant/chat/stream` | POST | 流式对话（SSE） |

安装步骤见 [`INSTALL.md`](INSTALL.md)。
