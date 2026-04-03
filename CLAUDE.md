# CLAUDE.md

本文件为在此代码库中工作的编码Agent提供仓库级指导。

## 项目简介

`SimpleAgent` 是一个基于 Python 实现的自进化编码Agent CLI。
它运行在终端中，能够读取项目上下文、调用工具、修改文件、执行验证，并在持续演进过程中逐步提升自己的能力。

当前项目的一个重要方向是：**优化整个提示词系统，而不是只修改单条 system prompt。**
提示词体系由以下几层组成：

1. **运行时 system prompt**：由 `src/main.py` 动态生成
2. **身份层**：`IDENTITY.md`
3. **仓库工作说明层**：本文件 `CLAUDE.md`
4. **技能层**：`skills/*/SKILL.md`
5. **状态上下文层**：`RUN_COUNT`、`ISSUES_TODAY.md`、`ROADMAP.md`、`JOURNAL.md`、`LEARNINGS.md`、`README.md`

## 当前架构

### 1. 运行入口

- `main.py`：主入口包装
- `src/main.py`：核心 Agent 实现

### 2. Prompt 装配逻辑

`src/main.py` 中会在运行时动态构建 system prompt，自动整合：
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
python main.py --model Pro/zai-org/GLM-5 --skills ./skills
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
  - `src/main.py` 中的 `build_system_prompt()`
  - `IDENTITY.md`
  - `CLAUDE.md`
  - `skills/*/SKILL.md`

## 当前演进重点

根据 `ISSUES_TODAY.md` 与 `ROADMAP.md`，当前重点包括：
- 提升提示词质量和一致性
- 将单文件逻辑逐步按职责拆分
- 提升验证、恢复和错误处理能力
- 让 Agent 更像真实可用的开发工具，而不是演示脚本
