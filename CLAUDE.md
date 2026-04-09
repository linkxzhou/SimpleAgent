# CLAUDE.md

本文件为在此代码库中工作的编码Agent提供仓库级指导。

## 项目简介

`SimpleAgent` 是一个基于 Python 实现的自进化编码Agent CLI。
它运行在终端中，能够读取项目上下文、调用工具、修改文件、执行验证，并在持续演进过程中逐步提升自己的能力。

当前项目的一个重要方向是：**优化整个提示词系统，而不是只修改单条 system prompt。**
提示词体系由以下几层组成：

1. **运行时 system prompt**：由 `src/prompt.py` 动态生成
2. **身份层**：`IDENTITY.md`
3. **仓库工作说明层**：本文件 `CLAUDE.md`
4. **技能层**：`skills/*/SKILL.md`
5. **状态上下文层**：`RUN_COUNT`、`ISSUES_TODAY.md`、`ROADMAP.md`、`JOURNAL.md`、`LEARNINGS.md`、`README.md`

## 当前架构

### 1. 运行入口与模块结构

- `main.py`：项目根目录入口脚本，直接运行 Agent
- `src/main.py`：包内入口，汇总导出所有模块符号，保持向后兼容
- `src/colors.py`：ANSI 终端颜色常量
- `src/models.py`：数据类（`ToolCallRequest`、`Usage`）
- `src/tools.py`：`ToolExecutor` 工具执行器 + `TOOL_DEFINITIONS` 工具定义
- `src/skills.py`：`Skill` / `SkillSet` 技能加载与管理
- `src/prompt.py`：提示词上下文渲染与 `build_system_prompt()` 动态构建
- `src/git.py`：Git 感知（分支检测、仓库状态）
- `src/providers.py`：`ProviderConfig` 提供商配置数据类 + 内置提供商注册表 + `resolve_provider()` 配置合并
- `src/logger.py`：`SessionLogger` 会话日志记录（JSONL 格式交互历史）
- `src/mcp_client.py`：`MCPClient` MCP 客户端（stdio transport 连接、工具发现、OpenAI 格式转换、代理调用）
- `src/memory.py`：`MemoryManager` 三层记忆管理（短期/中期 WorkingSummary/长期 Archival，Anchored Iterative Summarization）
- `src/router.py`：`ModelRouter` LLM 路由器（三级模型选择：HIGH/MIDDLE/LOW，基于任务复杂度自动路由）
- `src/agent.py`：`Agent` 核心类（对话循环、工具调用分发、LLM 交互、会话持久化、路由集成）
- `src/cli.py`：CLI / REPL 交互界面（参数解析、事件渲染、路由状态显示、`main()`）

### 2. Prompt 装配逻辑

`src/prompt.py` 中会在运行时动态构建 system prompt，自动整合：
- 当前项目目录
- 操作系统 / Shell / Python 版本
- 仓库中的关键文档
- 当前已加载的技能内容

这意味着：
- 修改 `IDENTITY.md`、`CLAUDE.md`、`ROADMAP.md`、`ISSUES_TODAY.md` 等文件，会直接影响模型的运行时上下文
- 修改 `skills/*/SKILL.md`，会影响任务型工作流
- 优化提示词时应关注“整体一致性”，而不是局部润色

### 3. 工具调用模型

当前 Agent 使用 **OpenAI function calling** 风格的工具调用：
- `read_file`
- `write_file`
- `edit_file`
- `list_files`
- `execute_command`
- `search_files`
- `web_search`（使用 DuckDuckGo 搜索网络内容，无需 API Key）

Agent 会执行如下循环：
1. 发送用户消息与 system prompt
2. 接收模型输出及 `tool_calls`
3. 执行工具
4. 将工具结果作为 `tool` 消息回传
5. 继续生成最终答案

### 4. 技能系统

`--skills ./skills` 会加载 `skills/` 目录下的技能。
每个技能由一个 `SKILL.md` 描述其：
- 目标
- 规则
- 执行步骤
- 输出格式

当前包含的技能：
- `self-assess`：自我评估
- `evolve`：安全演进
- `communicate`：日志与 issue 回复
- `last30days`：研究最近 30 天的前沿趋势（Reddit + X + Web）
- `code-simplifier`：代码简化与重构

## 构建与验证命令

```bash
python -m pytest
python -m flake8 .
python -m black --check .
python -m black .
```

如无特殊说明：
- 修改代码后至少运行与改动直接相关的最小验证
- 若改动涉及核心流程，优先运行 `python -m pytest`
- 不要声称“已验证”，除非真的执行了验证

## 交互运行

```bash
source .env
python main.py
python main.py --model DeepSeek-V3_2-Online-32k --skills ./skills
```

## 进化循环

```bash
source .env
./scripts/evolve.sh
```

进化循环大致包括：
1. 准备运行环境
2. 汇总 issue / 日志 / 路线图等上下文
3. 启动 Agent 执行一个聚焦改进
4. 运行验证
5. 成功则提交，失败则回滚或记录

## 状态文件

- `IDENTITY.md`：身份、原则、长期目标
- `CLAUDE.md`：仓库级工作说明
- `JOURNAL.md`：每日 / 每次演进日志
- `ROADMAP.md`：改进路线图
- `LEARNINGS.md`：学习记录与外部知识摘要
- `RUN_COUNT`：当前运行次数
- `ISSUES_TODAY.md`：当天待处理 issue
- `ISSUE_RESPONSE.md`：issue 回复输出

## 重要约束

- 优先满足用户当前请求
- 默认使用中文沟通
- 尽量做最小、清晰、可验证的改动
- 优先修改现有文件，而不是无关扩张
- 当提示词相关文件发生变化时，要检查以下内容是否仍一致：
  - `src/prompt.py` 中的 `build_system_prompt()`
  - `IDENTITY.md`
  - `CLAUDE.md`
  - `skills/*/SKILL.md`

## 当前演进重点

根据 `ISSUES_TODAY.md` 与 `ROADMAP.md`，当前重点包括：
- 级别 4 全部完成 ✅，进入终极挑战阶段
- 终极挑战：SWE-bench Lite、Terminal-bench、单提示词构建完整项目、重构真实开源项目
- 持续提升端到端可靠性和长对话稳定性
- 让 Agent 更像真实可用的开发工具，而不是演示脚本
