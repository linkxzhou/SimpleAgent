"""
测试异常处理模块
"""

import pytest
from src.exceptions import (
    SimpleAgentException,
    APIError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    ModelNotFoundError,
    ToolError,
    SystemError,
    classify_exception,
    format_error_message,
)


class TestExceptionClasses:
    """测试异常类"""

    def test_simple_agent_exception(self):
        """测试基础异常类"""
        exc = SimpleAgentException("测试错误", recoverable=True, suggestion="测试建议")
        assert exc.message == "测试错误"
        assert exc.recoverable is True
        assert exc.suggestion == "测试建议"

    def test_api_error(self):
        """测试 API 错误基类"""
        exc = APIError("API 调用失败")
        assert exc.message == "API 调用失败"
        assert exc.recoverable is True
        assert "API" in exc.suggestion
        assert hasattr(exc, 'retry_after')

    def test_authentication_error(self):
        """测试 API 认证错误"""
        exc = AuthenticationError()
        assert "认证失败" in exc.message
        assert exc.recoverable is True
        assert exc.retry_after is None
        assert "OPENAI_API_KEY" in exc.suggestion

    def test_rate_limit_error(self):
        """测试速率限制错误"""
        exc = RateLimitError()
        assert "频率超限" in exc.message
        assert exc.recoverable is True
        assert exc.retry_after == 60
        assert "60" in exc.suggestion

    def test_network_error(self):
        """测试网络错误"""
        exc = NetworkError()
        assert "网络" in exc.message
        assert exc.recoverable is True
        assert exc.retry_after == 5

    def test_model_not_found_error(self):
        """测试模型不存在错误"""
        exc = ModelNotFoundError("test-model")
        assert "test-model" in exc.message
        assert exc.recoverable is True
        assert exc.retry_after is None

    def test_tool_error(self):
        """测试工具错误"""
        exc = ToolError("工具执行失败")
        assert exc.message == "工具执行失败"
        assert exc.recoverable is True
        assert "工具" in exc.suggestion or "重试" in exc.suggestion

    def test_system_error(self):
        """测试系统错误"""
        exc = SystemError("系统崩溃")
        assert exc.message == "系统崩溃"
        assert exc.recoverable is False


class TestClassifyException:
    """测试异常分类"""

    def test_classify_api_key_error(self):
        """测试 API 密钥错误分类"""
        original_error = Exception("Invalid API key provided")
        classified = classify_exception(original_error)
        assert isinstance(classified, APIError)
        assert "认证" in classified.message or "API key" in classified.message

    def test_classify_rate_limit_error(self):
        """测试速率限制错误分类"""
        original_error = Exception("Rate limit exceeded")
        classified = classify_exception(original_error)
        assert isinstance(classified, APIError)
        assert "频率" in classified.message or "速率" in classified.message

    def test_classify_network_error(self):
        """测试网络错误分类"""
        original_error = Exception("Network connection timeout")
        classified = classify_exception(original_error)
        assert isinstance(classified, APIError)
        assert "网络" in classified.message

    def test_classify_file_not_found(self):
        """测试文件不存在错误分类"""
        original_error = FileNotFoundError("No such file or directory")
        classified = classify_exception(original_error)
        assert isinstance(classified, ToolError)
        assert "文件" in classified.message

    def test_classify_permission_error(self):
        """测试权限错误分类"""
        original_error = PermissionError("Permission denied")
        classified = classify_exception(original_error)
        assert isinstance(classified, ToolError)
        assert "权限" in classified.message

    def test_classify_memory_error(self):
        """测试内存错误分类"""
        original_error = MemoryError("Out of memory")
        classified = classify_exception(original_error)
        assert isinstance(classified, SystemError)
        assert "内存" in classified.message

    def test_classify_unknown_error(self):
        """测试未知错误分类"""
        original_error = RuntimeError("Unknown runtime error")
        classified = classify_exception(original_error)
        assert isinstance(classified, SimpleAgentException)
        assert classified.recoverable is True


class TestFormatErrorMessage:
    """测试错误消息格式化"""

    def test_format_recoverable_error(self):
        """测试可恢复错误格式化"""
        exc = SimpleAgentException("测试错误", recoverable=True, suggestion="测试建议")
        message = format_error_message(exc)
        assert "❌ 错误: 测试错误" in message
        assert "💡 建议: 测试建议" in message
        assert "✓ 会话继续" in message

    def test_format_non_recoverable_error(self):
        """测试不可恢复错误格式化"""
        exc = SystemError("系统崩溃")
        message = format_error_message(exc)
        assert "❌ 错误: 系统崩溃" in message
        assert "⚠ 会话需要退出" in message

    def test_format_error_without_suggestion(self):
        """测试无建议的错误格式化"""
        exc = SimpleAgentException("测试错误", recoverable=True, suggestion=None)
        message = format_error_message(exc)
        assert "❌ 错误: 测试错误" in message
        assert "💡 建议:" not in message