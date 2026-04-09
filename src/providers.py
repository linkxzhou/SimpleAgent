"""多提供商支持模块 - LLM 提供商注册表和配置解析。"""

from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class ProviderConfig:
    """LLM 提供商配置。
    
    Attributes:
        name: 提供商标识符（用于 --provider 参数）
        display_name: 显示名称
        base_url: API 基础 URL
        default_model: 该提供商的默认模型名称
        api_key_env: 读取 API key 的环境变量名（优先级高于 OPENAI_API_KEY）
    """
    name: str
    display_name: str
    base_url: str
    default_model: str
    api_key_env: Optional[str] = None
    default_max_tokens: Optional[int] = None  # 默认 max_tokens（None = 使用 Agent 默认值）


# 内置提供商注册表
# 用户可通过 --provider <name> 选择，自动设置 base_url 和默认模型
PROVIDERS: Dict[str, ProviderConfig] = {}

_BUILTIN_PROVIDERS = [
    ProviderConfig(
        name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        api_key_env="OPENAI_API_KEY",
    ),
    ProviderConfig(
        name="deepseek",
        display_name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    ProviderConfig(
        name="groq",
        display_name="Groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
        default_max_tokens=8192,  # Groq 部分模型输出上限 8192
    ),
    ProviderConfig(
        name="siliconflow",
        display_name="SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        default_model="deepseek-ai/DeepSeek-V3",
        api_key_env="SILICONFLOW_API_KEY",
    ),
    ProviderConfig(
        name="together",
        display_name="Together AI",
        base_url="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        api_key_env="TOGETHER_API_KEY",
    ),
    ProviderConfig(
        name="ollama",
        display_name="Ollama (本地)",
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
        api_key_env=None,  # Ollama 不需要 API key
    ),
]

# 注册内置提供商
for _p in _BUILTIN_PROVIDERS:
    PROVIDERS[_p.name] = _p


def get_provider(name: str) -> Optional[ProviderConfig]:
    """根据名称获取提供商配置。
    
    Args:
        name: 提供商标识符（不区分大小写）
    
    Returns:
        ProviderConfig 或 None（未找到）
    """
    return PROVIDERS.get(name.lower())


def list_providers() -> List[ProviderConfig]:
    """列出所有已注册的提供商。
    
    Returns:
        按名称排序的 ProviderConfig 列表
    """
    return sorted(PROVIDERS.values(), key=lambda p: p.name)


def resolve_provider(provider_name: Optional[str], model: Optional[str],
                     base_url: Optional[str], api_key: Optional[str]
                     ) -> Dict[str, Optional[str]]:
    """解析提供商配置，合并命令行参数和环境变量。
    
    优先级（从高到低）：
    1. 用户显式指定的 --model / --base-url / API_KEY 环境变量
    2. 提供商预设的默认值
    3. 全局默认值（OPENAI_API_KEY、无 base_url）
    
    Args:
        provider_name: --provider 参数值（可能为 None）
        model: --model 参数值（可能为 None）
        base_url: OPENAI_BASE_URL 环境变量值（可能为 None）
        api_key: 已获取的 API key（可能为 None）
    
    Returns:
        {"model": str, "base_url": str|None, "api_key": str|None,
         "provider_display_name": str|None}
    
    Raises:
        ValueError: 指定的提供商不存在
    """
    import os
    
    provider = None
    provider_display = None
    
    if provider_name:
        provider = get_provider(provider_name)
        if provider is None:
            available = ", ".join(p.name for p in list_providers())
            raise ValueError(
                f"未知提供商 '{provider_name}'。可用提供商：{available}"
            )
        provider_display = provider.display_name
    
    # 解析 model：用户指定 > 提供商默认
    resolved_model = model
    if not resolved_model and provider:
        resolved_model = provider.default_model
    
    # 解析 base_url：用户指定 > 提供商默认
    resolved_base_url = base_url
    if not resolved_base_url and provider:
        resolved_base_url = provider.base_url
    
    # 解析 api_key：用户已有 > 提供商专属环境变量 > OPENAI_API_KEY
    resolved_api_key = api_key
    if not resolved_api_key and provider and provider.api_key_env:
        resolved_api_key = os.environ.get(provider.api_key_env)
    if not resolved_api_key:
        resolved_api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("API_KEY")
    
    # 解析 max_tokens：提供商预设（None = 使用 Agent 默认值）
    resolved_max_tokens = None
    if provider and provider.default_max_tokens is not None:
        resolved_max_tokens = provider.default_max_tokens
    
    return {
        "model": resolved_model,
        "base_url": resolved_base_url,
        "api_key": resolved_api_key,
        "provider_display_name": provider_display,
        "max_tokens": resolved_max_tokens,
    }
