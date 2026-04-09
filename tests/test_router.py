"""LLM 路由模块测试。"""

import os
import pytest
from unittest.mock import patch

from src.router import (
    TaskComplexity,
    RouterConfig,
    ModelRouter,
    classify_complexity,
)


# ── RouterConfig 测试 ──────────────────────────────────────────


class TestRouterConfig:
    """RouterConfig 数据类测试。"""

    def test_all_none_not_enabled(self):
        config = RouterConfig()
        assert not config.enabled

    def test_single_model_not_enabled(self):
        config = RouterConfig(model_high="gpt-4o")
        assert not config.enabled

    def test_same_model_all_levels_not_enabled(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o", model_low="gpt-4o")
        assert not config.enabled

    def test_two_different_models_enabled(self):
        config = RouterConfig(model_high="gpt-4o", model_low="gpt-4o-mini")
        assert config.enabled

    def test_three_different_models_enabled(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o-mini", model_low="gpt-3.5")
        assert config.enabled

    def test_two_same_one_different_enabled(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o", model_low="gpt-3.5")
        assert config.enabled

    def test_resolve_high(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o-mini", model_low="gpt-3.5")
        assert config.resolve(TaskComplexity.HIGH) == "gpt-4o"

    def test_resolve_middle(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o-mini", model_low="gpt-3.5")
        assert config.resolve(TaskComplexity.MIDDLE) == "gpt-4o-mini"

    def test_resolve_low(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o-mini", model_low="gpt-3.5")
        assert config.resolve(TaskComplexity.LOW) == "gpt-3.5"

    def test_resolve_low_fallback_to_middle(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o-mini")
        assert config.resolve(TaskComplexity.LOW) == "gpt-4o-mini"

    def test_resolve_low_fallback_to_high(self):
        config = RouterConfig(model_high="gpt-4o")
        assert config.resolve(TaskComplexity.LOW) == "gpt-4o"

    def test_resolve_middle_fallback_to_high(self):
        config = RouterConfig(model_high="gpt-4o")
        assert config.resolve(TaskComplexity.MIDDLE) == "gpt-4o"

    def test_resolve_all_none(self):
        config = RouterConfig()
        assert config.resolve(TaskComplexity.HIGH) is None
        assert config.resolve(TaskComplexity.MIDDLE) is None
        assert config.resolve(TaskComplexity.LOW) is None


# ── classify_complexity 测试 ──────────────────────────────────


class TestClassifyComplexity:
    """任务复杂度分类测试。"""

    # LOW: 简单问候/闲聊
    @pytest.mark.parametrize("text", [
        "hi", "hello", "你好", "谢谢", "thanks", "ok", "好的",
        "yes", "no", "是", "否", "对", "可以",
        "Hello!", "你好！", "thanks!", "谢谢！",
    ])
    def test_low_greetings(self, text):
        assert classify_complexity(text) == TaskComplexity.LOW

    # LOW: 空输入
    def test_low_empty(self):
        assert classify_complexity("") == TaskComplexity.LOW
        assert classify_complexity("  ") == TaskComplexity.LOW

    # LOW: 极短输入
    @pytest.mark.parametrize("text", [
        "继续", "下一步", "help", "test",
    ])
    def test_low_short(self, text):
        assert classify_complexity(text) == TaskComplexity.LOW

    # HIGH: 包含复杂关键词
    @pytest.mark.parametrize("text,keyword", [
        ("请帮我重构这个模块的代码", "重构"),
        ("设计一个新的数据库架构", "架构"),
        ("do a security audit on this codebase", "security audit"),
        ("optimize the performance of this function", "performance"),
        ("create a comprehensive test suite for the auth module", "test suite"),
        ("请分步完成以下任务", "分步"),
    ])
    def test_high_keywords(self, text, keyword):
        result = classify_complexity(text)
        assert result == TaskComplexity.HIGH, f"Expected HIGH for '{text}' (keyword: {keyword}), got {result}"

    # HIGH: 长输入
    def test_high_long_input(self):
        text = "请修改 " + "x" * 500
        assert classify_complexity(text) == TaskComplexity.HIGH

    # HIGH: 多行输入
    def test_high_multiline(self):
        text = "\n".join([f"line {i}" for i in range(12)])
        assert classify_complexity(text) == TaskComplexity.HIGH

    # HIGH: 多代码块
    def test_high_multiple_code_blocks(self):
        text = "修改以下代码：\n```python\ndef foo():\n    pass\n```\n替换为：\n```python\ndef foo():\n    return 42\n```"
        assert classify_complexity(text) == TaskComplexity.HIGH

    # HIGH: 多文件引用
    def test_high_multiple_file_refs(self):
        text = "请修改 src/agent.py、src/cli.py 和 src/router.py 中的相关代码"
        assert classify_complexity(text) == TaskComplexity.HIGH

    # MIDDLE: 一般编码问题
    @pytest.mark.parametrize("text", [
        "帮我读取 config.json 的内容",
        "在 main.py 中添加一个新的函数",
        "这个报错是什么意思？TypeError: expected str, got int",
        "运行一下测试看看结果",
        "请解释这段代码的作用",
        "how to fix this bug in the login function",
    ])
    def test_middle_general(self, text):
        result = classify_complexity(text)
        assert result == TaskComplexity.MIDDLE, f"Expected MIDDLE for '{text}', got {result}"


# ── ModelRouter 测试 ──────────────────────────────────────────


class TestModelRouter:
    """ModelRouter 路由器测试。"""

    def test_disabled_returns_default(self):
        config = RouterConfig(model_high="gpt-4o")  # 只有一个模型，不启用
        router = ModelRouter(config)
        assert not router.enabled
        result = router.route("hello", default_model="default-model")
        assert result == "default-model"

    def test_enabled_routes_low(self):
        config = RouterConfig(model_high="gpt-4o", model_low="gpt-3.5")
        router = ModelRouter(config)
        assert router.enabled
        result = router.route("hi", default_model="default-model")
        assert result == "gpt-3.5"
        assert router.last_complexity == TaskComplexity.LOW
        assert router.last_model == "gpt-3.5"

    def test_enabled_routes_middle(self):
        config = RouterConfig(model_high="gpt-4o", model_middle="gpt-4o-mini", model_low="gpt-3.5")
        router = ModelRouter(config)
        result = router.route("帮我读取 config.json 的内容", default_model="default")
        assert result == "gpt-4o-mini"
        assert router.last_complexity == TaskComplexity.MIDDLE

    def test_enabled_routes_high(self):
        config = RouterConfig(model_high="gpt-4o", model_low="gpt-3.5")
        router = ModelRouter(config)
        result = router.route("请帮我重构整个模块的架构", default_model="default")
        assert result == "gpt-4o"
        assert router.last_complexity == TaskComplexity.HIGH

    def test_stats_tracking(self):
        config = RouterConfig(model_high="gpt-4o", model_low="gpt-3.5")
        router = ModelRouter(config)
        router.route("hi", default_model="default")
        router.route("hello", default_model="default")
        router.route("帮我读取 config.json 的内容并分析一下", default_model="default")
        router.route("请重构这个模块", default_model="default")
        assert router.stats[TaskComplexity.LOW] == 2
        assert router.stats[TaskComplexity.MIDDLE] == 1
        assert router.stats[TaskComplexity.HIGH] == 1

    def test_stats_summary(self):
        config = RouterConfig(model_high="gpt-4o", model_low="gpt-3.5")
        router = ModelRouter(config)
        assert router.get_stats_summary() == "无路由记录"
        router.route("hi", default_model="default")
        summary = router.get_stats_summary()
        assert "路由统计" in summary
        assert "low" in summary

    def test_load_from_env(self):
        env = {
            "OPENAI_MODEL": "gpt-4o",
            "OPENAI_MODEL_MIDDLE": "gpt-4o-mini",
            "OPENAI_MODEL_LOW": "gpt-3.5-turbo",
        }
        with patch.dict(os.environ, env, clear=False):
            router = ModelRouter()
            assert router.config.model_high == "gpt-4o"
            assert router.config.model_middle == "gpt-4o-mini"
            assert router.config.model_low == "gpt-3.5-turbo"
            assert router.enabled

    def test_load_from_env_partial(self):
        env = {"OPENAI_MODEL": "gpt-4o", "OPENAI_MODEL_LOW": "gpt-3.5"}
        # 使用 clear=True + 显式传入完整环境，确保 OPENAI_MODEL_MIDDLE 不存在
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("OPENAI_MODEL", "OPENAI_MODEL_MIDDLE", "OPENAI_MODEL_LOW")}
        clean_env.update(env)
        with patch.dict(os.environ, clean_env, clear=True):
            router = ModelRouter()
            assert router.config.model_high == "gpt-4o"
            assert router.config.model_middle is None
            assert router.config.model_low == "gpt-3.5"
            assert router.enabled

    def test_load_from_env_none(self):
        """环境变量未设置时路由不启用。"""
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("OPENAI_MODEL", "OPENAI_MODEL_MIDDLE", "OPENAI_MODEL_LOW")}
        with patch.dict(os.environ, clean_env, clear=True):
            router = ModelRouter()
            assert not router.enabled

    def test_fallback_on_missing_middle(self):
        """MIDDLE 级别未配置时回退到 HIGH。"""
        config = RouterConfig(model_high="gpt-4o", model_low="gpt-3.5")
        router = ModelRouter(config)
        result = router.route("帮我读取 config.json 的内容", default_model="default")
        # MIDDLE 未配置，回退到 HIGH
        assert result == "gpt-4o"
        assert router.last_complexity == TaskComplexity.MIDDLE

    def test_disabled_no_complexity(self):
        """路由未启用时 last_complexity 为 None。"""
        config = RouterConfig(model_high="gpt-4o")
        router = ModelRouter(config)
        router.route("hello", default_model="default")
        assert router.last_complexity is None
