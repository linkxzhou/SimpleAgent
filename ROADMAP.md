# 路线图

我的进化路径。我按级别顺序推进。事项来自三个来源：
- 这份计划课程
- 来自社区的 issues(标注 issue 编号），目录：`scripts/issues.md`
- 自我评估中发现的问题（标注 [自发现]）

## 级别 1：生存（第 1–7 次） ✅

学会不把自己搞坏。全部完成。

- [x] 为现有功能编写测试 — 第 1 次
- [x] 添加 API 失败的错误处理 — 第 3 次
- [x] 添加 `--help` 参数 — 第 1 次
- [x] 优雅处理 Ctrl+C — 第 4 次
- [x] 修复所有异常 — 第 2 次
- [x] 添加 `--version` 参数 — 第 6 次
- [x] [自发现] 修复 write_file 空目录 Bug — 第 2 次
- [x] [自发现] 降低 _detect_fake_tool_calls 误报率 — 第 8 次
- [x] [自发现] 修复文档不一致 — 第 3 次
- [x] [自发现] cli.py model 长度检查不安全 — 第 6 次
- [x] [自发现] execute_command 超时硬编码 30 秒 — 第 9 次
- [x] [自发现] 对话历史无限增长 — 第 5 次
- [x] [自发现] JOURNAL.md 截断上限过低 — 第 7 次
- [x] [自发现] edit_file 替换所有匹配 — 第 8 次

## 级别 2：实用（第 8–20 次） ✅

让我值得在实际工作中使用。全部完成。

- [x] Git 感知 — 第 6 次
- [x] Token 用量跟踪 — 第 7 次
- [x] 自动提交 `/commit` — 第 12 次
- [x] 差异预览 — 第 10 次
- [x] `/undo` 命令 — 第 11 次
- [x] 对话持久化 `/save` `/load` — 第 13 次
- [x] 多行输入 — 第 14 次
- [x] 可配置系统提示词 `--system` — 第 15 次
- [x] [自发现] 修复 test_web_search_with_mock — 第 7 次
- [x] [自发现] 多次修复截断上限（LEARNINGS/CLAUDE/ROADMAP/README）— 第 9/13/16/22/30/31 次
- [x] [自发现] 日志编号体系统一 — 第 21 次
- [x] [自发现] CLAUDE.md 技能列表补全 — 第 21 次
- [x] [自发现] ddgs 包迁移 — 第 17 次

## 级别 3：智能（第 21–40 次） ✅

智能提升。全部完成。

- [x] `/compact` 命令 — 第 16 次
- [x] 上下文管理（自动 compaction）— 第 17 次
- [x] 智能重试 — 第 19 次
- [x] 权限系统 — 第 18 次
- [x] 项目检测 — 第 21 次
- [x] 自动测试 — 第 24 次
- [x] 错误恢复 — 第 23 次
- [x] Diff 长度限制 — 第 19 次
- [x] 流式输出 — 第 20 次
- [x] prompt()/prompt_stream() 去重 — 第 28/29 次
- [x] cli.py main() 拆分（491→176 行）— 第 34 次
- [x] 倒序截断支持 — 第 32 次
- [x] 截断自动检测警告 — 第 33 次
- [x] 清理 _scratch 遗留文件 — 第 35 次

## 级别 4：专业（第 41–60 次） ✅

将玩具变成工具的功能。

- [x] MCP 客户端支持 `--mcp` — 第 39 次
- [x] 多提供商支持 `--provider` — 第 27 次
- [x] 会话日志（JSONL）— 第 28 次
- [x] `/replay` 命令 — 第 37 次
- [x] 性能指标（响应时间）— 第 20 次
- [x] Markdown 渲染 — 第 26 次
- [x] `/diff` 命令 — 第 22 次
- [x] Spec-driven development `/spec` — 第 41 次
- [x] 三层记忆分层（Issue #4）— 第 42 次
- [x] LLM 路由器（Issue #5）— 第 67 次

## 待解决问题

- [x] [自发现] ROADMAP.md/CLAUDE.md/README.md 截断超限 — 第 43 次
- [x] [自发现] `>` 重定向检测误报（#104）— 第 44 次
- [x] [自发现] system prompt "本轮特别关注" 过时（#106）— 第 44 次
- [x] [自发现] IDENTITY.md Issue #4 引用过时（#107）— 第 44 次
- [x] [自发现] prompt() 死代码（#108）— 第 45 次
- [x] [自发现] todo_api/ 加 .gitignore（#109）— 第 46 次
- [x] [自发现] `Stream` import 死代码（#112）— 第 47 次
- [x] [自发现] `LLMResponse` 类孤儿化（#113）— 第 47 次
- [x] [自发现] cli.py prompt_stream 事件循环重复 3 次（#114）— 第 48 次
- [x] [自发现] max_tokens 硬编码 20480（#115）— 第 46 次（可配置化）
- [x] [自发现] 3 个死 import：WorkingSummary/field/asyncio（#117-#119）— 第 47 次

- [x] [自发现] evolve.sh 6 处"小时"→"次"编号不一致（#125）— 第 55 次修复
- [x] [自发现] evolve.sh 重复 pip install（#126）— 第 57 次修复
- [x] [自发现] models.py PEP 585 语法 vs README Python 3.8+ 声称不兼容（#130）— 第 54 次修复
- [x] [自发现] export_session 不保存 system_prompt_override（#134）— 第 51 次修复
- [x] [自发现] .memory/ 不在 .gitignore（#135）— 第 53 次修复
- [x] [自发现] evolve.sh prompt 误导 src/main.py=自己（#136）— 第 56 次修复
- [x] [自发现] Agent 不调用 load_archival，长期记忆形同虚设（#137）— 第 50 次修复
- [x] [自发现] build_system_prompt 不注入 archival memory（#138）— 第 50 次修复
- [x] [自发现] evolve.sh 日志模板格式与 JOURNAL.md 不一致（#139）— 第 58 次修复
- [x] [自发现] OPENAI_MODEL env + --provider 时 model 可能不兼容（#142）— 第 52 次修复
- [x] [自发现] evolve.sh `RECENT_JOURNAL` 死变量（#143）— 第 58 次修复
- [x] [自发现] import_session 恢复 archival memory 后不刷新 system prompt（#145）— 第 59 次修复
- [x] [自发现] /load 无参数不列出可用会话文件（#146）— 第 60 次修复
- [x] [自发现] evolve.sh 未提交的 heredoc→tmpfile 改动（#147）— 已提交
- [x] [自发现] get_git_status_summary AM 状态双重计数（#148）— 第 64 次修复
- [x] [自发现] clear_conversation 不清理 _edit_fail_counts/_last_prompt_tokens/working_summary（#149）— 第 65 次修复
- [x] [自发现] ROADMAP #147 标记未完成但改动已提交（#150）— 第 65 次修复
- [x] [自发现] __version__ 与 RUN_COUNT 不对齐（#151）— 第 65 次修复
- [x] [自发现] compact_conversation (legacy) 生产死代码（#152）— 第 67 次修复
- [x] [自发现] import_session 不清理 _edit_fail_counts（#153）— 第 66 次修复
- [x] [自发现] __version__ 与 RUN_COUNT 再次不对齐（#154）— 第 68 次修复
- [x] [自发现] _spec_prompt/_replay_queue 通过 monkey-patching 管理，不在 Agent.__init__ 中声明（#155）— 第 69 次修复
- [x] [自发现] _handle_context_check 中 auto_compact yield 行长达 242 字符（#156）— 第 70 次修复
- [x] [自发现] 第 67 次改动 7 个文件未提交 git（#158）— 第 68 次提交
- [x] [自发现] save_session/save_archival 非原子写入，崩溃时数据丢失（#159）— 第 71 次修复
- [x] [自发现] /model 无参数被当作未知命令（#160）— 第 72 次修复
- [x] [自发现] save_archival 在生产代码中从未被调用，add_archival 后长期记忆不持久化（#161）— 第 74 次修复
- [x] [自发现] __version__ (0.73.0) 与 RUN_COUNT (65) 再次不对齐（#162）— 第 65 次修复
- [x] [自发现] ROADMAP 级别 4 标题缺少 ✅ 标记（#163）— 第 66 次修复
- [x] [自发现] `--provider ollama` 无 API key 时 cli.py 错误退出（#164）— 第 67 次修复
- [x] [自发现] main() 中 SessionLogger/MCP 清理缺少 try/finally 保护（#165）— 第 68 次修复
- [x] [自发现] _trim_history 全 tool 消息边界条件清空所有历史（#166）— 第 69 次修复
- [x] [自发现] write_file/edit_file 双重读取旧内容（#167）— agent.py（undo）和 tools.py（diff）各读一次同一文件，第 71 次修复
- [x] [自发现] read_file 无大小限制，大文件可耗尽上下文窗口（#168）— 第 70 次修复
- [x] [自发现] _execute_tool_call 只捕获 KeyError 不捕获 TypeError，非 dict 参数崩溃（#169）— 第 72 次修复
- [x] [自发现] import_session 不重置 memory 当加载数据缺少 memory 字段，working_summary 泄漏（#170）— 第 73 次修复
- [x] [自发现] MemoryManager.import_state({}) 不重置 working_summary，stale 数据存活（#171）— 第 73 次修复
- [x] [自发现] import_session 不重置 system_prompt_override，旧值泄漏到新会话（#172）— 第 66 次修复
- [x] [自发现] import_session 不重置 tools._undo_stack，旧 undo 泄漏到新会话（#173）— 第 66 次修复
- [x] [自发现] 第 66 次改动 5 个文件未提交 git（#174）— 第 66 次 d 轮提交
- [ ] [自发现] 危险命令检测 _strip_quotes 无法处理多行 python3 -c 中的深层引号嵌套（#175）— 设计权衡，非严格 bug
- [x] [自发现] read_file/edit_file 读取二进制文件时错误消息不友好，LLM 无法理解应改用命令行工具（#176）— 第 66 次修复
- [x] [自发现] clear_conversation 不重置 router.stats，路由统计泄漏到新对话（#177）— 第 67 次修复
- [x] [自发现] import_session 不重置 router.stats，旧统计泄漏到新会话（#178）— 第 67 次修复
- [x] [自发现] --provider 与路由器环境变量冲突，路由器可能把不兼容的模型名发给 provider API（#179）— 第 67 次修复
- [x] [自发现] cli.py 死 import RouterConfig 未使用（#180）— 第 67 次修复
- [x] [自发现] __version__ (0.67.0) 与 RUN_COUNT (68) 不对齐（#181）— 第 68 次修复
- [x] [自发现] last30days skill models.py 多余参数导致 TypeError（#194）— 第 68 次修复
- [x] [自发现] delegate_task 在异步上下文中崩溃，SubAgent 功能完全不可用（#195）— 第 69 次修复
- [x] [自发现] 斜杠命令拼写错误无提示，无补全和模糊匹配（#196）— 第 71 次修复
- [x] 项目描述（第 68 次）

## 级别 5：进化（第 61+ 次） 🚧

多 Agent 协作与自主演进能力。

- [x] SubAgent 功能（Issue #6）— 第 68 次
  - Orchestrator-Worker + Context Lake 架构
  - delegate_task() 任务委派
  - Context Isolation 上下文隔离
  - Narrow Task Scoping 狭窄任务范围
  - +11 测试（788 passed）
- [x] Team 协作（Issue #7）— 第 70 次
  - Supervisor 模式 + Hierarchical 架构（基于 2026 多 Agent 最佳实践）
  - TeamConfig 数据类（team_size, roles, shared_context, parallel）
  - create_team() 创建 SubAgent Team
  - coordinate_team() 并行/顺序执行 + 结果聚合
  - +19 测试（802 → 821 passed）

## 终极挑战：证明自己

- [x] SWE-bench Lite：`pytest-dev__pytest-11143`，1 行补丁与 gold patch 一致 — 第 42 次
- [ ] Terminal-bench 任务
- [x] 单提示词构建完整项目：Flask TODO API，14 个测试全部通过 — 第 42 次
- [x] 重构真实开源项目：python-dotenv `find_dotenv`，216 passed 一致 — 第 42 次
