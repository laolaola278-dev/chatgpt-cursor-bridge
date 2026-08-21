# Phase 6: Engineering Toolchain

## 概述

Phase 6 实现了工程工具链，包括 Git 操作、Test Runner、Command Policy 和 Stage Rollback。

## Git

- `/git/status`、`/git/diff` 为 LEVEL_0 只读操作
- `/git/commit` 为 LEVEL_1，要求 `message`、`workflow_id`、`stage_id`
- 全部使用参数数组、`shell=False`，工作目录由项目沙箱解析

## Test Runner

仅允许三个精确命令别名：

| 输入 | 固定 argv |
|------|----------|
| `pytest` | `["pytest"]` |
| `npm test` | `["npm", "test", "--"]` |
| `cmake build` | `["cmake", "--build", "build"]` |

拒绝 `;`、`&&`、`||`、管道、重定向、命令替换、PATH 修改等。

## Stage Rollback

- 绑定 workflow/stage 的文件、Memory、Git commit 在执行前写入快照
- 恢复按执行时间逆序执行
- 已存在文件恢复原始字节，新建文件删除

## 参考实现

- [`local-bridge/app/git/`](../local-bridge/app/git/) — Git 模块
- [`local-bridge/app/test_runner/`](../local-bridge/app/test_runner/) — 测试执行器
- [`local-bridge/app/security/command_policy.py`](../local-bridge/app/security/command_policy.py) — 命令策略
