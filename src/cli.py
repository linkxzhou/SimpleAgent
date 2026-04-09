"""CLI / REPL 模块 - 终端交互界面、参数解析和事件渲染。"""

import os
import re
import sys
import time
import asyncio
import argparse
from datetime import datetime
from typing import Optional

from . import __version__
from .colors import RESET, BOLD, DIM, GREEN, YELLOW, CYAN, RED
from .models import Usage
from .tools import default_tools
from .skills import SkillSet
from .agent import Agent
from .git import get_git_branch, git_add_and_commit, git_diff_files
from .providers import resolve_provider, list_providers
from .logger import SessionLogger, load_transcript
from .memory import MemoryManager
from .router import RouterConfig


# 默认模型名称
DEFAULT_MODEL = 'DeepSeek-V3_2-Online-32k'

# 默认会话保存目录
SESSIONS_DIR = 'sessions'

# 默认会话日志目录
LOGS_DIR = 'logs'


def print_banner():
    print(f"\n{BOLD}{CYAN}  SimpleAgent{RESET} {DIM}— a coding agent growing up in public{RESET}")
    print(f"{DIM}  Type /help for commands, /quit to exit{RESET}")
    print(f'{DIM}  Use \"\"\" or \'\'\' to enter multi-line input (paste code blocks){RESET}\n')


def format_diff_lines(diff_text: str) -> list:
    """将 unified diff 文本格式化为带 ANSI 颜色的行列表。
    
    Args:
        diff_text: unified diff 格式的文本
    
    Returns:
        格式化后的字符串行列表（每行带缩进和颜色）
    """
    if not diff_text:
        return []
    lines = []
    for line in diff_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            lines.append(f"{DIM}    {line}{RESET}")
        elif line.startswith("+"):
            lines.append(f"    {GREEN}{line}{RESET}")
        elif line.startswith("-"):
            lines.append(f"    {RED}{line}{RESET}")
        elif line.startswith("@@"):
            lines.append(f"    {CYAN}{line}{RESET}")
        else:
            lines.append(f"{DIM}    {line}{RESET}")
    return lines


def print_usage(usage: Usage, session_usage: Optional[Usage] = None):
    if usage.input > 0 or usage.output > 0:
        line = f"\n{DIM}  tokens: {usage.input} in / {usage.output} out"
        if session_usage and (session_usage.input > 0 or session_usage.output > 0):
            line += f"  (session: {session_usage.input} in / {session_usage.output} out)"
        line += f"{RESET}"
        print(line)


def format_elapsed(seconds: float) -> str:
    """将秒数格式化为人类可读的耗时字符串。

    Examples:
        0.5  -> "0.50s"
        12.3 -> "12.30s"
        75.0 -> "1m 15.00s"
        3661 -> "61m 1.00s"
    """
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    remaining = seconds - minutes * 60
    return f"{minutes}m {remaining:.2f}s"


def truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "…"


def match_command(user_input: str, command: str) -> bool:
    """检查用户输入是否匹配指定的斜杠命令。
    
    精确匹配命令本身，或命令后跟空格（带参数）。
    防止 '/loading' 被当作 '/load'、'/committing' 被当作 '/commit' 等。
    
    Args:
        user_input: 用户输入的文本
        command: 要匹配的命令（如 '/commit'、'/save'、'/load'）
    
    Returns:
        True 如果输入是该命令（可能带参数），否则 False
    """
    return user_input == command or user_input.startswith(command + ' ')


def levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串之间的 Levenshtein 距离（编辑距离）。
    
    Args:
        s1: 第一个字符串
        s2: 第二个字符串
    
    Returns:
        最小编辑次数（插入、删除、替换）
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # 插入、删除、替换的成本
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def suggest_similar_command(unknown_cmd: str) -> str | None:
    """根据未知命令建议最相似的可用命令。
    
    Args:
        unknown_cmd: 用户输入的未知命令（包含 '/' 前缀）
    
    Returns:
        最相似的命令（如果距离 <= 2），否则 None
    """
    available_commands = [
        '/help', '/quit', '/exit', '/clear', '/model', '/usage',
        '/compact', '/undo', '/diff', '/commit', '/save', '/load',
        '/replay', '/spec'
    ]
    
    min_distance = float('inf')
    best_match = None
    
    for cmd in available_commands:
        distance = levenshtein_distance(unknown_cmd, cmd)
        if distance < min_distance:
            min_distance = distance
            best_match = cmd
    
    # 只在距离较小时返回建议（避免完全无关的建议）
    return best_match if min_distance <= 2 else None


# 多行输入的三引号标记
_TRIPLE_DOUBLE = '"""'
_TRIPLE_SINGLE = "'''"


def read_user_input(prompt_str: str) -> str:
    """读取用户输入，支持多行模式。
    
    单行模式：直接返回 strip 后的输入。
    多行模式：当输入以 \\\"\\\"\\\" 或 ''' 开头时，进入多行模式，
    持续读取后续行直到遇到包含对应三引号的行。
    
    多行模式规则：
    - 开始行三引号后的内容作为第一行
    - 结束行三引号前的内容作为最后一行
    - 如果在同一行打开和关闭三引号，取中间内容
    - 保留行内缩进和空行
    - EOFError 时返回已收集的内容
    
    Args:
        prompt_str: 输入提示符
    
    Returns:
        用户输入的文本（单行或多行拼接）
    """
    first_line = input(prompt_str)
    stripped = first_line.strip()
    
    # 检测是否以三引号开头
    delimiter = None
    if stripped.startswith(_TRIPLE_DOUBLE):
        delimiter = _TRIPLE_DOUBLE
    elif stripped.startswith(_TRIPLE_SINGLE):
        delimiter = _TRIPLE_SINGLE
    
    if delimiter is None:
        # 普通单行输入
        return stripped
    
    # 多行模式：去掉开头的三引号
    rest = stripped[len(delimiter):]
    
    # 检查同一行是否也有结束三引号
    if delimiter in rest:
        # 取开头三引号和结尾三引号之间的内容
        end_idx = rest.index(delimiter)
        return rest[:end_idx]
    
    # 进入多行收集
    lines = []
    if rest:
        lines.append(rest)
    
    # 多行续行提示符
    continuation_prompt = "... "
    
    while True:
        try:
            line = input(continuation_prompt)
        except EOFError:
            break
        
        # 检查这一行是否包含结束三引号
        if delimiter in line:
            end_idx = line.index(delimiter)
            before = line[:end_idx]
            if before:
                lines.append(before)
            break
        else:
            lines.append(line)
    
    return "\n".join(lines)


class MarkdownRenderer:
    """流式友好的终端 Markdown 渲染器。
    
    按行缓冲输入，当行完成（遇到 \\\\n）时解析并输出格式化文本。
    支持围栏代码块、标题、行内代码、粗体。
    
    使用方式：
        renderer = MarkdownRenderer()
        # 流式 delta 到达时：
        output = renderer.feed(delta)
        if output:
            print(output, end="")
        # 流结束时：
        output = renderer.flush()
        if output:
            print(output, end="")
    """

    # 围栏代码块开始/结束模式
    _FENCE_PATTERN = re.compile(r'^(`{3,}|~{3,})\s*(.*)?$')

    def __init__(self):
        self._buffer = ""  # 未完成行的缓冲区
        self.in_code_block = False  # 是否在围栏代码块内
        self._fence_marker = ""  # 当前代码块的围栏标记（如 ``` 或 ~~~）

    def feed(self, delta: str) -> str:
        """接收一段文本 delta，返回可输出的格式化文本。
        
        不完整的行会被缓冲，直到遇到换行符。
        
        Args:
            delta: 新到达的文本片段
        
        Returns:
            可以直接 print 的格式化文本（可能为空字符串）
        """
        self._buffer += delta
        
        # 按换行符拆分，最后一段可能不完整
        parts = self._buffer.split("\n")
        
        if len(parts) == 1:
            # 没有换行符，全部缓冲
            return ""
        
        # 最后一个 part 可能是不完整的行，放回缓冲区
        self._buffer = parts[-1]
        
        # 处理所有完整的行
        output = ""
        for line in parts[:-1]:
            output += self._render_line(line) + "\n"
        
        return output

    def flush(self) -> str:
        """输出缓冲区中剩余的内容（流结束时调用）。
        
        Returns:
            缓冲区中的格式化文本
        """
        if not self._buffer:
            return ""
        
        line = self._buffer
        self._buffer = ""
        return self._render_line(line)

    def _render_line(self, line: str) -> str:
        """渲染单行 Markdown 为带 ANSI 颜色的文本。
        
        Args:
            line: 一行文本（不含换行符）
        
        Returns:
            格式化后的文本
        """
        stripped = line.strip()
        
        # 检查围栏代码块开始/结束
        fence_match = self._FENCE_PATTERN.match(stripped)
        if fence_match:
            marker = fence_match.group(1)
            lang = (fence_match.group(2) or "").strip()
            
            if not self.in_code_block:
                # 开始代码块
                self.in_code_block = True
                self._fence_marker = marker[0]  # 记录是 ` 还是 ~
                if lang:
                    return f"{DIM}───── {lang} ─────{RESET}"
                return f"{DIM}─────{RESET}"
            elif marker[0] == self._fence_marker:
                # 结束代码块（标记字符匹配）
                self.in_code_block = False
                self._fence_marker = ""
                return f"{DIM}─────{RESET}"
        
        # 代码块内部：DIM 渲染，不做行内解析
        if self.in_code_block:
            return f"{DIM}{line}{RESET}"
        
        # 标题
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            content = heading_match.group(2)
            return f"{BOLD}{CYAN}{content}{RESET}"
        
        # 行内格式化
        return self._render_inline(line)

    @staticmethod
    def _render_inline(line: str) -> str:
        """渲染行内 Markdown 格式（粗体、行内代码）。
        
        Args:
            line: 一行文本
        
        Returns:
            格式化后的文本
        """
        # 行内代码：`code` → CYAN
        line = re.sub(r'`([^`]+)`', f'{CYAN}\\1{RESET}', line)
        
        # 粗体：**text** → BOLD
        line = re.sub(r'\*\*([^*]+)\*\*', f'{BOLD}\\1{RESET}', line)
        
        return line


def load_system_prompt(value: Optional[str]) -> Optional[str]:
    """加载自定义系统提示词。
    
    如果 value 是一个已存在的文件路径，读取文件内容。
    否则直接使用 value 作为文本。
    空字符串或仅空白返回 None。
    
    Args:
        value: 文件路径或直接文本，或 None
    
    Returns:
        提示词文本，或 None
    """
    if value is None:
        return None
    
    # 尝试作为文件路径读取
    if os.path.isfile(value):
        try:
            with open(value, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            return content if content else None
        except Exception:
            pass  # 读取失败，回退到直接使用文本
    
    # 直接使用文本
    stripped = value.strip()
    return stripped if stripped else None


def parse_args():
    parser = argparse.ArgumentParser(description='SimpleAgent - coding agent')
    parser.add_argument('--version', action='version', version=f'SimpleAgent {__version__}')
    parser.add_argument('--model', default=None, help='Model to use (env: OPENAI_MODEL)')
    parser.add_argument('--provider', default=None, help='LLM provider (openai, deepseek, groq, siliconflow, together, ollama)')
    parser.add_argument('--skills', nargs='+', help='Skill directories to load')
    parser.add_argument('--system', default=None, help='Custom system prompt (text or file path)')
    parser.add_argument('--mcp', action='append', default=None,
                        help='MCP server command (repeatable, e.g. --mcp "npx -y @mcp/server-fs /tmp")')
    return parser.parse_args()


def resolve_model_for_provider(cli_model: Optional[str],
                                provider_name: Optional[str],
                                env_model: Optional[str]
                                ) -> tuple:
    """确定传给 resolve_provider 的 model 参数，并检测 OPENAI_MODEL 是否被忽略。

    优先级：
    1. cli_model（用户显式 --model）→ 直接使用
    2. 有 --provider 且无 --model → 使用 provider 默认模型，忽略 OPENAI_MODEL
    3. 无 --provider 且无 --model → 使用 OPENAI_MODEL 环境变量

    Args:
        cli_model: args.model 值（None 表示用户没传 --model）
        provider_name: args.provider 值（可能为 None）
        env_model: OPENAI_MODEL 环境变量值（可能为 None）

    Returns:
        (model_for_resolve, env_model_ignored) 元组：
        - model_for_resolve: 传给 resolve_provider 的 model 参数（可能为 None）
        - env_model_ignored: OPENAI_MODEL 环境变量是否被忽略
    """
    # 用户显式传了 --model → 直接使用
    if cli_model is not None:
        return cli_model, False

    # 有 --provider 且用户没传 --model → 使用 provider 默认模型
    if provider_name:
        env_model_ignored = bool(env_model)
        return None, env_model_ignored

    # 无 --provider 且无 --model → 使用 OPENAI_MODEL 或 None
    return env_model, False


# ── 斜杠命令处理函数 ──────────────────────────────────────────────


def handle_slash_command(user_input: str, agent: Agent, session_usage: Usage) -> bool:
    """处理斜杠命令。
    
    Args:
        user_input: 用户输入的文本（已 strip）
        agent: Agent 实例
        session_usage: 会话级累计 token 用量
    
    Returns:
        True 表示命令已处理（调用方应 continue），False 表示非斜杠命令
    """
    if user_input == '/help':
        print(f"\n{BOLD}  可用命令：{RESET}")
        print(f"  {CYAN}/help{RESET}              显示此帮助信息")
        print(f"  {CYAN}/quit{RESET}, {CYAN}/exit{RESET}       退出 Agent")
        print(f"  {CYAN}/clear{RESET}             清除对话历史")
        print(f"  {CYAN}/model{RESET} <名称>       切换模型（如 /model gpt-4）")
        print(f"  {CYAN}/usage{RESET}             查看会话累计 token 用量")
        print(f"  {CYAN}/compact{RESET}           总结旧对话并释放上下文空间")
        print(f"  {CYAN}/undo{RESET}              撤销上一次文件更改")
        print(f"  {CYAN}/diff{RESET}              显示本次会话所有更改的 git diff")
        print(f"  {CYAN}/commit{RESET} [消息]      提交本会话修改的文件")
        print(f"  {CYAN}/save{RESET} [名称]        保存当前会话到文件")
        print(f"  {CYAN}/load{RESET} <名称>        从文件加载会话")
        print(f"  {CYAN}/replay{RESET} <日志文件>  从 JSONL 日志重新执行用户输入")
        print(f"  {CYAN}/spec{RESET} <spec 文件>   从 spec 文件生成实现计划")
        print(f"\n{DIM}  多行输入：以 \\\"\\\"\\\" 或 ''' 开头进入，再次输入同样标记结束{RESET}\n")
        return True
    
    if user_input == '/clear':
        agent.clear_conversation()
        print(f"{DIM}  (conversation cleared){RESET}\n")
        return True
    
    if match_command(user_input, '/model'):
        new_model = user_input[6:].strip()
        if not new_model:
            print(f"\n{YELLOW}  ⚠ 用法：/model <名称>（如 /model gpt-4）{RESET}")
            print(f"{DIM}    当前模型：{agent.model}{RESET}\n")
            return True
        agent.with_model(new_model)
        agent.clear_conversation()
        print(f"{DIM}  (switched to {new_model}, conversation cleared){RESET}\n")
        return True
    
    if user_input == '/usage':
        if session_usage.input > 0 or session_usage.output > 0:
            total = session_usage.input + session_usage.output
            print(f"\n{DIM}  session tokens: {session_usage.input} in / {session_usage.output} out / {total} total{RESET}\n")
        else:
            print(f"\n{DIM}  (no token usage recorded yet){RESET}\n")
        return True
    
    if user_input == '/compact':
        return _handle_compact(agent, session_usage)
    
    if user_input == '/undo':
        result = agent.tools.undo()
        if result["success"]:
            path = result.get("path", "?")
            print(f"\n{GREEN}  ✓ 已撤销对 {path} 的更改{RESET}")
            diff_lines = format_diff_lines(result.get("diff", ""))
            for dl in diff_lines:
                print(dl)
        else:
            error = result.get("error", "未知错误")
            print(f"\n{YELLOW}  ⚠ {error}{RESET}")
        print()
        return True
    
    if user_input == '/diff':
        return _handle_diff(agent)
    
    if match_command(user_input, '/commit'):
        return _handle_commit(user_input, agent)
    
    if match_command(user_input, '/save'):
        return _handle_save(user_input, agent)
    
    if match_command(user_input, '/load'):
        return _handle_load(user_input, agent)
    
    if match_command(user_input, '/replay'):
        return _handle_replay(user_input, agent, session_usage)
    
    if match_command(user_input, '/spec'):
        return _handle_spec(user_input, agent)
    
    # 未知斜杠命令：提示可用命令，并建议最相似的命令
    if user_input.startswith('/'):
        cmd = user_input.split()[0]
        print(f"\n{YELLOW}  ⚠ 未知命令：{cmd}{RESET}")
        
        # 尝试建议相似的命令
        suggestion = suggest_similar_command(cmd)
        if suggestion:
            print(f"{DIM}  你是否想输入：{CYAN}{suggestion}{RESET}")
        
        print(f"{DIM}  可用命令：/help /quit /exit /clear /model /usage /compact /undo /diff /commit /save /load /replay /spec{RESET}\n")
        return True
    
    return False


def _handle_compact(agent: Agent, session_usage: Usage) -> bool:
    """处理 /compact 命令：生成结构化摘要并压缩对话。
    
    使用三层记忆的 Anchored Iterative Summarization：
    - 首次压缩：从零生成结构化摘要（4 字段）
    - 后续压缩：在已有摘要基础上增量合并
    """
    msg_count = len(agent.conversation_history)
    if msg_count <= agent.MIN_MESSAGES_TO_COMPACT:
        print(f"\n{YELLOW}  ⚠ 对话太短（{msg_count} 条），无需压缩{RESET}\n")
        return True
    print(f"\n{DIM}  正在生成结构化对话摘要...{RESET}")
    sys.stdout.flush()
    try:
        old_messages = agent.conversation_history[:-agent.DEFAULT_COMPACT_KEEP_RECENT]
        if not old_messages:
            print(f"{YELLOW}  ⚠ 没有足够的旧消息可压缩{RESET}\n")
            return True
        # 构建增量摘要 prompt（首次 vs 增量合并）
        summary_prompt = agent.memory.build_compaction_prompt(old_messages)
        summary_response = agent.client.chat.completions.create(
            model=agent.model,
            max_tokens=Agent.SUMMARY_MAX_TOKENS,
            messages=summary_prompt,
        )
        summary_text = summary_response.choices[0].message.content or "(无摘要)"
        if summary_response.usage:
            session_usage.input += summary_response.usage.prompt_tokens
            session_usage.output += summary_response.usage.completion_tokens
    except KeyboardInterrupt:
        print(f"\n{YELLOW}  ⏹ 摘要生成已中断{RESET}\n")
        return True
    except Exception as e:
        print(f"\n{RED}  ✗ 摘要生成失败：{e}{RESET}\n")
        return True
    # 解析结构化摘要
    new_summary = MemoryManager.parse_structured_summary(summary_text)
    # 执行 compaction
    compact_result = agent.memory.compact_with_summary(
        agent.conversation_history, new_summary, agent.DEFAULT_COMPACT_KEEP_RECENT
    )
    if compact_result["compacted"]:
        agent.conversation_history = compact_result["new_history"]
        # 只在 compact 成功后才更新中期记忆，避免数据不一致
        agent.memory.update_working_summary(new_summary, len(old_messages))
        print(f"{GREEN}  ✓ 已压缩对话：移除 {compact_result['removed']} 条旧消息，保留 {compact_result['kept']} 条最近消息{RESET}")
        # 显示结构化摘要预览
        preview_parts = []
        if new_summary.intent:
            preview_parts.append(f"目标: {truncate(new_summary.intent, 60)}")
        if new_summary.changes:
            preview_parts.append(f"操作: {truncate(new_summary.changes, 60)}")
        if preview_parts:
            print(f"{DIM}  摘要：{' | '.join(preview_parts)}{RESET}\n")
        else:
            print(f"{DIM}  摘要：{truncate(summary_text, 120)}{RESET}\n")
    else:
        print(f"{YELLOW}  ⚠ 对话无需压缩{RESET}\n")
    return True


def _handle_diff(agent: Agent) -> bool:
    """处理 /diff 命令：显示本次会话所有更改的 git diff。"""
    modified_files = agent.tools.get_modified_files()
    if not modified_files:
        print(f"\n{YELLOW}  ⚠ 本会话中没有修改过的文件{RESET}\n")
        return True
    result = git_diff_files(modified_files)
    if result["success"]:
        diff_text = result.get("diff", "")
        if diff_text:
            print(f"\n{BOLD}  📋 本次会话修改的文件（{len(modified_files)} 个）：{RESET}")
            for f in modified_files:
                print(f"{DIM}    • {f}{RESET}")
            print()
            diff_lines = format_diff_lines(diff_text)
            for dl in diff_lines:
                print(dl)
        else:
            print(f"\n{YELLOW}  ⚠ 文件已修改但没有未提交的差异（可能已经 /commit 过了）{RESET}")
    else:
        error = result.get("error", "未知错误")
        print(f"\n{RED}  ✗ 获取差异失败：{error}{RESET}")
    print()
    return True


def _handle_commit(user_input: str, agent: Agent) -> bool:
    """处理 /commit [message] 命令：提交本会话中修改过的文件。"""
    modified_files = agent.tools.get_modified_files()
    if not modified_files:
        print(f"\n{YELLOW}  ⚠ 本会话中没有修改过的文件{RESET}\n")
        return True
    commit_msg = user_input[7:].strip()
    if not commit_msg:
        commit_msg = "SimpleAgent: session changes"
    result = git_add_and_commit(modified_files, commit_msg)
    if result["success"]:
        files_str = ", ".join(result.get("files", []))
        print(f"\n{GREEN}  ✓ 已提交 {len(result.get('files', []))} 个文件：{files_str}{RESET}")
        output = result.get("output", "")
        if output:
            print(f"{DIM}    {output}{RESET}")
    else:
        error = result.get("error", "未知错误")
        print(f"\n{RED}  ✗ 提交失败：{error}{RESET}")
    print()
    return True


def _handle_save(user_input: str, agent: Agent) -> bool:
    """处理 /save [name] 命令：保存当前会话到文件。"""
    name = user_input[5:].strip()
    if not name:
        name = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if not name.endswith('.json'):
        name += '.json'
    filepath = os.path.join(SESSIONS_DIR, name)
    result = agent.save_session(filepath)
    if result["success"]:
        msg_count = len(agent.conversation_history)
        print(f"\n{GREEN}  ✓ 会话已保存：{result['path']}（{msg_count} 条消息）{RESET}")
    else:
        error = result.get("error", "未知错误")
        print(f"\n{RED}  ✗ 保存失败：{error}{RESET}")
    print()
    return True


def _handle_load(user_input: str, agent: Agent) -> bool:
    """处理 /load <name> 命令：从文件加载会话。"""
    name = user_input[5:].strip()
    if not name:
        # 列出可用的会话文件
        try:
            files = sorted(
                [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.json')],
                reverse=True,
            )
        except FileNotFoundError:
            files = []
        if files:
            print(f"\n{YELLOW}  ⚠ 用法：/load <名称>{RESET}")
            print(f"{DIM}  可用会话（最近 5 个）：{RESET}")
            for f in files[:5]:
                print(f"{DIM}    {f[:-5]}{RESET}")  # 去掉 .json 后缀
        else:
            print(f"\n{YELLOW}  ⚠ 用法：/load <名称>（{SESSIONS_DIR}/ 目录下无会话文件）{RESET}")
        print()
        return True
    if not name.endswith('.json'):
        name += '.json'
    filepath = os.path.join(SESSIONS_DIR, name)
    result = agent.load_session(filepath)
    if result["success"]:
        print(f"\n{GREEN}  ✓ 会话已加载：{result['path']}{RESET}")
        print(f"{DIM}    模型：{result['model']}，{result['message_count']} 条消息{RESET}")
    else:
        error = result.get("error", "未知错误")
        print(f"\n{RED}  ✗ 加载失败：{error}{RESET}")
    print()
    return True


def _handle_spec(user_input: str, agent: Agent) -> bool:
    """处理 /spec <file> 命令：从 spec 文件生成实现计划。
    
    读取 spec 文件内容，结合项目上下文，构造特殊提示让 Agent 分析
    spec 并生成分步实现计划。结果通过 agent._spec_prompt 传递给
    调用方（main 循环），作为下一条用户输入发送给 Agent。
    """
    name = user_input[5:].strip()
    if not name:
        print(f"\n{BOLD}  Spec-Driven Development{RESET}")
        print(f"{DIM}  从 spec 文件生成实现计划，引导 Agent 分步完成开发。{RESET}")
        print(f"\n{YELLOW}  用法：/spec <spec 文件路径>{RESET}")
        print(f"{DIM}  示例：{RESET}")
        print(f"{DIM}    /spec specs/auth-api.md{RESET}")
        print(f"{DIM}    /spec feature-request.md{RESET}")
        print(f"\n{DIM}  Spec 文件是普通 Markdown，描述功能需求、约束和验收标准。{RESET}")
        print(f"{DIM}  Agent 会分析 spec 并生成分步实现计划（不自动执行）。{RESET}")
        print(f"{DIM}  你可以逐步确认计划后再让 Agent 执行。{RESET}\n")
        return True
    
    # 读取 spec 文件
    filepath = name
    if not os.path.isfile(filepath):
        print(f"\n{RED}  ✗ Spec 文件不存在：{filepath}{RESET}\n")
        return True
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            spec_content = f.read().strip()
    except Exception as e:
        print(f"\n{RED}  ✗ 读取失败：{e}{RESET}\n")
        return True
    
    if not spec_content:
        print(f"\n{YELLOW}  ⚠ Spec 文件为空：{filepath}{RESET}\n")
        return True
    
    print(f"\n{GREEN}  ✓ 已加载 spec：{filepath}（{len(spec_content)} 字符）{RESET}")
    print(f"{DIM}  正在生成实现计划...{RESET}\n")
    
    # 构造 spec 分析提示，存储到 agent 临时属性供 main 循环发送
    spec_prompt = f"""请基于以下 Spec 文件生成一份详细的分步实现计划。

## Spec 文件：{filepath}

{spec_content}

---

## 要求

请分析以上 spec，结合当前项目的代码结构和约束，生成实现计划。计划应包含：

1. **需求分析**：简要总结 spec 的核心需求和约束
2. **影响范围**：列出需要修改或新增的文件
3. **分步计划**：将实现拆分为有序的小步骤，每步包含：
   - 步骤编号和标题
   - 具体要做什么（修改哪个文件的哪个部分）
   - 预期结果
4. **测试策略**：需要添加的测试用例概述
5. **风险提示**：可能的风险和注意事项

**注意：只输出计划，不要执行任何修改。** 等待用户确认后再逐步实施。"""
    
    agent._spec_prompt = spec_prompt
    return True


def _handle_replay(user_input: str, agent: Agent, session_usage: Usage) -> bool:
    """处理 /replay <file> 命令：从 JSONL 日志重新执行用户输入。
    
    仅提取日志中的 user_input 事件，不重放工具调用或 Agent 响应。
    用户可以在任何时候按 Ctrl+C 中断重放。
    返回 'replay_inputs' 键供调用方在事件循环中逐条执行。
    """
    name = user_input[7:].strip()
    if not name:
        # 列出可用的日志文件
        try:
            files = sorted(
                [f for f in os.listdir(LOGS_DIR) if f.endswith('.jsonl')],
                reverse=True,
            )
        except FileNotFoundError:
            files = []
        if files:
            print(f"\n{YELLOW}  ⚠ 用法：/replay <日志文件名>{RESET}")
            print(f"{DIM}  可用日志（最近 5 个）：{RESET}")
            for f in files[:5]:
                print(f"{DIM}    {f}{RESET}")
        else:
            print(f"\n{YELLOW}  ⚠ 用法：/replay <日志文件名>（{LOGS_DIR}/ 目录下无日志文件）{RESET}")
        print()
        return True
    
    # 自动补后缀
    if not name.endswith('.jsonl'):
        name += '.jsonl'
    filepath = os.path.join(LOGS_DIR, name)
    
    result = load_transcript(filepath)
    if not result["success"]:
        print(f"\n{RED}  ✗ 加载失败：{result['error']}{RESET}\n")
        return True
    
    inputs = result["inputs"]
    if not inputs:
        print(f"\n{YELLOW}  ⚠ 日志中没有用户输入可重放{RESET}\n")
        return True
    
    print(f"\n{BOLD}  🔄 准备重放 {len(inputs)} 条用户输入{RESET}")
    if result["model"]:
        print(f"{DIM}    原始模型：{result['model']}{RESET}")
    print(f"{DIM}    按 Ctrl+C 可随时中断重放{RESET}\n")
    
    # 将输入列表存入 agent 的临时属性，由 main() 循环逐条消费
    agent._replay_queue = list(inputs)
    return True


# ── 事件流渲染函数 ──────────────────────────────────────────────


def render_event(event: dict, md_renderer: MarkdownRenderer, in_text: bool,
                 session_logger: SessionLogger, collected_response: list) -> tuple:
    """渲染单个事件流事件。
    
    Args:
        event: 事件字典
        md_renderer: Markdown 渲染器实例
        in_text: 当前是否在文本输出中
        session_logger: 会话日志记录器
        collected_response: 收集响应文本的列表（单元素列表，用于在函数内修改）
    
    Returns:
        (in_text, last_usage, interrupted) 元组：
        - in_text: 更新后的文本输出状态
        - last_usage: 本轮 Usage（仅 agent_end 时非 None）
        - interrupted: 是否已中断
    """
    last_usage = None
    interrupted = False
    event_type = event["type"]
    
    if event_type == "tool_start":
        if in_text:
            remaining = md_renderer.flush()
            if remaining:
                print(remaining, end="")
            print()
            in_text = False
        tool_name = event["tool_name"]
        tool_args = event["args"]
        
        if tool_name == "execute_command":
            cmd = tool_args.get("command", "...")
            summary = f"$ {truncate(cmd, 80)}"
        elif tool_name == "read_file":
            summary = f"read {tool_args.get('path', '?')}"
        elif tool_name == "write_file":
            summary = f"write {tool_args.get('path', '?')}"
        elif tool_name == "edit_file":
            summary = f"edit {tool_args.get('path', '?')}"
        elif tool_name == "list_files":
            summary = f"ls {tool_args.get('path', '.')}"
        elif tool_name == "search_files":
            pattern = tool_args.get("pattern", "?")
            summary = f"search '{truncate(pattern, 60)}'"
        elif tool_name == "web_search":
            query = tool_args.get("query", "?")
            summary = f"🔍 {truncate(query, 60)}"
        else:
            summary = tool_name
        
        print(f"{YELLOW}  ▶ {summary}{RESET}")
        sys.stdout.flush()
        session_logger.log("tool_call", {"tool": tool_name, "args": tool_args})
    
    elif event_type == "tool_end":
        tool_name = event["tool_name"]
        result = event["result"]
        success = result.get("success", False)
        status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        print(f"{DIM}    {status} {tool_name} done{RESET}")
        diff_lines = format_diff_lines(result.get("diff", ""))
        for dl in diff_lines:
            print(dl)
        sys.stdout.flush()
        log_result = {"tool": tool_name, "success": success}
        if not success:
            log_result["error"] = result.get("error", "")
        session_logger.log("tool_result", log_result)
    
    elif event_type == "reasoning":
        if in_text:
            remaining = md_renderer.flush()
            if remaining:
                print(remaining, end="")
            print()
        print(f"{DIM}  💭 {truncate(event['content'], 200)}{RESET}")
        in_text = False
    
    elif event_type == "text_update":
        if not in_text:
            print()
            in_text = True
        rendered = md_renderer.feed(event["delta"])
        if rendered:
            print(rendered, end="")
            sys.stdout.flush()
        collected_response[0] += event["delta"]
    
    elif event_type == "agent_end":
        if in_text:
            remaining = md_renderer.flush()
            if remaining:
                print(remaining, end="")
        last_usage = Usage(
            input=event["usage"].input,
            output=event["usage"].output,
        )
        elapsed = event.get("elapsed")
        if elapsed is not None:
            print(f"\n{DIM}  ⏱ {format_elapsed(elapsed)}{RESET}")
        if collected_response[0]:
            session_logger.log("agent_response", {"content": collected_response[0]})
        session_logger.log("usage", {
            "input_tokens": last_usage.input,
            "output_tokens": last_usage.output,
            "elapsed": elapsed,
        })
    
    elif event_type == "interrupted":
        interrupted = True
        if in_text:
            remaining = md_renderer.flush()
            if remaining:
                print(remaining, end="")
            print()
        print(f"\n{YELLOW}  ⏹ 已中断：{event['message']}{RESET}")
    
    elif event_type == "error":
        print(f"{RED}Error: {event['message']}{RESET}")
    
    elif event_type == "warning":
        if in_text:
            print()
            in_text = False
        print(f"{YELLOW}  ⚠ {event['message']}{RESET}")
    
    elif event_type == "context_warning":
        if in_text:
            print()
            in_text = False
        print(f"\n{YELLOW}  {event['message']}{RESET}")
    
    elif event_type == "auto_compact":
        if in_text:
            print()
            in_text = False
        print(f"\n{GREEN}  🗜 {event['message']}{RESET}")
    
    elif event_type == "auto_test":
        if in_text:
            print()
            in_text = False
        test_result = event.get("result", {})
        if test_result.get("success"):
            print(f"\n{GREEN}  🧪 自动测试通过 ({test_result.get('command', '')}){RESET}")
        else:
            print(f"\n{RED}  🧪 自动测试失败 ({test_result.get('command', '')}){RESET}")
            stderr = test_result.get("stderr", "")
            stdout = test_result.get("stdout", "")
            output = stderr or stdout
            if output:
                lines = output.strip().splitlines()
                preview = "\n".join(lines[-5:]) if len(lines) > 5 else "\n".join(lines)
                print(f"{DIM}  {preview}{RESET}")
    
    elif event_type == "route":
        if in_text:
            print()
            in_text = False
        complexity = event.get("complexity", "?")
        routed_model = event.get("model", "?")
        print(f"{DIM}  🔀 路由: {complexity} → {routed_model}{RESET}")
    
    return in_text, last_usage, interrupted


# ── 事件流执行辅助函数 ──────────────────────────────────────────


async def _run_prompt_stream(agent: Agent, user_input: str,
                             session_usage: Usage,
                             session_logger: SessionLogger,
                             interrupt_label: str = "当前回合已中断") -> bool:
    """执行一次 prompt_stream 并渲染所有事件。

    封装初始化、事件流消费、KeyboardInterrupt 处理和 usage 输出的共用逻辑。

    Args:
        agent: Agent 实例
        user_input: 要发送给 Agent 的文本
        session_usage: 会话级累计 token 用量（原地更新）
        session_logger: 会话日志记录器
        interrupt_label: 中断时显示的标签文本

    Returns:
        True 表示正常完成，False 表示被中断
    """
    in_text = False
    last_usage = Usage()
    interrupted = False
    md_renderer = MarkdownRenderer()
    collected_response = [""]

    session_logger.log("user_input", {"content": user_input})

    try:
        async for event in agent.prompt_stream(user_input):
            in_text, event_usage, event_interrupted = render_event(
                event, md_renderer, in_text, session_logger, collected_response
            )
            if event_usage is not None:
                last_usage = event_usage
                session_usage.input += last_usage.input
                session_usage.output += last_usage.output
            if event_interrupted:
                interrupted = True
    except KeyboardInterrupt:
        interrupted = True
        if in_text:
            print()
        print(f"\n{YELLOW}  ⏹ {interrupt_label}{RESET}")

    if in_text and not interrupted:
        print()
    if not interrupted:
        print_usage(last_usage, session_usage)
    print()

    return not interrupted


# ── 主函数 ──────────────────────────────────────────────────────


async def main():
    args = parse_args()
    
    # 解析提供商配置
    raw_api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('API_KEY')
    raw_base_url = os.environ.get('OPENAI_BASE_URL')
    env_model = os.environ.get('OPENAI_MODEL')
    
    # 确定传给 resolve_provider 的 model 参数
    user_specified_model, env_model_ignored = resolve_model_for_provider(
        cli_model=args.model,
        provider_name=args.provider,
        env_model=env_model,
    )
    
    try:
        resolved = resolve_provider(
            provider_name=args.provider,
            model=user_specified_model,
            base_url=raw_base_url,
            api_key=raw_api_key,
        )
    except ValueError as e:
        print(f"Error: {e}")
        available = list_providers()
        print(f"\n可用提供商：")
        for p in available:
            print(f"  {p.name:15s} {p.display_name} (默认模型: {p.default_model})")
        sys.exit(1)
    
    api_key = resolved["api_key"]
    base_url = resolved["base_url"]
    model = resolved["model"] or DEFAULT_MODEL
    provider_display = resolved["provider_display_name"]
    
    # 警告：OPENAI_MODEL 被忽略
    if env_model_ignored:
        print(f"{YELLOW}  ⚠ 忽略环境变量 OPENAI_MODEL='{env_model}'（与 --provider {args.provider} 可能不兼容）{RESET}")
        print(f"{DIM}    使用 {args.provider} 默认模型：{model}{RESET}")
        print(f"{DIM}    如需指定模型，请使用 --model 参数{RESET}")
    
    if not api_key:
        # 不需要 API key 的 provider（如 Ollama）：使用占位值，跳过检查
        if args.provider:
            from .providers import get_provider
            p = get_provider(args.provider)
            if p and p.api_key_env is None:
                # Provider 明确声明不需要 API key，提供占位值给 OpenAI SDK
                api_key = "not-needed"
            else:
                env_hint = p.api_key_env if p and p.api_key_env else "OPENAI_API_KEY"
                print(f"Error: Set {env_hint} environment variable for {args.provider}")
                sys.exit(1)
        else:
            print("Error: Set OPENAI_API_KEY or API_KEY environment variable")
            sys.exit(1)
    
    skills = SkillSet()
    if args.skills:
        skills.load(args.skills)
    
    # 路由器配置：当 --provider 导致 OPENAI_MODEL 被忽略时，
    # 路由器也必须忽略环境变量中的模型名（它们可能与 provider 不兼容）
    router_config = None  # 默认从环境变量加载
    if env_model_ignored:
        # OPENAI_MODEL 被忽略 → 路由器不应使用环境变量中的模型名
        # 传入只含 model_high 的配置，路由器因只有 1 个 unique 模型而自动禁用
        router_config = RouterConfig(model_high=model)
    agent = Agent(api_key, model, base_url=base_url, max_tokens=resolved.get("max_tokens"),
                  router_config=router_config)
    agent.with_skills(skills)
    agent.with_tools(default_tools())
    
    # 注入危险命令确认回调
    def confirm_dangerous_command(command: str, reason: str) -> bool:
        """终端中询问用户是否允许执行危险命令。"""
        print(f"\n{YELLOW}  ⚠ 危险命令需要确认：{reason}{RESET}")
        print(f"{DIM}    命令：{command}{RESET}")
        try:
            answer = input(f"{YELLOW}  是否执行？(y/N) {RESET}").strip().lower()
            return answer in ('y', 'yes')
        except (EOFError, KeyboardInterrupt):
            print()
            return False
    
    agent.confirm_callback = confirm_dangerous_command
    
    # 连接 MCP 服务器
    mcp_clients = []
    if args.mcp:
        from .mcp_client import MCPClient, parse_mcp_arg
        for mcp_arg in args.mcp:
            try:
                params = parse_mcp_arg(mcp_arg)
            except ValueError as e:
                print(f"{RED}  ✗ MCP 参数解析失败：{e}{RESET}")
                continue
            client = MCPClient(params["command"], params["args"], params.get("env"))
            print(f"{DIM}  正在连接 MCP 服务器：{params['command']} {' '.join(params['args'])}...{RESET}")
            sys.stdout.flush()
            result = await client.connect()
            if result["success"]:
                count = agent.register_mcp_tools(client)
                mcp_clients.append(client)
                tools_str = ", ".join(result["tools"][:5])
                if len(result["tools"]) > 5:
                    tools_str += f" ... (+{len(result['tools']) - 5})"
                print(f"{GREEN}  ✓ MCP 已连接：{count} 个工具 [{tools_str}]{RESET}")
            else:
                print(f"{RED}  ✗ MCP 连接失败：{result['error']}{RESET}")
                await client.close()
    
    # 加载自定义系统提示词
    custom_prompt = load_system_prompt(args.system)
    if custom_prompt:
        agent.with_system_prompt(custom_prompt)
    
    print_banner()
    model_display = f"{provider_display} / {model}" if provider_display else model
    print(f"{DIM}  model: {model_display}{RESET}")
    if base_url:
        print(f"{DIM}  base_url: {base_url}{RESET}")
    if not skills.is_empty():
        print(f"{DIM}  skills: {len(skills)} loaded{RESET}")
    if mcp_clients:
        total_mcp_tools = sum(len(c.tools) for c in mcp_clients)
        print(f"{DIM}  mcp:    {len(mcp_clients)} server(s), {total_mcp_tools} tool(s){RESET}")
    if custom_prompt:
        if args.system and os.path.isfile(args.system):
            print(f"{DIM}  system: {args.system}{RESET}")
        else:
            preview = truncate(custom_prompt, 60)
            print(f'{DIM}  system: "{preview}"{RESET}')
    if agent.router.enabled:
        cfg = agent.router.config
        parts = []
        if cfg.model_high:
            parts.append(f"high={cfg.model_high}")
        if cfg.model_middle:
            parts.append(f"mid={cfg.model_middle}")
        if cfg.model_low:
            parts.append(f"low={cfg.model_low}")
        print(f"{DIM}  router: {', '.join(parts)}{RESET}")
    
    git_branch = get_git_branch()
    if git_branch:
        print(f"{DIM}  branch: {git_branch}{RESET}")
    
    print(f"{DIM}  cwd:   {os.getcwd()}{RESET}\n")
    
    last_interrupt_time = 0.0
    DOUBLE_CTRL_C_INTERVAL = 1.0
    session_usage = Usage()
    
    # 初始化会话日志
    session_logger = SessionLogger(log_dir=LOGS_DIR, model=model)
    
    try:
        while True:
            try:
                # 每次输入时刷新分支名
                branch = get_git_branch()
                if branch:
                    prompt_str = f"{BOLD}{GREEN}{branch}> {RESET}"
                else:
                    prompt_str = f"{BOLD}{GREEN}> {RESET}"
                
                user_input = read_user_input(prompt_str)
                
                if not user_input:
                    continue
                
                if user_input in ['/quit', '/exit']:
                    break
                
                # 处理斜杠命令
                if handle_slash_command(user_input, agent, session_usage):
                    # 检查是否有 replay 队列需要执行
                    if agent._replay_queue:
                        replay_inputs = agent._replay_queue
                        agent._replay_queue = None
                        replay_ok = True
                        for idx, replay_input in enumerate(replay_inputs, 1):
                            print(f"{BOLD}{CYAN}  🔄 [{idx}/{len(replay_inputs)}] {truncate(replay_input, 80)}{RESET}\n")
                            completed = await _run_prompt_stream(
                                agent, replay_input, session_usage, session_logger,
                                interrupt_label=f"重放已中断（第 {idx}/{len(replay_inputs)} 条）",
                            )
                            if not completed:
                                replay_ok = False
                                break
                        
                        if replay_ok:
                            print(f"{GREEN}  ✓ 重放完成（{len(replay_inputs)} 条）{RESET}\n")
                    # 检查是否有 spec 提示需要发送
                    elif agent._spec_prompt:
                        spec_input = agent._spec_prompt
                        agent._spec_prompt = None
                        await _run_prompt_stream(
                            agent, spec_input, session_usage, session_logger,
                            interrupt_label="Spec 分析已中断",
                        )
                    continue
                
                # 处理事件流
                await _run_prompt_stream(
                    agent, user_input, session_usage, session_logger,
                    interrupt_label="当前回合已中断",
                )
                    
            except KeyboardInterrupt:
                now = time.time()
                if now - last_interrupt_time < DOUBLE_CTRL_C_INTERVAL:
                    print("\n")
                    break
                last_interrupt_time = now
                print(f"\n{DIM}  (按 Ctrl+C 再次快速按下以退出，或继续输入){RESET}\n")
                continue
            except EOFError:
                break
    finally:
        # 无论正常退出还是异常冒泡，都确保清理资源
        session_logger.close()
        for client in mcp_clients:
            await client.close()
    
    print(f"\n{DIM}  bye 👋{RESET}\n")


def run():
    """同步入口点，方便从 main.py 调用。"""
    asyncio.run(main())
