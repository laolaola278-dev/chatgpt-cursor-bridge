# Phase 2: Browser Extension

## 概述

Phase 2 实现了 Chrome/Edge Manifest V3 浏览器扩展，负责在 ChatGPT 网页中注入 UI 并捕获 GPT 输出中的 `<action>` 指令。

## 核心功能

- **内容脚本注入**：在 ChatGPT 页面中注入交互 UI
- **Action 解析**：捕获 GPT 输出的 `<action>` 指令
- **审批面板**：展示待审批操作列表
- **本地通信**：与 Local Bridge 通过 HTTP 通信

## 技术栈

- TypeScript + Vite + Vitest
- Chrome Manifest V3
- 权限：`storage`、`scripting`
- 主机权限：`chatgpt.com`、`chat.openai.com`、`127.0.0.1:8765`

## 参考实现

- [`browser-extension/manifest.json`](../browser-extension/manifest.json) — 扩展配置
- [`browser-extension/src/content/`](../browser-extension/src/content/) — 内容脚本
- [`browser-extension/src/bridge/`](../browser-extension/src/bridge/) — 桥接通信
