#!/usr/bin/env python3
"""
SimpleAgent — a coding agent that evolves itself.

Started as a Rust project. Now converted to Python without external agent frameworks.

Usage:
  python src/main.py
  OPENAI_BASE_URL=https://api.siliconflow.cn/v1 python src/main.py
  OPENAI_MODEL=Pro/zai-org/GLM-5 python src/main.py
  python src/main.py --model Pro/zai-org/GLM-5
  python src/main.py --skills ./skills

Commands:
  /quit, /exit    Exit the agent
  /clear          Clear conversation history
  /model <name>   Switch model mid-session
"""

import os
import sys
import json
import platform
import asyncio
import argparse
import subprocess
import glob
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from openai import OpenAI
from dotenv import load_dotenv

# ANSI color helpers
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
RED = "\x1b[31m"

# ============================================================
# 工具模块 - 提供文件操作和命令执行功能
# ============================================================

class ToolExecutor:
    """简单的工具执行类"""
    
    @staticmethod
    def read_file(path: str) -> Dict[str, Any]:
        """读取文件内容"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"success": True, "content": content, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}
    
    @staticmethod
    def write_file(path: str, content: str) -> Dict[str, Any]:
        """写入文件内容"""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}
    
    @staticmethod
    def edit_file(path: str, old_content: str, new_content: str) -> Dict[str, Any]:
        """编辑文件内容（替换）"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_content not in content:
                return {"success": False, "error": "Old content not found", "path": path}
            
            new_content_full = content.replace(old_content, new_content)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content_full)
            
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}
    
    @staticmethod
    def list_files(path: str = ".") -> Dict[str, Any]:
        """列出目录内容"""
        try:
            if not os.path.exists(path):
                return {"success": False, "error": "Path does not exist", "path": path}
            
            items = []
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    items.append({"name": item, "type": "directory", "path": item_path})
                else:
                    items.append({"name": item, "type": "file", "path": item_path, 
                                "size": os.path.getsize(item_path)})
            
            return {"success": True, "items": items, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}
    
    @staticmethod
    def execute_command(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """执行 shell 命令"""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=cwd or os.getcwd(),
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out", "command": command}
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}
    
    @staticmethod
    def search_files(pattern: str, path: str = ".") -> Dict[str, Any]:
        """搜索匹配模式的文件"""
        try:
            matches = []
            search_path = os.path.join(path, "**", pattern) if pattern != "." else path
            
            for match in glob.glob(search_path, recursive=True):
                if os.path.isfile(match):
                    matches.append({
                        "path": match, 
                        "size": os.path.getsize(match)
                    })
            
            return {"success": True, "matches": matches, "pattern": pattern}
        except Exception as e:
            return {"success": False, "error": str(e), "pattern": pattern}

def default_tools() -> ToolExecutor:
    """返回默认的工具执行器"""
    return ToolExecutor()

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


# ============================================================
# OpenAI Function Calling 工具定义
# ============================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定路径的文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入指定路径的文件（会覆盖已有内容）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑文件内容，将旧内容替换为新内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的文件路径"
                    },
                    "old_content": {
                        "type": "string",
                        "description": "要被替换的旧内容（必须精确匹配）"
                    },
                    "new_content": {
                        "type": "string",
                        "description": "替换后的新内容"
                    }
                },
                "required": ["path", "old_content", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出指定目录下的文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出内容的目录路径，默认为当前目录",
                        "default": "."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "在 shell 中执行命令",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令"
                    },
                    "cwd": {
                        "type": "string",
                        "description": "命令执行的工作目录（可选）"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "搜索匹配指定模式的文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "文件名匹配模式（支持 glob 通配符，如 *.py）"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索的根目录路径，默认为当前目录",
                        "default": "."
                    }
                },
                "required": ["pattern"]
            }
        }
    }
]

# ============================================================
# LLM 响应数据类
# ============================================================

@dataclass
class ToolCallRequest:
    """LLM 返回的工具调用请求"""
    id: str
    name: str
    arguments: dict[str, Any]
    provider_specific_fields: dict[str, Any] | None = None
    function_provider_specific_fields: dict[str, Any] | None = None

    def to_openai_tool_call(self) -> dict[str, Any]:
        """序列化为 OpenAI 格式的 tool_call。"""
        tool_call: dict[str, Any] = {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }
        if self.provider_specific_fields:
            tool_call["provider_specific_fields"] = self.provider_specific_fields
        if self.function_provider_specific_fields:
            tool_call["function"]["provider_specific_fields"] = self.function_provider_specific_fields
        return tool_call


@dataclass
class LLMResponse:
    """LLM 提供者的响应"""
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None  # Kimi, DeepSeek-R1 等
    thinking_blocks: list[dict] | None = None  # Anthropic extended thinking

    @property
    def has_tool_calls(self) -> bool:
        """检查响应中是否包含工具调用。"""
        return len(self.tool_calls) > 0

# ============================================================
# Agent 核心逻辑
# ============================================================

@dataclass
class Usage:
    input: int = 0
    output: int = 0

@dataclass
class Skill:
    name: str
    description: str
    path: str
    content: str = ""

class SkillSet:
    def __init__(self):
        self.skills: List[Skill] = []
    
    def load(self, skill_dirs: List[str]) -> 'SkillSet':
        for skill_dir in skill_dirs:
            if not os.path.isdir(skill_dir):
                continue
            for item in os.listdir(skill_dir):
                skill_path = os.path.join(skill_dir, item)
                if not os.path.isdir(skill_path):
                    continue
                skill_file = os.path.join(skill_path, "SKILL.md")
                if not os.path.isfile(skill_file):
                    continue
                with open(skill_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                description = ""
                for line in content.splitlines():
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
                        break
                if not description:
                    description = content[:120] + "..." if len(content) > 120 else content
                self.skills.append(Skill(item, description, skill_path, content))
        return self
    
    def is_empty(self) -> bool:
        return len(self.skills) == 0
    
    def __len__(self) -> int:
        return len(self.skills)

    def to_prompt_text(self) -> str:
        if self.is_empty():
            return "### 已加载技能\n(无已加载技能)"

        blocks = ["### 已加载技能"]
        for skill in self.skills:
            content = skill.content.strip()
            blocks.append(
                f"#### {skill.name}\n路径：{skill.path}\n说明：{skill.description}\n\n{content}"
            )
        return "\n\n".join(blocks)


def build_system_prompt(skills: Optional[SkillSet] = None, extra_instructions: Optional[str] = None) -> str:
    """动态构建系统提示词，整合运行环境、仓库规则和技能说明。"""
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

SYSTEM_PROMPT = build_system_prompt()

class Agent:
    def __init__(self, api_key: str, model: str = "Pro/zai-org/GLM-5", base_url: Optional[str] = None):
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)
        self.model = model
        self.system_prompt_override: Optional[str] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.skills = SkillSet()
        self.tools = default_tools()
        self.tool_definitions = TOOL_DEFINITIONS
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
            return self.tools.edit_file(args["path"], args["old_content"], args["new_content"])
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
        import re
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
                yield {"type": "error", "message": str(e)}
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
                yield {"type": "agent_end", "usage": total_usage}
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

def print_banner():
    print(f"\n{BOLD}{CYAN}  SimpleAgent{RESET} {DIM}— a coding agent growing up in public{RESET}")
    print(f"{DIM}  Type /quit to exit, /clear to reset{RESET}\n")

def print_usage(usage: Usage):
    if usage.input > 0 or usage.output > 0:
        print(f"\n{DIM}  tokens: {usage.input} in / {usage.output} out{RESET}")

def truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len]

# 默认模型名称
DEFAULT_MODEL = 'Pro/zai-org/GLM-5'

def parse_args():
    default_model = os.environ.get('OPENAI_MODEL', DEFAULT_MODEL)
    parser = argparse.ArgumentParser(description='SimpleAgent - coding agent')
    parser.add_argument('--model', default=default_model, help='Model to use (env: OPENAI_MODEL)')
    parser.add_argument('--skills', nargs='+', help='Skill directories to load')
    return parser.parse_args()

async def main():
    # 加载 .env 文件中的环境变量
    load_dotenv()
    
    api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('API_KEY')
    if not api_key:
        print("Error: Set OPENAI_API_KEY or API_KEY environment variable")
        sys.exit(1)
    
    base_url = os.environ.get('OPENAI_BASE_URL')
    args = parse_args()
    if not args.model or len(args.model) <= 0:
        args.model = os.environ.get('OPENAI_MODEL', DEFAULT_MODEL)
    
    skills = SkillSet()
    if args.skills:
        skills.load(args.skills)
    
    agent = Agent(api_key, args.model, base_url=base_url)
    agent.with_skills(skills)
    agent.with_tools(default_tools())
    
    print_banner()
    print(f"{DIM}  model: {args.model}{RESET}")
    if base_url:
        print(f"{DIM}  base_url: {base_url}{RESET}")
    if not skills.is_empty():
        print(f"{DIM}  skills: {len(skills)} loaded{RESET}")
    print(f"{DIM}  cwd:   {os.getcwd()}{RESET}\n")
    
    while True:
        try:
            user_input = input(f"{BOLD}{GREEN}> {RESET}").strip()
            
            if not user_input:
                continue
            
            if user_input in ['/quit', '/exit']:
                break
            elif user_input == '/clear':
                agent.clear_conversation()
                print(f"{DIM}  (conversation cleared){RESET}\n")
                continue
            elif user_input.startswith('/model '):
                new_model = user_input[7:].strip()
                agent.with_model(new_model)
                agent.clear_conversation()
                print(f"{DIM}  (switched to {new_model}, conversation cleared){RESET}\n")
                continue
            
            # 处理事件流
            in_text = False
            last_usage = Usage()
            
            async for event in agent.prompt(user_input):
                if event["type"] == "tool_start":
                    if in_text:
                        print()
                        in_text = False
                    tool_name = event["tool_name"]
                    tool_args = event["args"]
                    
                    if tool_name == "execute_command":
                        cmd = tool_args.get("command", "...")
                        summary = f"$ {truncate(cmd, 80)}"
                    elif tool_name == "read_file":
                        path = tool_args.get("path", "?")
                        summary = f"read {path}"
                    elif tool_name == "write_file":
                        path = tool_args.get("path", "?")
                        summary = f"write {path}"
                    elif tool_name == "edit_file":
                        path = tool_args.get("path", "?")
                        summary = f"edit {path}"
                    elif tool_name == "list_files":
                        path = tool_args.get("path", ".")
                        summary = f"ls {path}"
                    elif tool_name == "search_files":
                        pattern = tool_args.get("pattern", "?")
                        summary = f"search '{truncate(pattern, 60)}'"
                    else:
                        summary = tool_name
                    
                    print(f"{YELLOW}  ▶ {summary}{RESET}")
                    sys.stdout.flush()
                
                elif event["type"] == "tool_end":
                    tool_name = event["tool_name"]
                    result = event["result"]
                    success = result.get("success", False)
                    status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
                    print(f"{DIM}    {status} {tool_name} done{RESET}")
                    sys.stdout.flush()
                
                elif event["type"] == "reasoning":
                    if in_text:
                        print()
                    print(f"{DIM}  💭 {truncate(event['content'], 200)}{RESET}")
                    in_text = False
                
                elif event["type"] == "text_update":
                    if not in_text:
                        print()
                        in_text = True
                    print(event["delta"], end="")
                    sys.stdout.flush()
                
                elif event["type"] == "agent_end":
                    last_usage = event["usage"]
                
                elif event["type"] == "error":
                    print(f"{RED}Error: {event['message']}{RESET}")
            
            if in_text:
                print()
            
            print_usage(last_usage)
            print()
                
        except KeyboardInterrupt:
            print("\n")
            break
        except EOFError:
            break
    
    print(f"\n{DIM}  bye 👋{RESET}\n")

if __name__ == "__main__":
    asyncio.run(main())