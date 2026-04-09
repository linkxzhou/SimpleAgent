"""提示词构建模块 - 动态构建系统提示词，整合运行环境、仓库上下文和技能说明。"""

import os
import sys
import platform
from typing import Optional, Dict, List, Tuple

from .skills import SkillSet
from .git import is_git_repo, get_git_branch


# 截断警告阈值：文件实际大小超过 max_chars 的此比例时发出警告
_TRUNCATION_WARN_RATIO = 0.85


# 需要注入到 system prompt 中的仓库上下文文件
# 格式：(标题, 文件路径, 最大字符数, 倒序截断)
# reverse=True 时取文件尾部内容（适用于不断追加的日志型文件）
PROMPT_CONTEXT_FILES = [
    ("运行次数", "RUN_COUNT", 64, False),
    ("依赖约束", "requirements.txt", 1000, False),
    ("身份与规则", "IDENTITY.md", 4000, False),
    ("仓库工作指南", "CLAUDE.md", 6000, False),
    ("当日待处理事项", "ISSUES_TODAY.md", 3000, False),
    ("近期日志", "JOURNAL.md", 4000, False),
    ("学习记录", "LEARNINGS.md", 4000, True),
    ("路线图", "ROADMAP.md", 6000, False),
    ("项目说明", "README.md", 8000, False),
]


def read_prompt_file(path: str, max_chars: int, reverse: bool = False) -> str:
    """读取提示词上下文文件，并在必要时截断。
    
    Args:
        path: 文件路径
        max_chars: 最大字符数
        reverse: 为 True 时取文件尾部内容（倒序截断），适用于日志型文件
    """
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
        if reverse:
            # 取尾部内容，在换行处切断以避免截断段落中间
            tail = content[-(max_chars):]
            newline_pos = tail.find('\n')
            if newline_pos != -1 and newline_pos < len(tail) - 1:
                tail = tail[newline_pos + 1:]
            return "...[前文已截断]\n" + tail
        else:
            return content[:max_chars].rstrip() + "\n...[已截断]"
    return content


def check_context_truncation(cwd: str) -> List[Tuple[str, str, int, int, float]]:
    """检测上下文文件截断状况，返回需要警告的条目列表。
    
    对每个 PROMPT_CONTEXT_FILES 中的文件，比较实际大小与 max_chars：
    - 已超限（actual > max_chars）：返回该文件信息，可见率 < 100%
    - 接近超限（actual > max_chars * _TRUNCATION_WARN_RATIO）：同样返回警告
    
    Args:
        cwd: 项目根目录路径
    
    Returns:
        [(title, rel_path, max_chars, actual_chars, visible_pct), ...]
        仅包含需要警告的文件，空列表表示全部正常。
    """
    warnings = []
    threshold = _TRUNCATION_WARN_RATIO
    for title, rel_path, max_chars, _reverse in PROMPT_CONTEXT_FILES:
        abs_path = os.path.join(cwd, rel_path)
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                actual = len(f.read().strip())
        except (FileNotFoundError, OSError):
            continue  # 文件不存在或无法读取，不是截断问题
        if actual == 0:
            continue
        if actual > max_chars * threshold:
            visible_pct = round(min(max_chars / actual, 1.0) * 100, 1)
            warnings.append((title, rel_path, max_chars, actual, visible_pct))
    return warnings


def emit_truncation_warnings(cwd: str) -> List[Tuple[str, str, int, int, float]]:
    """检测并向 stderr 输出截断警告。
    
    在 build_system_prompt() 中调用，确保开发者能及时发现文件增长超限。
    
    Returns:
        警告列表（与 check_context_truncation 相同），便于调用方进一步处理。
    """
    warnings = check_context_truncation(cwd)
    for title, rel_path, max_chars, actual, visible_pct in warnings:
        if visible_pct < 100:
            level = "⚠️  已超限"
            detail = f"可见率 {visible_pct}%，丢失 {actual - max_chars} 字符"
        else:
            level = "⚡ 接近上限"
            headroom = max_chars - actual
            detail = f"仅剩 {headroom} 字符余量"
        print(
            f"[prompt 截断警告] {level}: {rel_path}（{title}）"
            f" — 实际 {actual} vs 上限 {max_chars}，{detail}",
            file=sys.stderr,
        )
    return warnings


def render_prompt_context(cwd: str) -> str:
    """渲染仓库内的关键上下文文件。"""
    sections = []
    for title, rel_path, max_chars, reverse in PROMPT_CONTEXT_FILES:
        abs_path = os.path.join(cwd, rel_path)
        content = read_prompt_file(abs_path, max_chars, reverse=reverse)
        sections.append(f"### {title}（{rel_path}）\n{content}")
    return "\n\n".join(sections)


# 项目标志文件 → (语言, 包管理器, 测试框架)
_PROJECT_MARKERS = [
    # Python
    ("requirements.txt", "Python", "pip", None),
    ("pyproject.toml", "Python", None, None),
    ("setup.py", "Python", None, None),
    ("setup.cfg", "Python", None, None),
    ("Pipfile", "Python", "pipenv", None),
    ("poetry.lock", "Python", "poetry", None),
    ("pytest.ini", None, None, "pytest"),
    ("tox.ini", None, None, "tox"),
    (".pytest_cache", None, None, "pytest"),
    # Node.js
    ("package.json", "Node.js", "npm", None),
    ("yarn.lock", "Node.js", "yarn", None),
    ("pnpm-lock.yaml", "Node.js", "pnpm", None),
    # Rust
    ("Cargo.toml", "Rust", "cargo", None),
    # Go
    ("go.mod", "Go", "go", None),
    # Java / Kotlin
    ("pom.xml", "Java", "maven", None),
    ("build.gradle", "Java/Kotlin", "gradle", None),
    ("build.gradle.kts", "Kotlin", "gradle", None),
    # Build tools
    ("Makefile", None, None, None),
    ("Dockerfile", None, None, None),
    ("docker-compose.yml", None, None, None),
    ("docker-compose.yaml", None, None, None),
]

# 特殊文件 → build_tools 映射
_BUILD_TOOL_MARKERS = {
    "Makefile": "make",
    "Dockerfile": "docker",
    "docker-compose.yml": "docker-compose",
    "docker-compose.yaml": "docker-compose",
}


def detect_project_info(cwd: str) -> Dict[str, List[str]]:
    """检测项目类型、语言、包管理器和测试框架。
    
    通过检查项目根目录中的标志文件来推断项目信息。
    不执行任何命令，仅读取文件系统。
    
    Args:
        cwd: 项目根目录路径
    
    Returns:
        {"languages": [...], "package_managers": [...], 
         "test_frameworks": [...], "build_tools": [...]}
    """
    languages = []
    package_managers = []
    test_frameworks = []
    build_tools = []
    
    for filename, lang, pkg_mgr, test_fw in _PROJECT_MARKERS:
        if os.path.exists(os.path.join(cwd, filename)):
            if lang and lang not in languages:
                languages.append(lang)
            if pkg_mgr and pkg_mgr not in package_managers:
                package_managers.append(pkg_mgr)
            if test_fw and test_fw not in test_frameworks:
                test_frameworks.append(test_fw)
            # build tools
            if filename in _BUILD_TOOL_MARKERS:
                tool = _BUILD_TOOL_MARKERS[filename]
                if tool not in build_tools:
                    build_tools.append(tool)
    
    return {
        "languages": languages,
        "package_managers": package_managers,
        "test_frameworks": test_frameworks,
        "build_tools": build_tools,
    }


def _format_project_info(info: Dict[str, List[str]]) -> str:
    """将项目检测结果格式化为 system prompt 中可读的文本。"""
    parts = []
    if info["languages"]:
        parts.append(f"语言：{', '.join(info['languages'])}")
    if info["package_managers"]:
        parts.append(f"包管理：{', '.join(info['package_managers'])}")
    if info["test_frameworks"]:
        parts.append(f"测试框架：{', '.join(info['test_frameworks'])}")
    if info["build_tools"]:
        parts.append(f"构建工具：{', '.join(info['build_tools'])}")
    if not parts:
        return ""
    return "\n- ".join([""] + parts)  # 每项前加 "\n- " 前缀


def build_system_prompt(skills: Optional[SkillSet] = None, extra_instructions: Optional[str] = None, archival_context: Optional[str] = None) -> str:
    """动态构建系统提示词，整合运行环境、仓库规则和技能说明。"""
    cwd = os.getcwd()
    os_name = platform.system()
    os_version = platform.release()
    python_version = platform.python_version()
    shell = os.environ.get('SHELL', 'unknown')
    hostname = platform.node()
    arch = platform.machine()

    # 截断警告：检测文件超限并输出 stderr 提醒
    emit_truncation_warnings(cwd)

    repo_context = render_prompt_context(cwd)
    skills_context = skills.to_prompt_text() if skills else "### 已加载技能\n(无已加载技能)"
    extra_block = f"\n\n### 额外指令\n{extra_instructions}" if extra_instructions else ""

    # Git 感知
    git_line = ""
    if is_git_repo(cwd):
        branch = get_git_branch(cwd)
        if branch:
            git_line = f"\n- Git 分支：{branch}"
        else:
            git_line = "\n- Git：在仓库中（detached HEAD 或无法获取分支名）"
    else:
        git_line = "\n- Git：不在 Git 仓库中"

    # 项目检测
    project_info = detect_project_info(cwd)
    project_line = _format_project_info(project_info)

    # 长期记忆（archival memory）
    archival_block = ""
    if archival_context:
        archival_block = f"\n\n### 长期记忆（跨会话）\n{archival_context}"

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
- 修改提示词相关文件时，要保证 system prompt、身份说明、仓库指引和技能说明彼此一致
- 默认使用中文沟通，必要时保留英文命令、路径、函数名和报错
### 运行环境
- 项目目录：{cwd}
- 操作系统：{os_name} {os_version} ({arch})
- 主机名：{hostname}
- 默认 Shell：{shell}
- Python 版本：{python_version}{git_line}{project_line}

### 项目上下文
{repo_context}

{skills_context}{extra_block}{archival_block}
"""
