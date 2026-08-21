# Phase 3: Project Memory System

## 概述

Phase 3 实现了项目级长期记忆系统，用于保存项目事实、架构决策和任务状态，不保存聊天记录。

## 记忆结构

每个项目在 `workspace/memory/<project>/` 下独立存储：

```
├ project.md          项目目标、技术栈、约束
├ architecture.md     架构设计、模块关系
├ decisions.md        ADR（追加式）
├ tasks.md            当前任务
├ changelog.md        修改历史
└ memory.db           SQLite 索引（仅元数据）
```

## 操作规则

- **追加语义**：`/memory/append` 只追加，永不覆盖
- **ADR 格式**：title / context / decision / consequence 四字段必填
- **SQLite 索引**：只存元数据，正文保留在 Markdown 中

## 参考实现

- [`local-bridge/app/memory/`](../local-bridge/app/memory/) — 记忆系统模块
