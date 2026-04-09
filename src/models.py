"""工具调用请求和 token 用量等共享数据结构。"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallRequest:
    """LLM 返回的工具调用请求"""
    id: str
    name: str
    arguments: Dict[str, Any]
    provider_specific_fields: Optional[Dict[str, Any]] = None
    function_provider_specific_fields: Optional[Dict[str, Any]] = None

    def to_openai_tool_call(self) -> Dict[str, Any]:
        """序列化为 OpenAI 格式的 tool_call。"""
        tool_call: Dict[str, Any] = {
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
class Usage:
    input: int = 0
    output: int = 0


@dataclass
class TeamConfig:
    """Team 协作配置（Issue #7）。
    
    定义 SubAgent Team 的规模、角色和协作模式。
    """
    team_size: int  # Team 成员数量（2-10）
    roles: List[str]  # 每个成员的角色（长度应等于 team_size）
    shared_context: Dict[str, Any] = field(default_factory=dict)  # Context Lake（共享只读上下文）
    parallel: bool = True  # 是否并行执行任务（True=asyncio.gather, False=顺序执行）
    max_workers: int = 5  # 并行执行时的最大并发数（防止资源耗尽）
    
    def __post_init__(self):
        """验证配置有效性。"""
        if self.team_size < 1:
            raise ValueError(f"team_size must be >= 1, got {self.team_size}")
        if self.team_size > 20:
            raise ValueError(f"team_size must be <= 20 (avoid resource exhaustion), got {self.team_size}")
        if len(self.roles) != self.team_size:
            raise ValueError(f"roles length ({len(self.roles)}) must equal team_size ({self.team_size})")
        if self.max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {self.max_workers}")
