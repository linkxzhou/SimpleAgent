"""多提供商支持测试。"""

import os
import pytest
from unittest.mock import patch

from src.providers import (
    ProviderConfig, PROVIDERS, get_provider, list_providers, resolve_provider,
)


class TestProviderConfig:
    """ProviderConfig 数据类测试。"""

    def test_basic_creation(self):
        p = ProviderConfig(
            name="test", display_name="Test", base_url="http://localhost",
            default_model="test-model"
        )
        assert p.name == "test"
        assert p.display_name == "Test"
        assert p.base_url == "http://localhost"
        assert p.default_model == "test-model"
        assert p.api_key_env is None

    def test_with_api_key_env(self):
        p = ProviderConfig(
            name="test", display_name="Test", base_url="http://localhost",
            default_model="m", api_key_env="MY_KEY"
        )
        assert p.api_key_env == "MY_KEY"


    def test_with_default_max_tokens(self):
        p = ProviderConfig(
            name="test", display_name="Test", base_url="http://localhost",
            default_model="m", default_max_tokens=8192
        )
        assert p.default_max_tokens == 8192

    def test_default_max_tokens_is_none(self):
        p = ProviderConfig(
            name="test", display_name="Test", base_url="http://localhost",
            default_model="m"
        )
        assert p.default_max_tokens is None


class TestBuiltinProviders:
    """内置提供商注册表测试。"""

    def test_openai_registered(self):
        p = PROVIDERS.get("openai")
        assert p is not None
        assert p.display_name == "OpenAI"
        assert "openai.com" in p.base_url
        assert p.default_model == "gpt-4o"

    def test_deepseek_registered(self):
        p = PROVIDERS.get("deepseek")
        assert p is not None
        assert p.display_name == "DeepSeek"
        assert "deepseek.com" in p.base_url

    def test_groq_registered(self):
        p = PROVIDERS.get("groq")
        assert p is not None
        assert "groq.com" in p.base_url
        assert p.default_max_tokens == 8192

    def test_siliconflow_registered(self):
        p = PROVIDERS.get("siliconflow")
        assert p is not None
        assert "siliconflow" in p.base_url

    def test_together_registered(self):
        p = PROVIDERS.get("together")
        assert p is not None
        assert "together" in p.base_url

    def test_ollama_registered(self):
        p = PROVIDERS.get("ollama")
        assert p is not None
        assert "localhost" in p.base_url
        assert p.api_key_env is None  # Ollama 不需要 key

    def test_at_least_6_providers(self):
        assert len(PROVIDERS) >= 6


class TestGetProvider:
    """get_provider() 函数测试。"""

    def test_existing_provider(self):
        p = get_provider("openai")
        assert p is not None
        assert p.name == "openai"

    def test_case_insensitive(self):
        p = get_provider("OpenAI")
        assert p is not None
        assert p.name == "openai"

    def test_unknown_provider_returns_none(self):
        assert get_provider("nonexistent") is None


class TestListProviders:
    """list_providers() 函数测试。"""

    def test_returns_list(self):
        result = list_providers()
        assert isinstance(result, list)
        assert len(result) >= 6

    def test_sorted_by_name(self):
        result = list_providers()
        names = [p.name for p in result]
        assert names == sorted(names)

    def test_all_are_provider_config(self):
        for p in list_providers():
            assert isinstance(p, ProviderConfig)


class TestResolveProvider:
    """resolve_provider() 函数测试。"""

    def test_no_provider_no_model(self):
        """无 provider 无 model 时，model 为 None。"""
        result = resolve_provider(None, None, None, "sk-test")
        assert result["model"] is None
        assert result["base_url"] is None
        assert result["api_key"] == "sk-test"
        assert result["provider_display_name"] is None

    def test_provider_sets_defaults(self):
        """provider 设置默认 model 和 base_url。"""
        result = resolve_provider("openai", None, None, "sk-test")
        assert result["model"] == "gpt-4o"
        assert "openai.com" in result["base_url"]
        assert result["provider_display_name"] == "OpenAI"

    def test_model_overrides_provider_default(self):
        """--model 覆盖 provider 的默认 model。"""
        result = resolve_provider("openai", "gpt-3.5-turbo", None, "sk-test")
        assert result["model"] == "gpt-3.5-turbo"

    def test_base_url_overrides_provider_default(self):
        """OPENAI_BASE_URL 覆盖 provider 的默认 base_url。"""
        result = resolve_provider("openai", None, "http://custom/v1", "sk-test")
        assert result["base_url"] == "http://custom/v1"

    def test_unknown_provider_raises_valueerror(self):
        """未知 provider 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="未知提供商"):
            resolve_provider("nonexistent", None, None, None)

    def test_valueerror_lists_available_providers(self):
        """ValueError 消息中列出可用提供商。"""
        with pytest.raises(ValueError, match="openai"):
            resolve_provider("bad", None, None, None)

    def test_provider_specific_api_key_env(self):
        """provider 的专属环境变量用于获取 API key。"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-ds-test"}, clear=False):
            result = resolve_provider("deepseek", None, None, None)
            assert result["api_key"] == "sk-ds-test"

    def test_explicit_api_key_overrides_env(self):
        """显式传入的 api_key 优先于环境变量。"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-ds-env"}, clear=False):
            result = resolve_provider("deepseek", None, None, "sk-explicit")
            assert result["api_key"] == "sk-explicit"

    def test_fallback_to_openai_api_key(self):
        """provider 的专属环境变量不存在时，回退到 OPENAI_API_KEY。"""
        env = {"OPENAI_API_KEY": "sk-fallback"}
        # 确保 DEEPSEEK_API_KEY 不存在
        with patch.dict(os.environ, env, clear=False):
            # 移除 DEEPSEEK_API_KEY（如果存在）
            os.environ.pop("DEEPSEEK_API_KEY", None)
            result = resolve_provider("deepseek", None, None, None)
            assert result["api_key"] == "sk-fallback"

    def test_ollama_no_api_key_needed(self):
        """Ollama 不需要 API key，api_key_env 为 None。"""
        # 清除所有 key 环境变量
        env = {}
        with patch.dict(os.environ, env, clear=True):
            result = resolve_provider("ollama", None, None, None)
            assert result["model"] == "llama3.2"
            assert "localhost" in result["base_url"]
            # api_key 为 None（无任何 key 环境变量）
            assert result["api_key"] is None

    def test_ollama_with_dummy_key(self):
        """Ollama 无 api_key_env 但有 OPENAI_API_KEY 时，使用该 key。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=True):
            result = resolve_provider("ollama", None, None, None)
            assert result["api_key"] == "dummy"

    def test_max_tokens_from_provider(self):
        """provider 有 default_max_tokens 时，返回该值。"""
        result = resolve_provider("groq", None, None, "sk-test")
        assert result["max_tokens"] == 8192

    def test_max_tokens_none_when_provider_has_no_default(self):
        """provider 无 default_max_tokens 时，返回 None。"""
        result = resolve_provider("openai", None, None, "sk-test")
        assert result["max_tokens"] is None

    def test_max_tokens_none_without_provider(self):
        """不指定 provider 时，max_tokens 为 None。"""
        result = resolve_provider(None, None, None, "sk-test")
        assert result["max_tokens"] is None
