# Phase 5: Engineering Workflow

## 概述

Phase 5 实现了完整的工程工作流编排，让 ChatGPT 从单次 Action 执行升级为完整开发流程编排。核心原则是 human-in-the-loop。

## 阶段管线

```
REQUIREMENT -> ANALYSIS -> ARCHITECTURE -> IMPLEMENTATION -> TESTING -> DEBUG -> DELIVERY
```

## 工作流状态

```
CREATED -> ANALYZING -> DESIGNING -> WAITING_APPROVAL -> IMPLEMENTING -> TESTING -> COMPLETED
   |           |            |                       |                  |              |
   +-----------+------------+-----------------------+------------------+--------------+
                                                              CANCELLED / FAILED
```

## 报告契约

每个 stage 的报告必须包含指定 `##` 小节：

| Stage | 必填小节 |
|-------|---------|
| REQUIREMENT | Goal、Scope、Constraints |
| ANALYSIS | Findings、Risks、Assumptions |
| ARCHITECTURE | Technology、Modules、Risks、Trade-offs |
| IMPLEMENTATION | Summary、Files Touched、Follow-ups |
| TESTING | Coverage、Results、Gaps |
| DEBUG | Symptom、Root Cause、Fix |
| DELIVERY | Outcome、Artifacts、Next Steps |

## 参考实现

- [`local-bridge/app/workflow/`](../local-bridge/app/workflow/) — 工作流模块
