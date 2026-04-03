"""
Agent 核心逻辑模块
"""

import json
import re
from typing import List, Dict, Any, Optional
from openai import OpenAI

from .models import Usage, SkillSet, ToolCallRequest, LLMResponse
from .tools import ToolExecutor, TOOL_DEFINITIONS
from .prompt import build_system_prompt
from .exceptions import classify_exception, format_error_message, SimpleAgentException


class Agent:
    """SimpleAgent 核心类"""

    def __init__(self, api_key: str, model: str = "Pro/zai-org/GLM-5", base_url: Optional[str] = None):
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        self.model = model
        self.system_prompt_override: Optional[str] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.skills = SkillSet()
        self.tools: ToolExecutor = ToolExecutor()
        self.tool_definitions = TOOL_DEFINITIONS
        self.session_usage = Usage()  # 会话累计 token 用量
        self.refresh_system_prompt()

    def refresh_system_prompt(self) -> 'Agent':
        self.system_prompt = build_system_prompt(self.skills, self.system_prompt_override)
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

    def _parse_llm_response(self, response) -> LLMResponse:
        """将 OpenAI API 原始响应解析为 LLMResponse 数据类"""
        choice = response.choices[0]
        message = choice.message

        # 解析工具调用
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments,
                ))

        # 解析 usage
        usage_dict = {}
        if response.usage:
            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        # 解析 reasoning_content（DeepSeek-R1 / Kimi 等）
        reasoning_content = getattr(message, 'reasoning_content', None)

        # 解析 thinking_blocks（Anthropic）
        thinking_blocks = getattr(message, 'thinking_blocks', None)

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage_dict,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks,
        )

    def _execute_tool_call(self, tool_call: ToolCallRequest) -> Dict[str, Any]:
        """根据 ToolCallRequest 分发执行对应的工具，返回结果"""
        name = tool_call.name
        args = tool_call.arguments

        if name == "read_file":
            return self.tools.read_file(args["path"])
        elif name == "write_file":
            return self.tools.write_file(args["path"], args["content"])
        elif name == "edit_file":
            return self.tools.edit_file(
                args["path"], 
                args["old_content"], 
                args["new_content"],
                args.get("preview", False)
            )
        elif name == "list_files":
            return self.tools.list_files(args.get("path", "."))
        elif name == "execute_command":
            return self.tools.execute_command(args["command"], args.get("cwd"))
        elif name == "search_files":
            return self.tools.search_files(args["pattern"], args.get("path", "."))
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    @staticmethod
    def _detect_fake_tool_calls(content: str) -> bool:
        """检测 LLM 是否在文本中伪装了工具调用（而非通过 function calling 执行）。

        常见模式：
        - read_file("path") 或 read_file('path')
        - execute_command("cmd") 或 execute_command('''cmd''')
        - write_file("path", "content")
        - edit_file("path", "old", "new")
        """
        # 匹配常见的伪工具调用模式
        fake_patterns = [
            r'\bread_file\s*\(',
            r'\bwrite_file\s*\(',
            r'\bedit_file\s*\(',
            r'\bexecute_command\s*\(',
            r'\blist_files\s*\(',
            r'\bsearch_files\s*\(',
        ]
        for pattern in fake_patterns:
            if re.search(pattern, content):
                return True
        return False

    async def prompt(self, user_input: str):
        """发送提示并通过事件流返回结果，支持 function calling 工具循环"""
        self.refresh_system_prompt()

        # 将用户输入追加到对话历史
        self.conversation_history.append({"role": "user", "content": user_input})

        # 构建完整消息列表
        messages = [{"role": "system", "content": self.system_prompt}] + self.conversation_history

        total_usage = Usage()
        max_iterations = 20  # 防止无限循环

        for _ in range(max_iterations):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=10240 * 2,
                    messages=messages,
                    tools=self.tool_definitions,
                    tool_choice="auto",
                )
            except Exception as e:
                # 使用统一异常分类系统处理 API 错误
                classified = classify_exception(e)
                yield {
                    "type": "error",
                    "message": format_error_message(classified),
                    "recoverable": classified.recoverable
                }
                return

            # 解析响应
            llm_response = self._parse_llm_response(response)

            # 累计 token 用量
            total_usage.input += llm_response.usage.get("prompt_tokens", 0)
            total_usage.output += llm_response.usage.get("completion_tokens", 0)

            # 如果有 reasoning_content，先输出思考过程
            if llm_response.reasoning_content:
                yield {"type": "reasoning", "content": llm_response.reasoning_content}

            # 如果有文本内容，输出
            if llm_response.content:
                yield {"type": "text_update", "delta": llm_response.content}

            # 如果没有工具调用，检查是否在文本中伪装了工具调用
            if not llm_response.has_tool_calls:
                if llm_response.content and self._detect_fake_tool_calls(llm_response.content):
                    # LLM 在文本中描述了工具调用而非真正执行，追加提醒让它重新执行
                    yield {"type": "text_update", "delta": "\n\n⚠️ 检测到文本中包含伪工具调用，正在要求模型使用真正的 function calling 重新执行...\n"}
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": llm_response.content,
                    })
                    reminder_msg = {
                        "role": "user",
                        "content": "你刚才在文本中描述了工具调用（如 read_file(...)、execute_command(...)、write_file(...) 等），但并没有真正执行它们。请不要在文本中写伪代码来描述工具操作。你必须通过 function calling 机制发起真正的工具调用来执行这些操作。现在请重新执行你刚才描述的操作。"
                    }
                    messages.append(reminder_msg)
                    self.conversation_history.append(reminder_msg)
                    continue  # 继续循环，让 LLM 重新生成带 tool_calls 的响应

                # 正常结束对话
                self.conversation_history.append({
                    "role": "assistant",
                    "content": llm_response.content,
                })
                # 累加当次用量到会话统计
                self.session_usage.input += total_usage.input
                self.session_usage.output += total_usage.output
                yield {"type": "agent_end", "usage": total_usage, "session_usage": self.session_usage}
                return

            # 有工具调用：构建 assistant 消息（含 tool_calls）并追加到消息列表
            assistant_msg: Dict[str, Any] = {"role": "assistant"}
            if llm_response.content:
                assistant_msg["content"] = llm_response.content
            else:
                assistant_msg["content"] = None
            assistant_msg["tool_calls"] = [
                tc.to_openai_tool_call() for tc in llm_response.tool_calls
            ]
            messages.append(assistant_msg)
            self.conversation_history.append(assistant_msg)

            # 逐个执行工具调用并收集结果
            for tc in llm_response.tool_calls:
                # 通知前端工具开始执行
                yield {"type": "tool_start", "tool_name": tc.name, "args": tc.arguments, "tool_call_id": tc.id}

                # 执行工具
                result = self._execute_tool_call(tc)
                result_str = json.dumps(result, ensure_ascii=False, default=str)

                # 通知前端工具执行完成
                yield {"type": "tool_end", "tool_name": tc.name, "tool_call_id": tc.id, "result": result}

                # 将工具结果追加到消息列表
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                }
                messages.append(tool_msg)
                self.conversation_history.append(tool_msg)

            # 继续循环，让 LLM 根据工具结果继续生成

        # 超过最大迭代次数
        yield {"type": "error", "message": f"工具调用循环超过最大次数 ({max_iterations})"}

    def clear_conversation(self):
        self.conversation_history = []
        self.session_usage = Usage()  # 重置会话统计