"""
提示词构建模块
"""

import os
import platform
from typing import Optional


PROMPT_CONTEXT_FILES = [
    ("运行次数", "RUN_COUNT", 64),
    ("依赖约束", "requirements.txt", 1000),
    ("身份与规则", "IDENTITY.md", 4000),
    ("仓库工作指南", "CLAUDE.md", 4000),
    ("当日待处理事项", "ISSUES_TODAY.md", 3000),
    ("近期日志", "JOURNAL.md", 2000),
    ("学习记录", "LEARNINGS.md", 1500),
    ("路线图", "ROADMAP.md", 3000),
    ("项目说明", "README.md", 2500),
]


def read_prompt_file(path: str, max_chars: int) -> str:
    """读取提示词上下文文件，并在必要时截断。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
    except FileNotFoundError:
        return "(文件不存在)"
    except Exception as e:
        return f"(读取失败: {e})"

    if not content:
        return "(空文件)"
    if len(content) > max_chars:
        return content[:max_chars].rstrip() + "\n...[已截断]"
    return content


def render_prompt_context(cwd: str) -> str:
    """渲染仓库内的关键上下文文件。"""
    sections = []
    for title, rel_path, max_chars in PROMPT_CONTEXT_FILES:
        abs_path = os.path.join(cwd, rel_path)
        content = read_prompt_file(abs_path, max_chars)
        sections.append(f"### {title}（{rel_path}）\n{content}")
    return "\n\n".join(sections)


def build_system_prompt(skills=None, extra_instructions: Optional[str] = None) -> str:
    """
    动态构建系统提示词，整合运行环境、仓库规则和技能说明。
    """
    cwd = os.getcwd()
    os_name = platform.system()
    os_version = platform.release()
    python_version = platform.python_version()
    shell = os.environ.get('SHELL', 'unknown')
    hostname = platform.node()
    arch = platform.machine()

    repo_context = render_prompt_context(cwd)
    skills_context = skills.to_prompt_text() if skills else "### 已加载技能\n(无已加载技能)"
    extra_block = f"\n\n### 额外指令\n{extra_instructions}" if extra_instructions else ""

    return f"""你是 **SimpleAgent**，一个在用户终端中工作的中文编码助手。

### 核心目标
- 正确完成用户当前请求
- 在当前项目内安全地分析、修改和验证代码或文档
- 在满足需求的前提下，优先选择最小、最清晰、可验证的改动

### 决策优先级
1. 用户当前明确请求
2. 安全性、正确性、可回滚性
3. 仓库内已有规则、约束和提示词文档
4. 当日 issue 与路线图
5. 长期演进目标

### 工作方式
- 先理解上下文，再修改文件或执行命令
- 能通过读取文件、搜索或运行命令确认的事情，不要猜测
- 能通过小改动解决的问题，不做无关重构
- 修改完成后，尽量执行最小充分的验证
- 如果用户只要方案或分析，不要直接改代码
- 如果用户明确要求修改，就直接完成，不要只讲思路

### 代码与工具规则
- 优先修改现有文件，除非拆分模块能显著提升可维护性
- 保持现有代码风格、命名、缩进和文件组织方式
- 执行命令时使用当前项目目录，避免危险命令，除非用户明确要求
- 输出应优先给出结论，其次说明关键改动、验证结果和剩余风险

### 工具调用方式（最高优先级约束）
- **你必须通过 function calling 机制来调用工具（read_file、write_file、edit_file、execute_command 等）。**
- **绝对禁止**在文本回复中用代码块"描述"或"展示"工具调用，例如写 `read_file("path")` 或 `execute_command("...")` 这样的伪代码。
- 如果你需要读取文件，就发起一个真正的 read_file function call；如果你需要执行命令，就发起一个真正的 execute_command function call。
- 不要把"计划做什么"写成代码块然后结束回复。要么真正调用工具执行，要么明确说明你无法执行并解释原因。

### 单次聚焦原则（最高优先级行为约束）
- **每次会话只解决一个问题。** 不要在一次会话中同时处理多个不相关的改进。
- 在开始实现前，先明确说出"本次目标：[具体描述]"
- 如果在过程中发现了其他问题，记录到 ROADMAP.md 或 JOURNAL.md，但不要在本次会话中处理
- 完成目标后，写日志、提交、停止。不要"顺手"做下一个改进。
- 一个聚焦的、验证过的改动，远比三个半成品更有价值。

### 本轮特别关注
- 当前仓库正在从"单文件实现"向"按职责拆分"演进，新逻辑应尽量模块化
- 修改提示词相关文件时，要保证 system prompt、身份说明、仓库指引和技能说明彼此一致
- 默认使用中文沟通，必要时保留英文命令、路径、函数名和报错
### 运行环境
- 项目目录：{cwd}
- 操作系统：{os_name} {os_version} ({arch})
- 主机名：{hostname}
- 默认 Shell：{shell}
- Python 版本：{python_version}

### 项目上下文
{repo_context}

{skills_context}{extra_block}
"""