"""
测试 CLI 模块
"""

import sys
from io import StringIO
from unittest.mock import patch
from src.cli import (
    print_banner,
    print_version,
    truncate,
    DEFAULT_MODEL,
)


class TestPrintBanner:
    """测试 print_banner 功能"""

    def test_print_banner_output(self):
        """测试 banner 输出"""
        captured = StringIO()
        with patch('sys.stdout', captured):
            print_banner()
        output = captured.getvalue()
        assert "SimpleAgent" in output


class TestPrintVersion:
    """测试 print_version 功能"""

    def test_print_version_output(self):
        """测试版本输出"""
        captured = StringIO()
        with patch('sys.stdout', captured):
            print_version()
        output = captured.getvalue()
        assert "SimpleAgent" in output
        assert "0.1.0" in output


class TestTruncate:
    """测试 truncate 功能"""

    def test_truncate_short_string(self):
        """测试短字符串不被截断"""
        result = truncate("hello", 10)
        assert result == "hello"

    def test_truncate_long_string(self):
        """测试长字符串被截断"""
        result = truncate("hello world this is very long", 10)
        assert result == "hello worl"
        assert len(result) == 10

    def test_truncate_exact_length(self):
        """测试恰好长度的字符串"""
        result = truncate("hello", 5)
        assert result == "hello"

    def test_truncate_empty_string(self):
        """测试空字符串"""
        result = truncate("", 10)
        assert result == ""


class TestConstants:
    """测试常量定义"""

    def test_default_model_defined(self):
        """测试默认模型已定义"""
        assert DEFAULT_MODEL is not None
        assert len(DEFAULT_MODEL) > 0