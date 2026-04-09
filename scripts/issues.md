<!-- 
  issues.md — Issue 列表模板
  
  使用说明：
  - 每个 issue 以 "### Issue #编号: 标题" 开头
  - 可选字段：优先级（高/中/低）、标签（逗号分隔）、状态（待处理/已完成）
  - issue 描述写在元数据下方
  - 每个 issue 之间用 "---" 分隔
  - 脚本 format_issues.py 会自动解析此文件，已完成的 issue 会被过滤
  
  优先级说明：
  - 高：紧急问题，需要立即处理（崩溃、数据丢失等）
  - 中：重要改进，应尽快处理
  - 低：优化建议，有空时处理

  状态说明：
  - 待处理（默认）：尚未开始或进行中
  - 已完成：已解决，格式化输出时会被自动过滤
-->

### Issue #1: 将逻辑拆分为独立的文件，不应该放到一个文件中
状态: 已完成
优先级: 高
标签: 单一原则

按照单一原则，将逻辑拆分为独立的文件，不应该将逻辑全部放到一个文件中

### Issue #2: 增加 `web_fetch` 的功能
状态: 已完成
优先级: 高
标签: 网络

增加 `web_fetch` 的功能，支持网络访问，不要依赖 key，推荐用duckduckgo 相关的库

### Issue #3: 增加了 `last30days` skill，关注 Agent 前沿的发展方向
状态: 已完成
优先级: 低
标签: skill

增加了 `last30days` skill，作用是关注最近 30 天的相关主题的前沿或者论文的发展方向，可以通过当前 skill 规划后续迭代的 ROADMAP

### Issue #4: 当前上下文压缩是个最大的问题，如何解决？
状态: 已完成
优先级: 高
标签: 上下文压缩

使用 `last30days` skill，找到最近的前沿相关主题，实现长，中，短的记忆分层来优化问题。

### Issue #5: 给模型增加路由的功能，分为OPENAI_MODEL_MIDDLE，OPENAI_MODEL_LOW，OPENAI_MODEL
状态: 已完成
优先级: 高
标签: LLMRouter

- 简单任务使用OPENAI_MODEL_LOW实现
- 中等任务使用OPENAI_MODEL_MIDDLE实现
- 复杂任务使用OPENAI_MODEL实现
- 使用 `last30days` skill，找到最近的前沿相关主题

### Issue #6: 增加 SubAgent 的功能，考虑 Agent 之间上下文共享或者独立的问题
状态: 已完成
优先级: 高
标签: SubAgent

- 使用 `last30days` skill，找到最近的前沿相关主题
- 增加 SubAgent，需要考虑 Agent 之间上下文传递的问题
- 需要考虑哪些上下文共享，哪些上下文独立
- **完成日期：第 68 次（2026-04-08）**
- **实现：** Orchestrator-Worker + Context Lake 架构，delegate_task() 任务委派，Context Isolation 上下文隔离

### Issue #7: 增加 Team 协作的功能，类似 OpenSwarm
状态: 未完成
优先级: 高
标签: Team Agent

- 使用 `last30days` skill，找到最近的前沿相关主题
- 增加 Team 协作的功能，参考 OpenSwarm
- 需要考虑 Team Leader，Team SubAgentXXX 等

### Issue #8: 使用 `code-simplifier` 优化代码
状态: 未完成
优先级: 高
标签: Code Review

- 使用 `code-simplifier` 优化代码
- 每个代码文件不超过 500 行，超过进行拆分

<!--
  === 空白模板（复制使用） ===

### Issue #N: 标题
状态: 待处理
优先级: 高/中/低
标签: tag1, tag2

issue 描述内容...

---
-->
