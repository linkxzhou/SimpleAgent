"""
数据模型定义
"""

import os
import json
from dataclasses import dataclass, field
from typing import List, Any, Optional


@dataclass
class Usage:
    """Token 用量统计"""
    input: int = 0
    output: int = 0


@dataclass
class Skill:
    """技能描述"""
    name: str
    description: str
    path: str
    content: str = ""


class SkillSet:
    """技能集合管理"""

    def __init__(self):
        self.skills: List[Skill] = []

    def load(self, skill_dirs: List[str]) -> 'SkillSet':
        """从指定目录加载技能"""
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
        """转换为提示词文本格式"""
        if self.is_empty():
            return "### 已加载技能\n(无已加载技能)"

        blocks = ["### 已加载技能"]
        for skill in self.skills:
            content = skill.content.strip()
            blocks.append(
                f"#### {skill.name}\n路径：{skill.path}\n说明：{skill.description}\n\n{content}"
            )
        return "\n\n".join(blocks)


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