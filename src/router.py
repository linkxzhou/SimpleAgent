"""LLM 路由模块 - 根据任务复杂度自动选择合适的模型。

支持三级模型路由：
- HIGH (复杂): 多文件重构、架构设计、复杂推理 → OPENAI_MODEL
- MIDDLE (中等): 一般编码、文件操作、调试 → OPENAI_MODEL_MIDDLE
- LOW (简单): 短问题、问候、简单查询 → OPENAI_MODEL_LOW

当某一级模型未配置时，自动向上回退到更高级别的模型。
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict


class TaskComplexity(Enum):
    """任务复杂度级别。"""
    LOW = "low"
    MIDDLE = "middle"
    HIGH = "high"


@dataclass
class RouterConfig:
    """路由配置。

    Attributes:
        model_high: 复杂任务模型（OPENAI_MODEL）
        model_middle: 中等任务模型（OPENAI_MODEL_MIDDLE）
        model_low: 简单任务模型（OPENAI_MODEL_LOW）
        enabled: 路由是否启用（至少配置了 2 个不同级别的模型才有意义）
    """
    model_high: Optional[str] = None
    model_middle: Optional[str] = None
    model_low: Optional[str] = None

    @property
    def enabled(self) -> bool:
        """路由是否启用：至少配置了 2 个不同级别的模型。"""
        models = [self.model_high, self.model_middle, self.model_low]
        configured = [m for m in models if m is not None]
        unique = set(configured)
        return len(unique) >= 2

    def resolve(self, complexity: TaskComplexity) -> Optional[str]:
        """根据复杂度选择模型，未配置时向上回退。

        回退逻辑：LOW → MIDDLE → HIGH
        """
        if complexity == TaskComplexity.LOW:
            return self.model_low or self.model_middle or self.model_high
        elif complexity == TaskComplexity.MIDDLE:
            return self.model_middle or self.model_high
        else:
            return self.model_high


# ── 复杂度分类规则 ────────────────────────────────────────────────

# LOW: 简单任务的关键词/模式（中英文）
_LOW_PATTERNS = [
    # 简单问候/闲聊
    r'^(hi|hello|hey|你好|嗨|谢谢|thanks|thank you|ok|好的|明白|understood)\s*[!！.。？?]*$',
    # 简单是/否/确认
    r'^(yes|no|y|n|是|否|对|不|好|行|可以|不行|不用)\s*[!！.。？?]*$',
    # 简短问题（少于 15 个字符且无代码特征）
    r'^[^`\n]{1,15}[?？]$',
    # 版本/状态查询
    r'^(version|status|what version|什么版本|当前版本)',
]

# HIGH: 复杂任务的关键词/模式
_HIGH_KEYWORDS = [
    # 多文件操作
    'refactor', 'restructure', '重构', '重写', '架构',
    # 复杂推理
    'design', 'architect', '设计', '方案', '规划',
    # 长文档生成
    'documentation', 'spec', '文档', '规范',
    # 多步骤任务
    'step by step', '分步', '逐步',
    # 安全/审计
    'security audit', 'vulnerability', '安全审计', '漏洞',
    # 性能分析
    'performance', 'optimize', '性能', '优化',
    # 测试套件
    'test suite', 'test coverage', '测试套件', '测试覆盖',
]

# HIGH: 复杂任务的结构特征
_HIGH_THRESHOLDS = {
    'min_length': 500,         # 超过 500 字符的输入
    'min_code_blocks': 2,      # 包含 2 个以上代码块
    'min_file_refs': 3,        # 引用 3 个以上文件路径
    'min_newlines': 10,        # 超过 10 行的输入
}

# 文件路径模式（用于计数文件引用）
# 支持前导分隔符：空白、中文标点（、，；）、英文逗号分号等
_FILE_PATH_PATTERN = re.compile(
    r'(?:^|[\s,;、，；])(?:\.?/)?(?:[\w.-]+/)*[\w.-]+\.(?:py|js|ts|go|rs|java|md|json|yaml|yml|toml|sh)\b'
)

# 代码块模式
_CODE_BLOCK_PATTERN = re.compile(r'```')


def classify_complexity(user_input: str, history_len: int = 0) -> TaskComplexity:
    """根据用户输入和上下文判断任务复杂度。

    分类策略（按优先级）：
    1. 空/纯空白 → LOW
    2. 匹配 LOW 模式（问候、确认等）→ LOW
    3. 匹配 HIGH 关键词 → HIGH（优先于短输入判断，因为中文关键词可能很短）
    4. 极短输入（少于 8 字符且无代码特征）→ LOW
    5. 匹配 HIGH 结构特征 → HIGH
    6. 默认 → MIDDLE

    Args:
        user_input: 用户输入文本
        history_len: 当前对话历史长度（长对话中的后续消息倾向于更简单）

    Returns:
        TaskComplexity 枚举值
    """
    if not user_input or not user_input.strip():
        return TaskComplexity.LOW

    text = user_input.strip()
    text_lower = text.lower()

    # 1. 检查 LOW 模式（问候、确认等）
    for pattern in _LOW_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return TaskComplexity.LOW

    # 2. 检查 HIGH 关键词（优先于短输入判断，因为中文关键词可能很短）
    for keyword in _HIGH_KEYWORDS:
        if keyword.lower() in text_lower:
            return TaskComplexity.HIGH

    # 3. 极短输入（少于 8 字符且无代码特征）→ LOW
    if len(text) < 8 and '```' not in text and '\n' not in text:
        return TaskComplexity.LOW

    # 4. 检查 HIGH 结构特征
    # 长输入
    if len(text) >= _HIGH_THRESHOLDS['min_length']:
        return TaskComplexity.HIGH

    # 多代码块
    code_blocks = len(_CODE_BLOCK_PATTERN.findall(text)) // 2  # 每对 ``` 算一个块
    if code_blocks >= _HIGH_THRESHOLDS['min_code_blocks']:
        return TaskComplexity.HIGH

    # 多文件引用
    file_refs = len(_FILE_PATH_PATTERN.findall(text))
    if file_refs >= _HIGH_THRESHOLDS['min_file_refs']:
        return TaskComplexity.HIGH

    # 多行输入
    newlines = text.count('\n')
    if newlines >= _HIGH_THRESHOLDS['min_newlines']:
        return TaskComplexity.HIGH

    # 5. 默认 → MIDDLE
    return TaskComplexity.MIDDLE


class ModelRouter:
    """模型路由器 — 根据任务复杂度自动选择模型。

    从环境变量读取三级模型配置，在 Agent 发送请求前自动选择。
    当路由未启用（配置不足 2 个不同模型）时，不做任何切换。
    """

    def __init__(self, config: Optional[RouterConfig] = None):
        """初始化路由器。

        Args:
            config: 路由配置。如果为 None，从环境变量自动读取。
        """
        self.config = config or self._load_from_env()
        self._last_complexity: Optional[TaskComplexity] = None
        self._last_model: Optional[str] = None
        # 统计信息
        self.stats: Dict[TaskComplexity, int] = {
            TaskComplexity.LOW: 0,
            TaskComplexity.MIDDLE: 0,
            TaskComplexity.HIGH: 0,
        }

    @staticmethod
    def _load_from_env() -> RouterConfig:
        """从环境变量加载路由配置。"""
        return RouterConfig(
            model_high=os.environ.get('OPENAI_MODEL'),
            model_middle=os.environ.get('OPENAI_MODEL_MIDDLE'),
            model_low=os.environ.get('OPENAI_MODEL_LOW'),
        )

    @property
    def enabled(self) -> bool:
        """路由是否启用。"""
        return self.config.enabled

    @property
    def last_complexity(self) -> Optional[TaskComplexity]:
        """最近一次路由的任务复杂度。"""
        return self._last_complexity

    @property
    def last_model(self) -> Optional[str]:
        """最近一次路由选择的模型。"""
        return self._last_model

    def route(self, user_input: str, default_model: str,
              history_len: int = 0) -> str:
        """根据用户输入选择模型。

        Args:
            user_input: 用户输入文本
            default_model: 默认模型（路由未启用时使用）
            history_len: 当前对话历史长度

        Returns:
            选择的模型名称
        """
        if not self.enabled:
            self._last_complexity = None
            self._last_model = default_model
            return default_model

        complexity = classify_complexity(user_input, history_len)
        selected = self.config.resolve(complexity)

        # 如果 resolve 返回 None（理论上不会，因为 enabled 检查保证至少 2 个模型）
        if selected is None:
            selected = default_model

        self._last_complexity = complexity
        self._last_model = selected
        self.stats[complexity] += 1

        return selected

    def get_stats_summary(self) -> str:
        """返回路由统计摘要。"""
        total = sum(self.stats.values())
        if total == 0:
            return "无路由记录"
        parts = []
        for level in (TaskComplexity.LOW, TaskComplexity.MIDDLE, TaskComplexity.HIGH):
            count = self.stats[level]
            if count > 0:
                pct = int(count / total * 100)
                parts.append(f"{level.value}: {count} ({pct}%)")
        return f"路由统计（共 {total} 次）：{', '.join(parts)}"
