"""Agent 核心逻辑 - 对话循环、工具调用分发和 LLM 交互。"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from openai import OpenAI, AuthenticationError, RateLimitError, APIConnectionError, APITimeoutError, BadRequestError, APIStatusError

from .models import ToolCallRequest, Usage
from .tools import ToolExecutor, TOOL_DEFINITIONS, default_tools
from .skills import SkillSet
from .prompt import build_system_prompt, detect_project_info
from .memory import MemoryManager, WorkingSummary
from .router import ModelRouter, RouterConfig


class Agent:
    # 对话历史最大消息数（超过时自动截断最早的消息）
    DEFAULT_MAX_HISTORY = 100

    # 上下文窗口默认 token 上限（对应 DeepSeek-V3_2-Online-32k）
    DEFAULT_MAX_CONTEXT_TOKENS = 32768
    # 当 prompt_tokens 占 max_context_tokens 的比例达到此值时，发出警告
    CONTEXT_WARNING_RATIO = 0.80
    # 当比例达到此值时，自动触发 compaction
    CONTEXT_AUTO_COMPACT_RATIO = 0.90

    # 默认 max_tokens（LLM 单次回复的最大 token 数）
    DEFAULT_MAX_TOKENS = 20480

    # 摘要生成的 max_tokens（compaction 使用）
    SUMMARY_MAX_TOKENS = 1024

    def __init__(self, api_key: str, model: str = "DeepSeek-V3_2-Online-32k", base_url: Optional[str] = None,
                 max_history: int = DEFAULT_MAX_HISTORY,
                 max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
                 max_tokens: Optional[int] = None,
                 router_config: Optional[RouterConfig] = None,
                 parent: Optional['Agent'] = None):
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        self.model = model
        self.max_history = max_history
        self.max_context_tokens = max_context_tokens
        self.max_tokens = max_tokens if max_tokens is not None else self.DEFAULT_MAX_TOKENS
        self._last_prompt_tokens = 0
        self.system_prompt_override: Optional[str] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.skills = SkillSet()
        self.tools = default_tools()
        self.tool_definitions = list(TOOL_DEFINITIONS)  # 每个实例独立副本
        self.confirm_callback: Optional[Any] = None  # Callable[[str, str], bool] 用于危险命令确认
        self._edit_fail_counts: Dict[str, int] = {}  # 按文件路径追踪 edit_file 连续失败次数
        self.auto_test = True  # 修改代码文件后自动运行项目测试
        self._mcp_clients: list = []  # MCPClient 实例列表
        self._mcp_tool_map: Dict[str, Any] = {}  # tool_name -> MCPClient 映射
        self._spec_prompt: Optional[str] = None  # /spec 命令产生的提示，由 cli.py main() 消费
        self._replay_queue: Optional[List[str]] = None  # /replay 命令产生的输入队列，由 cli.py main() 消费
        self.memory = MemoryManager()  # 三层记忆管理器
        self.memory.load_archival()  # 加载跨会话长期记忆
        self.router = ModelRouter(router_config)  # LLM 路由器（三级模型选择）
        
        # SubAgent 支持（Issue #6）
        self.parent = parent  # 父 Agent（None 表示顶层 Agent）
        self.subagents: List['Agent'] = []  # 子 Agent 列表
        self.shared_context: Dict[str, Any] = {}  # Context Lake（共享只读上下文）
        
        self.refresh_system_prompt()
    
    def refresh_system_prompt(self) -> 'Agent':
        archival_context = self.memory.get_archival_context() if self.memory.archival else None
        self.system_prompt = build_system_prompt(self.skills, self.system_prompt_override, archival_context)
        return self

    def with_system_prompt(self, prompt: str) -> 'Agent':
        self.system_prompt_override = prompt
        return self.refresh_system_prompt()
    
    def with_model(self, model: str) -> 'Agent':
        self.model = model
        return self
    
    def with_skills(self, skills: SkillSet) -> 'Agent':
        self.skills = skills
        return self.refresh_system_prompt()
    
    def with_tools(self, tools: ToolExecutor) -> 'Agent':
        self.tools = tools
        return self
    
    def register_mcp_tools(self, client) -> int:
        """注册一个 MCP 客户端的工具到 Agent。
        
        将客户端的工具定义追加到 tool_definitions，
        并建立 tool_name -> client 的映射关系。
        
        Args:
            client: 已连接的 MCPClient 实例
        
        Returns:
            注册的工具数量
        """
        self._mcp_clients.append(client)
        tool_defs = client.get_tool_definitions()
        for td in tool_defs:
            name = td["function"]["name"]
            self._mcp_tool_map[name] = client
            self.tool_definitions.append(td)
        return len(tool_defs)
    
    def _trim_history(self) -> int:
        """当对话历史超过 max_history 时，截断最早的消息。
        
        截断时注意不能拆开 assistant(tool_calls) + tool 消息组：
        OpenAI API 要求每个 tool_calls 后紧跟对应的 tool 结果消息。
        如果截断点落在一个 tool_calls 组的中间，需要向前多删到该组开头。
        
        Returns:
            被删除的消息数量（0 表示未截断）
        """
        if len(self.conversation_history) <= self.max_history:
            return 0
        
        # 需要保留的消息数
        keep = self.max_history
        # 初始截断点：从这里开始保留
        cut = len(self.conversation_history) - keep
        
        # 确保截断点不落在 tool_calls 组中间：
        # 如果 cut 处的消息是 tool 角色，说明它前面应有对应的 assistant(tool_calls)
        # 需要继续向后移动 cut 直到跳过这个不完整的组
        while cut < len(self.conversation_history) and self.conversation_history[cut].get("role") == "tool":
            cut += 1
        
        # 如果跳过 tool 消息后 cut 到达末尾，说明无法找到安全截断点，不截断
        if cut >= len(self.conversation_history):
            return 0
        
        # 如果 cut 处是 assistant 且带 tool_calls，它后面的 tool 消息也要保留
        # 这种情况 cut 已经在 assistant 开头，是安全的截断点，不需要调整
        
        if cut <= 0:
            return 0
        
        removed = cut
        self.conversation_history = self.conversation_history[cut:]
        return removed

    def _check_context_usage(self) -> str:
        """检查上下文 token 使用率。
        
        基于最近一次 API 返回的 prompt_tokens 和 max_context_tokens 计算比例。
        
        Returns:
            'ok' — 低于警告阈值
            'warning' — 达到 CONTEXT_WARNING_RATIO 但未达 CONTEXT_AUTO_COMPACT_RATIO
            'critical' — 达到或超过 CONTEXT_AUTO_COMPACT_RATIO
        """
        if self.max_context_tokens <= 0 or self._last_prompt_tokens <= 0:
            return "ok"
        
        ratio = self._last_prompt_tokens / self.max_context_tokens
        
        if ratio >= self.CONTEXT_AUTO_COMPACT_RATIO:
            return "critical"
        elif ratio >= self.CONTEXT_WARNING_RATIO:
            return "warning"
        return "ok"

    def _context_pct(self) -> int:
        """返回当前上下文使用率百分比（整数）。"""
        if self.max_context_tokens <= 0:
            return 0
        return int(self._last_prompt_tokens / self.max_context_tokens * 100)

    def _context_warning_message(self, suffix: str) -> str:
        """构建上下文警告消息的通用格式。
        
        Args:
            suffix: 消息尾部的建议文本（如 "建议使用 /compact ..."）
        
        Returns:
            格式化的警告消息字符串
        """
        pct = self._context_pct()
        return f"⚠️ 上下文使用率 {pct}%（{self._last_prompt_tokens}/{self.max_context_tokens} tokens），{suffix}"

    # 危险命令模式：(正则模式, 原因描述)
    DANGEROUS_COMMAND_PATTERNS = [
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?(?:xargs\s+)?rm(?:\s|$)', 'rm 命令会删除文件'),
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?rmdir(?:\s|$)', 'rmdir 命令会删除目录'),
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?chmod(?:\s|$)', 'chmod 命令会修改文件权限'),
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?chown(?:\s|$)', 'chown 命令会修改文件所有者'),
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?mkfs', 'mkfs 命令会格式化磁盘'),
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?dd(?:\s|$)', 'dd 命令会直接写磁盘'),
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?truncate(?:\s|$)', 'truncate 命令会截断文件'),
        (r'(?:^|[|;&]\s*)(?:sudo\s+)?mv\s+\S+\s+/dev/null', 'mv 到 /dev/null 会销毁文件'),
        (r'(?:^|\s)>\s*\S+', '> 重定向会覆盖文件内容'),
    ]

    @staticmethod
    def _strip_quotes(command: str) -> str:
        """剥离命令中引号包裹的内容，用占位符替换。
        
        用于危险命令检测时排除引号内的 > 等符号。
        支持双引号和单引号，不处理转义引号（简化实现，覆盖绝大多数场景）。
        
        Args:
            command: shell 命令字符串
        
        Returns:
            引号内容被替换为 __QUOTED__ 后的字符串
        """
        # 先替换双引号内容，再替换单引号内容
        result = re.sub(r'"[^"]*"', '__QUOTED__', command)
        result = re.sub(r"'[^']*'", '__QUOTED__', result)
        return result

    @staticmethod
    def _is_dangerous_command(command: str) -> Optional[str]:
        """检测命令是否为破坏性操作。
        
        Args:
            command: 要检测的 shell 命令字符串
        
        Returns:
            危险原因字符串（如果是危险命令），或 None（安全命令）
        """
        if not command or not command.strip():
            return None
        
        for pattern, reason in Agent.DANGEROUS_COMMAND_PATTERNS:
            # > 重定向模式需要先剥离引号内容，避免引号内的 > 误报
            if '>' in pattern:
                if re.search(pattern, Agent._strip_quotes(command)):
                    return reason
            else:
                if re.search(pattern, command):
                    return reason
        return None

    @staticmethod
    def _classify_api_error(exc: Exception) -> tuple:
        """将 API 调用异常分类为事件元组 (event_type, message)。
        
        从 8 层 except 块中提取的共享逻辑，被 prompt() 和 prompt_stream() 使用。
        
        Args:
            exc: API 调用抛出的异常
        
        Returns:
            (event_type, message) 元组，event_type 为 'interrupted' 或 'error'
        """
        if isinstance(exc, KeyboardInterrupt):
            return ("interrupted", "用户中断了 API 请求")
        elif isinstance(exc, AuthenticationError):
            return ("error", f"API 认证失败：密钥无效或已过期。请检查 OPENAI_API_KEY 环境变量。\n详情：{exc}")
        elif isinstance(exc, RateLimitError):
            return ("error", f"API 速率限制：请求过于频繁或额度已用完。请稍后重试或检查账户余额。\n详情：{exc}")
        elif isinstance(exc, APITimeoutError):
            return ("error", f"API 请求超时：服务器响应时间过长。请稍后重试。\n详情：{exc}")
        elif isinstance(exc, APIConnectionError):
            return ("error", f"API 连接失败：无法连接到服务器。请检查网络连接和 OPENAI_BASE_URL 设置。\n详情：{exc}")
        elif isinstance(exc, BadRequestError):
            msg = str(exc)
            if "context_length" in msg or "max_tokens" in msg or "too long" in msg.lower():
                return ("error", f"上下文过长：对话历史超出模型限制。请使用 /clear 清除对话后重试。\n详情：{exc}")
            else:
                return ("error", f"API 请求参数错误：{exc}")
        elif isinstance(exc, APIStatusError):
            return ("error", f"API 服务异常（HTTP {exc.status_code}）：{exc}")
        else:
            return ("error", f"未知错误：{exc}")

    @staticmethod
    def _enrich_tool_error(tool_name: str, result: Dict[str, Any], fail_count: int = 0) -> Dict[str, Any]:
        """为失败的工具调用结果附加智能提示（hint），引导 LLM 尝试替代方案。
        
        成功结果原样返回。失败结果根据工具名和错误类型添加 hint 字段。
        当 edit_file 对同一文件连续失败多次时，升级建议使用 write_file 整体覆盖。
        
        Args:
            tool_name: 工具名称（如 'read_file', 'edit_file'）
            result: 工具执行返回的字典
            fail_count: 该工具对同一文件的连续失败次数（仅 edit_file 使用）
        
        Returns:
            原始结果（成功时）或附加了 hint 字段的结果（失败时）
        """
        if result.get("success"):
            return result
        
        error = result.get("error", "")
        hint = ""
        
        if tool_name == "edit_file":
            if "Old content not found" in error:
                if fail_count >= 2:
                    hint = "提示：edit_file 已连续多次失败，old_content 与文件实际内容不匹配。建议改用替代方案：先用 read_file 获取文件完整内容，然后用 write_file 写入修改后的完整内容来替代 edit_file。"
                else:
                    hint = "提示：old_content 与文件实际内容不匹配。请先用 read_file 查看文件当前内容，确认 old_content 精确匹配后重试。"
            elif "二进制文件" in error:
                hint = "提示：该文件是二进制文件，无法使用 edit_file。如需修改二进制文件，请使用 execute_command 配合合适的命令行工具。"
            elif "No such file or directory" in error:
                hint = "提示：文件不存在。请用 list_files 或 search_files 确认正确的文件路径后重试。"
            elif "Permission denied" in error:
                hint = "提示：权限不足，无法编辑该文件。请检查文件权限或尝试其他路径。"
        
        elif tool_name == "read_file":
            if "二进制文件" in error:
                hint = "提示：该文件是二进制文件，无法用 read_file 读取。如需查看文件类型，请使用 execute_command 执行 file <路径>；如需查看内容，请使用 xxd 或 hexdump 命令。"
            elif "No such file or directory" in error:
                hint = "提示：文件不存在。请用 list_files 查看目录内容，或用 search_files 搜索文件名。"
            elif "Permission denied" in error:
                hint = "提示：权限不足，无法读取该文件。请检查文件权限。"
        
        elif tool_name == "write_file":
            if "Permission denied" in error:
                hint = "提示：权限不足，无法写入该路径。请检查目录权限或尝试其他路径。"
            elif "No such file or directory" in error:
                hint = "提示：目标目录不存在。请先创建目录或检查路径是否正确。"
        
        elif tool_name == "execute_command":
            if "timed out" in error.lower():
                hint = "提示：命令执行超时。可以通过 timeout 参数增大超时时间，或将命令拆分为更小的步骤。"
            elif result.get("returncode") == 127 or "command not found" in (result.get("stderr", "") + error).lower():
                hint = "提示：命令未找到，可能未安装。请确认命令名称正确，或尝试用 execute_command 检查是否已安装（如 which <command>）。"
            elif result.get("returncode", 0) != 0:
                stderr = result.get("stderr", "")
                hint = f"提示：命令返回非零退出码 {result.get('returncode')}。请查看 stderr 输出分析失败原因，然后修正命令或参数后重试。"
        
        # 通用 fallback：没有匹配到特定模式的失败
        if not hint:
            hint = "提示：工具调用失败。请检查参数是否正确，或尝试用其他方式完成任务。"
        
        # 返回新字典，不修改原始 result（避免副作用污染 tool_end 事件）
        return {**result, "hint": hint}

    # 代码文件扩展名集合（修改这些文件后触发自动测试）
    CODE_FILE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.rs', '.go', '.java', '.kt', '.kts',
        '.c', '.cpp', '.h', '.hpp', '.cs',
        '.rb', '.php', '.swift', '.m',
    }

    # 测试框架 → 测试命令映射
    TEST_COMMANDS = {
        'pytest': 'python -m pytest --tb=short -q',
        'tox': 'python -m pytest --tb=short -q',  # tox 项目也用 pytest 快速验证
        'npm': 'npm test',
        'yarn': 'yarn test',
        'cargo': 'cargo test',
        'go': 'go test ./...',
        'maven': 'mvn test -q',
        'gradle': 'gradle test',
    }

    # 自动测试超时秒数
    AUTO_TEST_TIMEOUT = 60

    @staticmethod
    def _is_code_file(path: str) -> bool:
        """判断文件路径是否为代码文件（根据扩展名）。

        Args:
            path: 文件路径

        Returns:
            True 如果是代码文件，False 否则
        """
        _, ext = os.path.splitext(path)
        return ext.lower() in Agent.CODE_FILE_EXTENSIONS

    def _get_test_command(self) -> Optional[str]:
        """根据项目检测结果确定测试命令。

        优先使用检测到的测试框架，回退到检测到的包管理器。
        如果无法确定，返回 None。

        Returns:
            测试命令字符串，或 None
        """
        project_info = detect_project_info(os.getcwd())

        # 优先：已检测到的测试框架
        for fw in project_info.get('test_frameworks', []):
            if fw in self.TEST_COMMANDS:
                return self.TEST_COMMANDS[fw]

        # 回退：根据包管理器推断
        for pm in project_info.get('package_managers', []):
            if pm in self.TEST_COMMANDS:
                return self.TEST_COMMANDS[pm]

        # 最终回退：如果检测到 Python 语言，默认用 pytest
        if 'Python' in project_info.get('languages', []):
            return self.TEST_COMMANDS['pytest']

        return None

    def _run_auto_test(self) -> Optional[Dict[str, Any]]:
        """运行项目测试并返回结果。

        Returns:
            测试结果字典 {"success": bool, "command": str, "stdout": str, "stderr": str,
            "returncode": int}，或 None 如果无法确定测试命令
        """
        cmd = self._get_test_command()
        if not cmd:
            return None

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=os.getcwd(),
                capture_output=True,
                text=True,
                timeout=self.AUTO_TEST_TIMEOUT,
            )
            return {
                "success": result.returncode == 0,
                "command": cmd,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "command": cmd,
                "stdout": "",
                "stderr": f"自动测试超时（{self.AUTO_TEST_TIMEOUT}s）",
                "returncode": -1,
            }
        except Exception as e:
            return {
                "success": False,
                "command": cmd,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
            }

    async def _process_tool_calls(self, tool_calls: List[ToolCallRequest], messages: List[Dict[str, Any]]):
        """执行工具调用列表并生成事件流。
        
        这是 prompt() 和 prompt_stream() 共享的工具执行循环。
        逐个执行工具调用，处理中断、自动测试、错误增强，并将结果追加到消息列表。
        
        Yields:
            tool_start, tool_end, auto_test, interrupted 事件
        
        返回值通过 yield 的 interrupted 事件隐含：如果 yield 了 interrupted 事件，
        调用方应 return（不继续循环）。
        """
        for tc in tool_calls:
            # 通知前端工具开始执行
            yield {"type": "tool_start", "tool_name": tc.name, "args": tc.arguments, "tool_call_id": tc.id}

            # 执行工具（可被 Ctrl+C 中断）
            try:
                result = self._execute_tool_call(tc)
                # MCP 工具返回特殊标记，需要在 async 上下文中完成实际调用
                if result.get("_mcp_pending"):
                    client = self._mcp_tool_map[tc.name]
                    result = await client.call_tool(tc.name, tc.arguments)
            except KeyboardInterrupt:
                # 工具执行被中断，需要清理对话历史中不完整的 tool_calls 组
                # 可能已有 assistant(tool_calls) + 若干 tool 结果消息，全部删除
                while self.conversation_history and self.conversation_history[-1].get("role") in ("assistant", "tool"):
                    self.conversation_history.pop()
                yield {"type": "interrupted", "message": f"工具 {tc.name} 执行被中断"}
                return

            # 通知前端工具执行完成（使用原始结果，不含 hint）
            yield {"type": "tool_end", "tool_name": tc.name, "tool_call_id": tc.id, "result": result}

            # 自动测试：代码文件被成功修改后，运行项目测试
            auto_test_info = None
            if (self.auto_test
                    and tc.name in ("write_file", "edit_file")
                    and result.get("success")
                    and self._is_code_file(tc.arguments.get("path", ""))):
                test_result = self._run_auto_test()
                if test_result is not None:
                    auto_test_info = test_result
                    yield {"type": "auto_test", "result": test_result}

            # 智能错误增强：为失败结果附加 hint 引导 LLM 重试
            fail_count = self._edit_fail_counts.get(tc.arguments.get("path", ""), 0) if tc.name == "edit_file" else 0
            enriched = self._enrich_tool_error(tc.name, result, fail_count=fail_count)

            # 如果有自动测试结果，附加到工具结果中让 LLM 知晓
            # 注意：_enrich_tool_error 成功时返回原始 result 引用，
            # 必须浅拷贝后再附加 auto_test，避免污染 tool_end 事件中的 result
            if auto_test_info is not None:
                enriched = {**enriched}  # 浅拷贝，断开与 result 的引用
                test_summary = f"✅ 测试通过" if auto_test_info["success"] else f"❌ 测试失败（退出码 {auto_test_info['returncode']}）"
                # 截取测试输出的最后部分（避免过长）
                test_output = auto_test_info.get("stdout", "") or ""
                test_stderr = auto_test_info.get("stderr", "") or ""
                if len(test_output) > 1000:
                    test_output = "...\n" + test_output[-1000:]
                if len(test_stderr) > 500:
                    test_stderr = "...\n" + test_stderr[-500:]
                enriched["auto_test"] = {
                    "summary": test_summary,
                    "command": auto_test_info["command"],
                    "stdout": test_output,
                    "stderr": test_stderr,
                    "success": auto_test_info["success"],
                }

            enriched_str = json.dumps(enriched, ensure_ascii=False, default=str)

            # 将工具结果追加到消息列表（使用增强后的结果）
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": enriched_str,
            }
            messages.append(tool_msg)
            self.conversation_history.append(tool_msg)

    async def _handle_context_check(self, total_usage: Usage):
        """检查上下文使用率并在必要时自动 compact。
        
        使用三层记忆的结构化增量摘要（Anchored Iterative Summarization）：
        - 旧消息 → 增量合并到 working_summary（中期记忆）
        - 最近消息保留完整（短期记忆）
        - 摘要使用结构化 4 字段格式（intent/changes/decisions/next_steps）
        
        这是 prompt() 和 prompt_stream() 共享的上下文管理逻辑。
        
        Yields:
            context_warning 或 auto_compact 事件
        """
        context_status = self._check_context_usage()
        if context_status == "critical":
            # 尝试自动 compaction（结构化增量摘要）
            if len(self.conversation_history) > self.MIN_MESSAGES_TO_COMPACT:
                old_messages = self.conversation_history[:-self.DEFAULT_COMPACT_KEEP_RECENT]
                if old_messages:
                    try:
                        # 构建增量摘要 prompt（首次 vs 增量合并）
                        summary_prompt = self.memory.build_compaction_prompt(old_messages)
                        summary_response = self.client.chat.completions.create(
                            model=self.model,
                            max_tokens=self.SUMMARY_MAX_TOKENS,
                            messages=summary_prompt,
                        )
                        summary_text = summary_response.choices[0].message.content or "(无摘要)"
                        # 统计摘要生成的 token
                        if summary_response.usage:
                            total_usage.input += summary_response.usage.prompt_tokens
                            total_usage.output += summary_response.usage.completion_tokens
                        # 解析结构化摘要
                        new_summary = MemoryManager.parse_structured_summary(summary_text)
                        # 执行 compaction（使用结构化摘要消息替代旧的纯文本摘要）
                        compact_result = self.memory.compact_with_summary(
                            self.conversation_history, new_summary, self.DEFAULT_COMPACT_KEEP_RECENT
                        )
                        if compact_result["compacted"]:
                            self.conversation_history = compact_result["new_history"]
                            # 只在 compact 成功后才更新中期记忆，避免数据不一致
                            self.memory.update_working_summary(new_summary, len(old_messages))
                            pct = self._context_pct()
                            removed = compact_result["removed"]
                            kept = compact_result["kept"]
                            msg = (
                                f"上下文使用率 {pct}%，已自动压缩对话："
                                f"移除 {removed} 条旧消息，"
                                f"保留 {kept} 条最近消息（结构化摘要）"
                            )
                            yield {
                                "type": "auto_compact",
                                "removed": removed,
                                "kept": kept,
                                "message": msg,
                            }
                    except Exception:
                        # 自动 compaction 失败，降级为警告
                        yield {"type": "context_warning", "message": self._context_warning_message("自动压缩失败。建议使用 /compact 手动压缩或 /clear 清除对话。")}
                else:
                    # 没有足够旧消息，降级为警告
                    yield {"type": "context_warning", "message": self._context_warning_message("接近上限。建议使用 /compact 压缩或 /clear 清除对话。")}
            else:
                # 对话太短无法 compact，降级为警告
                yield {"type": "context_warning", "message": self._context_warning_message("接近上限。建议使用 /clear 清除对话。")}
        elif context_status == "warning":
            yield {"type": "context_warning", "message": self._context_warning_message("建议使用 /compact 压缩对话释放空间。")}

    def _execute_tool_call(self, tool_call: ToolCallRequest) -> Dict[str, Any]:
        """根据 ToolCallRequest 分发执行对应的工具，返回结果"""
        name = tool_call.name
        args = tool_call.arguments

        try:
            if name == "read_file":
                return self.tools.read_file(args["path"])
            elif name == "write_file":
                path = args["path"]
                result = self.tools.write_file(path, args["content"])
                if result.get("success"):
                    # old_content 由 tools.write_file 返回，避免双重读取文件
                    self.tools.record_undo(path, result.get("old_content"))
                    # 从返回结果中移除 old_content，不暴露给 LLM
                    result.pop("old_content", None)
                return result
            elif name == "edit_file":
                path = args["path"]
                result = self.tools.edit_file(path, args["old_content"], args["new_content"])
                if result.get("success"):
                    # old_content_full 由 tools.edit_file 返回，避免双重读取文件
                    self.tools.record_undo(path, result.get("old_content_full"))
                    # 从返回结果中移除 old_content_full，不暴露给 LLM
                    result.pop("old_content_full", None)
                    # 成功：清零该文件的连续失败计数
                    self._edit_fail_counts.pop(path, None)
                else:
                    # 失败：递增该文件的连续失败计数
                    self._edit_fail_counts[path] = self._edit_fail_counts.get(path, 0) + 1
                return result
            elif name == "list_files":
                return self.tools.list_files(args.get("path", "."))
            elif name == "execute_command":
                command = args["command"]
                # 权限检查：危险命令需要确认
                danger_reason = self._is_dangerous_command(command)
                if danger_reason:
                    if self.confirm_callback is None:
                        return {"success": False, "error": f"危险命令已拒绝：{danger_reason}。命令：{command}"}
                    if not self.confirm_callback(command, danger_reason):
                        return {"success": False, "error": f"用户拒绝执行危险命令：{command}"}
                return self.tools.execute_command(command, args.get("cwd"), args.get("timeout"))
            elif name == "search_files":
                return self.tools.search_files(args["pattern"], args.get("path", "."))
            elif name == "web_search":
                return self.tools.web_search(args["query"], args.get("max_results", 5))
            elif name in self._mcp_tool_map:
                # MCP 工具：返回特殊标记，由 _process_tool_calls (async) 完成实际调用
                return {"_mcp_pending": True, "tool_name": name, "arguments": args}
            else:
                return {"success": False, "error": f"Unknown tool: {name}"}
        except (KeyError, TypeError) as e:
            return {"success": False, "error": f"Missing required argument {e} for tool '{name}'"}

    @staticmethod
    def _strip_code_blocks(content: str) -> str:
        """剥离 Markdown 代码块（``` ... ```）和行内代码（`...`）。
        
        返回剥离后的纯文本，用于后续检测。
        先处理围栏代码块（可能跨多行），再处理行内代码。
        """
        # 1. 移除围栏代码块（``` 或 ~~~，可选语言标记）
        stripped = re.sub(r'(`{3,}|~{3,}).*?\1', '', content, flags=re.DOTALL)
        # 2. 移除行内代码（`...`）
        stripped = re.sub(r'`[^`]+`', '', stripped)
        return stripped

    @staticmethod
    def _detect_fake_tool_calls(content: str) -> bool:
        """检测 LLM 是否在文本中伪装了工具调用（而非通过 function calling 执行）。
        
        常见模式：
        - read_file("path") 或 read_file('path')
        - execute_command("cmd") 或 execute_command('''cmd''')
        - write_file("path", "content")
        - edit_file("path", "old", "new")
        
        排除误报：
        - Markdown 围栏代码块（``` ... ```）内的匹配
        - 行内代码（`...`）内的匹配
        """
        # 先剥离代码块和行内代码，只检查纯文本部分
        plain_text = Agent._strip_code_blocks(content)

        # 匹配常见的伪工具调用模式
        fake_patterns = [
            r'\bread_file\s*\(',
            r'\bwrite_file\s*\(',
            r'\bedit_file\s*\(',
            r'\bexecute_command\s*\(',
            r'\blist_files\s*\(',
            r'\bsearch_files\s*\(',
            r'\bweb_search\s*\(',
        ]
        for pattern in fake_patterns:
            if re.search(pattern, plain_text):
                return True
        return False

    async def prompt_stream(self, user_input: str):
        """发送提示并通过流式事件返回结果，支持 function calling 工具循环。
        
        逐 token 输出文本，实时响应。text_update 事件会频繁 yield 小片段（delta）。
        
        流式处理的关键特点：
        - 文本内容逐 chunk 到达，每个 chunk yield 一个 text_update 事件
        - 工具调用的 arguments 分段到达，需要累积后再解析
        - usage 信息在最后一个 chunk 中（需要 stream_options.include_usage=True）
        """
        start_time = time.monotonic()
        self.refresh_system_prompt()

        # LLM 路由：根据用户输入复杂度选择模型
        routed_model = self.router.route(
            user_input, default_model=self.model,
            history_len=len(self.conversation_history),
        )
        # 通知调用方路由结果（仅路由启用且选了不同模型时）
        if self.router.enabled and routed_model != self.model:
            yield {
                "type": "route",
                "model": routed_model,
                "complexity": self.router.last_complexity.value if self.router.last_complexity else None,
                "default_model": self.model,
            }

        # 将用户输入追加到对话历史
        self.conversation_history.append({"role": "user", "content": user_input})

        # 截断过长的对话历史
        trimmed = self._trim_history()
        if trimmed > 0:
            yield {"type": "warning", "message": f"对话历史过长，已自动丢弃最早的 {trimmed} 条消息。使用 /clear 可手动清除全部历史。"}

        # 构建完整消息列表
        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation_history

        total_usage = Usage()
        max_iterations = 30
        fake_tool_call_retries = 0
        max_fake_retries = 2

        for _ in range(max_iterations):
            try:
                stream = self.client.chat.completions.create(
                    model=routed_model,
                    max_tokens=self.max_tokens,
                    messages=messages,
                    tools=self.tool_definitions,
                    tool_choice="auto",
                    stream=True,
                    stream_options={"include_usage": True},
                )
            except (KeyboardInterrupt, Exception) as e:
                event_type, message = self._classify_api_error(e)
                yield {"type": event_type, "message": message}
                return

            # 从流式响应中累积完整结果
            collected_content = ""
            collected_reasoning = ""
            # tool_calls 累积：{index: {"id": ..., "name": ..., "arguments": ...}}
            collected_tool_calls: Dict[int, Dict[str, str]] = {}
            finish_reason = None
            chunk_usage = {}

            try:
                for chunk in stream:
                    if not chunk.choices:
                        # 最后一个 chunk 可能只有 usage，没有 choices
                        if chunk.usage:
                            chunk_usage = {
                                "prompt_tokens": chunk.usage.prompt_tokens or 0,
                                "completion_tokens": chunk.usage.completion_tokens or 0,
                                "total_tokens": chunk.usage.total_tokens or 0,
                            }
                        continue

                    delta = chunk.choices[0].delta
                    chunk_finish_reason = chunk.choices[0].finish_reason

                    if chunk_finish_reason:
                        finish_reason = chunk_finish_reason

                    # 文本内容 delta
                    if delta.content:
                        collected_content += delta.content
                        yield {"type": "text_update", "delta": delta.content}

                    # reasoning_content (DeepSeek-R1 等)
                    reasoning_delta = getattr(delta, "reasoning_content", None)
                    if reasoning_delta:
                        collected_reasoning += reasoning_delta

                    # 工具调用 delta
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in collected_tool_calls:
                                collected_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc_delta.id:
                                collected_tool_calls[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    collected_tool_calls[idx]["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    collected_tool_calls[idx]["arguments"] += tc_delta.function.arguments

                    # 检查流 chunk 中的 usage（某些 API 在最后一个 choice chunk 附带 usage）
                    if chunk.usage:
                        chunk_usage = {
                            "prompt_tokens": chunk.usage.prompt_tokens or 0,
                            "completion_tokens": chunk.usage.completion_tokens or 0,
                            "total_tokens": chunk.usage.total_tokens or 0,
                        }
            except KeyboardInterrupt:
                yield {"type": "interrupted", "message": "用户中断了流式响应"}
                return

            # 累计 token 用量
            total_usage.input += chunk_usage.get("prompt_tokens", 0)
            total_usage.output += chunk_usage.get("completion_tokens", 0)

            # 更新最近一次 prompt_tokens
            prompt_tokens = chunk_usage.get("prompt_tokens", 0)
            if prompt_tokens > 0:
                self._last_prompt_tokens = prompt_tokens

            # 输出 reasoning（如果有）
            if collected_reasoning:
                yield {"type": "reasoning", "content": collected_reasoning}

            # 解析工具调用
            tool_calls = []
            for idx in sorted(collected_tool_calls.keys()):
                tc_data = collected_tool_calls[idx]
                try:
                    arguments = json.loads(tc_data["arguments"])
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                tool_calls.append(ToolCallRequest(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=arguments,
                ))

            has_tool_calls = len(tool_calls) > 0

            # 如果没有工具调用
            if not has_tool_calls:
                if (collected_content
                        and self._detect_fake_tool_calls(collected_content)
                        and fake_tool_call_retries < max_fake_retries):
                    fake_tool_call_retries += 1
                    yield {"type": "text_update", "delta": f"\n\n⚠️ 检测到文本中包含伪工具调用（第 {fake_tool_call_retries}/{max_fake_retries} 次重试），正在要求模型使用真正的 function calling 重新执行...\n"}
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": collected_content,
                    })
                    reminder_msg = {
                        "role": "user",
                        "content": "你刚才在文本中描述了工具调用（如 read_file(...)、execute_command(...)、write_file(...) 等），但并没有真正执行它们。请不要在文本中写伪代码来描述工具操作。你必须通过 function calling 机制发起真正的工具调用来执行这些操作。现在请重新执行你刚才描述的操作。"
                    }
                    messages.append(reminder_msg)
                    self.conversation_history.append(reminder_msg)
                    continue

                # 正常结束
                if fake_tool_call_retries >= max_fake_retries and collected_content and self._detect_fake_tool_calls(collected_content):
                    yield {"type": "text_update", "delta": "\n\n⚠️ 模型多次未能使用 function calling，已放弃重试。上述操作未被实际执行。\n"}
                self.conversation_history.append({
                    "role": "assistant",
                    "content": collected_content or None,
                })

                # 检查上下文使用率（共享方法）
                async for event in self._handle_context_check(total_usage):
                    yield event

                elapsed = time.monotonic() - start_time
                yield {"type": "agent_end", "usage": total_usage, "elapsed": round(elapsed, 2)}
                return

            # 有工具调用
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if collected_content:
                assistant_msg["content"] = collected_content
            else:
                assistant_msg["content"] = None
            assistant_msg["tool_calls"] = [
                tc.to_openai_tool_call() for tc in tool_calls
            ]
            messages.append(assistant_msg)
            self.conversation_history.append(assistant_msg)

            # 逐个执行工具调用（共享方法）
            async for event in self._process_tool_calls(tool_calls, messages):
                yield event
                if event["type"] == "interrupted":
                    return

        yield {"type": "error", "message": f"工具调用循环超过最大次数 ({max_iterations})"}

    def clear_conversation(self):
        self.conversation_history = []
        self._edit_fail_counts = {}
        self._last_prompt_tokens = 0
        self._spec_prompt = None
        self._replay_queue = None
        self.memory.working_summary = WorkingSummary()
        self.router.stats = {k: 0 for k in self.router.stats}

    # 默认 compact 保留最近的消息数
    DEFAULT_COMPACT_KEEP_RECENT = 10
    # 至少需要多少条消息才值得压缩
    MIN_MESSAGES_TO_COMPACT = 6

    def export_session(self) -> Dict[str, Any]:
        """将当前会话状态导出为可序列化的字典。
        
        Returns:
            包含 model、conversation_history、memory、version、timestamp 的字典。
            如果设置了 system_prompt_override，也会一并导出。
        """
        from . import __version__
        data = {
            "version": __version__,
            "model": self.model,
            "conversation_history": list(self.conversation_history),
            "memory": self.memory.export_state(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self.system_prompt_override is not None:
            data["system_prompt_override"] = self.system_prompt_override
        return data

    def import_session(self, data: Dict[str, Any]) -> None:
        """从字典恢复会话状态。
        
        Args:
            data: 由 export_session() 生成的字典
        """
        self.conversation_history = data.get("conversation_history", [])
        self._edit_fail_counts = {}
        self._last_prompt_tokens = 0
        self._spec_prompt = None
        self._replay_queue = None
        self.tools._undo_stack.clear()
        self.router.stats = {k: 0 for k in self.router.stats}
        if "model" in data:
            self.model = data["model"]
        # 恢复自定义 system prompt（无该字段时重置为 None，防止旧值泄漏）
        self.system_prompt_override = data.get("system_prompt_override")
        # 恢复记忆状态（始终调用 import_state，确保旧会话文件无 memory 字段时也重置）
        self.memory.import_state(data.get("memory") or {})
        # 刷新 system prompt（反映 system_prompt_override 和 archival memory 的变化）
        self.refresh_system_prompt()

    def save_session(self, filepath: str) -> Dict[str, Any]:
        """将当前会话保存到 JSON 文件。
        
        使用 write-to-temp-then-rename 原子写入模式，防止崩溃时丢失已有会话文件。
        
        Args:
            filepath: 保存路径
            
        Returns:
            {"success": True, "path": filepath} 或 {"success": False, "error": ...}
        """
        import tempfile
        try:
            dir_name = os.path.dirname(filepath) or "."
            os.makedirs(dir_name, exist_ok=True)
            data = self.export_session()
            # 原子写入：先写临时文件，再 rename 替换目标
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, filepath)
            except BaseException:
                # 写入或 rename 失败时清理临时文件
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return {"success": True, "path": filepath}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_session(self, filepath: str) -> Dict[str, Any]:
        """从 JSON 文件加载会话。
        
        Args:
            filepath: 文件路径
            
        Returns:
            {"success": True, "model": ..., "message_count": ...} 或 {"success": False, "error": ...}
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.import_session(data)
            return {
                "success": True,
                "model": self.model,
                "message_count": len(self.conversation_history),
                "path": filepath,
            }
        except FileNotFoundError:
            return {"success": False, "error": f"文件不存在：{filepath}"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"无效的 JSON 格式：{e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== SubAgent 支持方法（Issue #6） ====================
    
    async def delegate_task(self, task: str, role: str = "worker", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """委派任务给 SubAgent 执行（异步方法）。
        
        创建一个新的 SubAgent，继承父 Agent 的配置和凭证，
        但拥有独立的对话历史和状态。SubAgent 可以访问共享的只读上下文。
        
        Args:
            task: 要委派的任务描述
            role: SubAgent 的角色（如 "worker", "specialist", "reviewer"）
            context: 额外的上下文信息（可选）
        
        Returns:
            {
                "success": bool,
                "output": str,  # SubAgent 的最终输出
                "error": Optional[str],
                "conversation_length": int,  # SubAgent 的对话长度
                "usage": Optional[Usage],  # Token 用量
            }
        """
        # 创建 SubAgent
        subagent = Agent(
            api_key=self.client.api_key,
            model=self.model,
            base_url=self.client.base_url if hasattr(self.client, 'base_url') else None,
            max_history=self.max_history,
            max_context_tokens=self.max_context_tokens,
            max_tokens=self.max_tokens,
            router_config=self.router.config if hasattr(self.router, 'config') else None,
            parent=self,  # 设置父子关系
        )
        
        # 继承父 Agent 的配置
        subagent.skills = self.skills
        subagent.auto_test = False  # SubAgent 默认禁用自动测试，避免重复运行
        subagent.confirm_callback = self.confirm_callback
        
        # 设置共享上下文（Context Lake Pattern）
        if context:
            subagent.shared_context.update(context)
        subagent.shared_context.update(self.shared_context)
        
        # 构建 SubAgent 专用 system prompt
        subagent_prompt = self._build_subagent_prompt(task, role)
        subagent.with_system_prompt(subagent_prompt)
        
        # 注册 SubAgent
        self.subagents.append(subagent)
        
        # 执行任务（异步执行，收集所有事件）
        result = {
            "success": False,
            "output": "",
            "error": None,
            "conversation_length": 0,
            "usage": None,
        }
        
        try:
            collected_output = []
            total_usage = None
            
            async for event in subagent.prompt_stream(task):
                if event["type"] == "text_update":
                    collected_output.append(event["delta"])
                elif event["type"] == "agent_end":
                    total_usage = event.get("usage")
                elif event["type"] == "error":
                    result["error"] = event["message"]
                    return result
            
            # 执行成功
            result["success"] = True
            result["output"] = "".join(collected_output)
            result["usage"] = total_usage
            result["conversation_length"] = len(subagent.conversation_history)
        
        except Exception as e:
            result["error"] = f"SubAgent 执行失败：{str(e)}"
        
        return result
    
    def _build_subagent_prompt(self, task: str, role: str) -> str:
        """构建 SubAgent 专用 system prompt。
        
        基于 Narrow Task Scoping 原则（2026 最佳实践）：
        每个 SubAgent 应有清晰定义的、狭窄的任务范围。
        
        Args:
            task: 任务描述
            role: 角色名称
        
        Returns:
            SubAgent 专用 system prompt
        """
        shared_context_summary = ""
        if self.shared_context:
            items = []
            for key, value in self.shared_context.items():
                if isinstance(value, (str, int, float, bool)):
                    items.append(f"  - {key}: {value}")
                elif isinstance(value, dict):
                    items.append(f"  - {key}: {len(value)} 个字段")
                elif isinstance(value, list):
                    items.append(f"  - {key}: {len(value)} 个元素")
                else:
                    items.append(f"  - {key}: {type(value).__name__}")
            shared_context_summary = "\n".join(items)
        
        prompt = f"""你是一个 SubAgent，专注于完成一个特定的子任务。

**你的角色：** {role}

**你的任务：**
{task}

**重要原则：**
1. 专注完成上述任务，不要做无关的事情
2. 使用必要的工具（read_file、write_file、execute_command 等）
3. 如果遇到问题，报告错误并说明原因
4. 完成后，简要总结你做了什么

"""
        
        if shared_context_summary:
            prompt += f"""**你可以访问的共享上下文：**
{shared_context_summary}

"""
        
        prompt += """**现在开始执行任务。**"""
        
        return prompt
    
    def get_subagent_results(self) -> List[Dict[str, Any]]:
        """获取所有 SubAgent 的结果摘要。
        
        Returns:
            SubAgent 结果列表，每个元素包含：
            {
                "index": int,
                "conversation_length": int,
                "last_message": str,  # SubAgent 最后一条消息内容（截断前 200 字符）
            }
        """
        results = []
        for i, subagent in enumerate(self.subagents):
            last_msg = ""
            if subagent.conversation_history:
                last = subagent.conversation_history[-1]
                content = last.get("content", "")
                if isinstance(content, str):
                    last_msg = content[:200] + ("..." if len(content) > 200 else "")
            
            results.append({
                "index": i,
                "conversation_length": len(subagent.conversation_history),
                "last_message": last_msg,
            })
        
        return results
    
    # ── Team 协作方法（Issue #7）──────────────────────────────────
    
    def create_team(self, config: 'TeamConfig') -> List['Agent']:
        """创建 SubAgent Team（Supervisor 模式）。
        
        基于 TeamConfig 创建指定数量的 SubAgent，每个 SubAgent 有独立的角色
        但共享相同的配置（模型、API key、工具、技能等）。
        
        Args:
            config: TeamConfig 实例（定义 team_size、roles、shared_context）
        
        Returns:
            SubAgent 列表（长度 = config.team_size）
        
        Example:
            >>> from src.models import TeamConfig
            >>> config = TeamConfig(
            ...     team_size=3,
            ...     roles=["researcher", "coder", "reviewer"],
            ...     shared_context={"project": "SimpleAgent"},
            ... )
            >>> team = agent.create_team(config)
            >>> len(team)
            3
        """
        from .models import TeamConfig
        
        if not isinstance(config, TeamConfig):
            raise TypeError(f"config must be TeamConfig instance, got {type(config)}")
        
        team = []
        for i, role in enumerate(config.roles):
            subagent = Agent(
                api_key=self.client.api_key,
                model=self.model,
                base_url=self.client.base_url if hasattr(self.client, 'base_url') else None,
                max_history=self.max_history,
                max_context_tokens=self.max_context_tokens,
                max_tokens=self.max_tokens,
                router_config=self.router.config if hasattr(self.router, 'config') else None,
                parent=self,
            )
            
            subagent.skills = self.skills
            subagent.auto_test = False
            subagent.confirm_callback = self.confirm_callback
            
            subagent.shared_context.update(config.shared_context)
            subagent.shared_context["team_index"] = i
            subagent.shared_context["team_role"] = role
            subagent.shared_context["team_size"] = config.team_size
            
            role_prompt = self._build_team_member_prompt(role, i, config.team_size)
            subagent.with_system_prompt(role_prompt)
            
            self.subagents.append(subagent)
            team.append(subagent)
        
        return team
    
    def _build_team_member_prompt(self, role: str, index: int, team_size: int) -> str:
        """构建 Team 成员专用 system prompt。"""
        lines = []
        lines.append("你是一个 Team Agent 成员，专注于完成特定角色的任务。")
        lines.append("")
        lines.append("**你的身份：**")
        lines.append(f"- 角色：{role}")
        lines.append(f"- 编号：Member #{index + 1}/{team_size}")
        lines.append("- 模式：Team 协作（Supervisor 模式）")
        lines.append("")
        lines.append("**你的职责：**")
        lines.append(f"你只负责 \"{role}\" 角色的工作，不要尝试完成其他角色的任务。")
        lines.append(f"Team 中有 {team_size} 个成员，每个人负责不同的部分。")
        lines.append("你的输出会被 Supervisor（父 Agent）汇总，所以请确保输出清晰、完整。")
        lines.append("")
        lines.append("**重要约束：**")
        lines.append(f"1. **专注于你的角色** — 只做 \"{role}\" 应该做的事情")
        lines.append("2. **输出结构化信息** — 使用清晰的格式（Markdown、列表、代码块等）")
        lines.append("3. **不要重复其他成员的工作** — 假设其他角色会完成他们的部分")
        lines.append("4. **直接给出结果** — 不要问\"需要我做什么\"，主动完成你的角色任务")
        lines.append("")
        lines.append("**当前任务：**")
        lines.append("Supervisor 会给你一个具体任务，请根据你的角色完成它。")
        return "\\n".join(lines)
    
    async def coordinate_team(self, team: List['Agent'], tasks: List[str]) -> Dict[str, Any]:
        """协调 Team 执行任务（Supervisor 模式，支持并行）。
        
        Supervisor 分配任务给 Team 成员，收集结果并聚合。
        支持并行执行（asyncio.gather）或顺序执行。
        
        Args:
            team: SubAgent 列表（由 create_team 创建）
            tasks: 任务列表（长度应与 team 一致）
        
        Returns:
            {
                "success": bool,
                "results": List[Dict],
                "aggregated_output": str,
                "total_usage": Usage,
                "elapsed": float,
            }
        """
        import time
        import asyncio
        from .models import Usage
        
        if len(team) != len(tasks):
            return {
                "success": False,
                "error": f"team size ({len(team)}) must match tasks length ({len(tasks)})",
                "results": [],
                "aggregated_output": "",
                "total_usage": Usage(),
                "elapsed": 0.0,
            }
        
        start_time = time.monotonic()
        total_usage = Usage()
        results = []
        
        parallel = team[0].shared_context.get("parallel", True) if team else True
        
        try:
            if parallel:
                async_tasks = [
                    self._execute_team_member(member, task, i)
                    for i, (member, task) in enumerate(zip(team, tasks))
                ]
                results = await asyncio.gather(*async_tasks, return_exceptions=True)
                
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        results[i] = {
                            "success": False,
                            "index": i,
                            "role": team[i].shared_context.get("team_role", "unknown"),
                            "output": "",
                            "error": f"Exception: {str(result)}",
                            "usage": Usage(),
                        }
            else:
                for i, (member, task) in enumerate(zip(team, tasks)):
                    result = await self._execute_team_member(member, task, i)
                    results.append(result)
            
            for result in results:
                if result.get("success") and result.get("usage"):
                    usage = result["usage"]
                    total_usage.input += usage.input
                    total_usage.output += usage.output
            
            aggregated_output = self._aggregate_team_results(results)
            
            elapsed = time.monotonic() - start_time
            
            return {
                "success": True,
                "results": results,
                "aggregated_output": aggregated_output,
                "total_usage": total_usage,
                "elapsed": elapsed,
            }
        
        except Exception as e:
            elapsed = time.monotonic() - start_time
            return {
                "success": False,
                "error": f"Team coordination failed: {str(e)}",
                "results": results,
                "aggregated_output": "",
                "total_usage": total_usage,
                "elapsed": elapsed,
            }
    
    async def _execute_team_member(self, member: 'Agent', task: str, index: int) -> Dict[str, Any]:
        """执行单个 Team 成员的任务。"""
        from .models import Usage
        
        role = member.shared_context.get("team_role", "unknown")
        result = {
            "success": False,
            "index": index,
            "role": role,
            "output": "",
            "error": None,
            "usage": Usage(),
        }
        
        try:
            collected_output = []
            total_usage = None
            
            async for event in member.prompt_stream(task):
                if event["type"] == "text_update":
                    collected_output.append(event["delta"])
                elif event["type"] == "agent_end":
                    total_usage = event.get("usage")
                elif event["type"] == "error":
                    result["error"] = event["message"]
                    return result
            
            result["success"] = True
            result["output"] = "".join(collected_output)
            result["usage"] = total_usage if total_usage else Usage()
        
        except Exception as e:
            result["error"] = f"Member execution failed: {str(e)}"
        
        return result
    
    def _aggregate_team_results(self, results: List[Dict[str, Any]]) -> str:
        """聚合 Team 成员的输出为单一报告。"""
        lines = []
        lines.append("# Team 协作结果")
        lines.append("")
        
        success_count = sum(1 for r in results if r.get("success"))
        lines.append(f"**完成情况：** {success_count}/{len(results)} 个成员成功完成任务")
        lines.append("")
        
        for result in results:
            index = result.get("index", -1)
            role = result.get("role", "unknown")
            success = result.get("success", False)
            output = result.get("output", "")
            error = result.get("error")
            
            status = "✅" if success else "❌"
            lines.append(f"## {status} Member #{index + 1}: {role}")
            lines.append("")
            
            if success and output:
                lines.append(output)
            elif error:
                lines.append(f"**错误：** {error}")
            else:
                lines.append("*（无输出）*")
            
            lines.append("")
            lines.append("---")
            lines.append("")
        
        return "\\n".join(lines)
