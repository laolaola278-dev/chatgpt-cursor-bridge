# Phase 1: Local Bridge Service

## 概述

Phase 1 实现了 ChatGPT Cursor Bridge 的基础本地桥接服务，提供沙箱化的 workspace 访问、审批保护的写入能力、Patch 应用和审计日志。

## 核心功能

- **文件操作**：受限的 workspace 内文件读写与创建
- **Patch 应用**：统一 diff 格式的补丁应用
- **安全沙箱**：路径隔离、权限分级、CORS 限制
- **审批流**：所有修改操作必须经审批
- **审计日志**：结构化 JSONL 日志记录所有操作

## API 端点

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/health` | LEVEL_0 | 服务健康状态 |
| GET | `/workspace/list` | LEVEL_0 | 列出 workspace 项目 |
| GET | `/project/tree` | LEVEL_0 | 项目文件树 |
| GET | `/file/read` | LEVEL_0 | 读取 UTF-8 文本文件 |
| POST | `/file/write` | LEVEL_1 | 覆盖写入（需审批） |
| POST | `/file/create` | LEVEL_1 | 创建文件（需审批） |
| POST | `/patch/apply` | LEVEL_1 | 应用 unified diff（需审批） |

## 安全机制

- 路径沙箱：拒绝绝对路径、`..` 穿越、空字节
- 权限分级：LEVEL_0（自动）、LEVEL_1（审批）、LEVEL_2（强制审批）
- 审批流：持久化待审批请求，含操作类型、diff 预览、风险等级、TTL

## 参考实现

- [`local-bridge/app/main.py`](../local-bridge/app/main.py) — 服务入口
- [`local-bridge/app/security/`](../local-bridge/app/security/) — 安全模块
- [`local-bridge/app/audit/`](../local-bridge/app/audit/) — 审计日志
