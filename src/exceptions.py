"""
异常处理模块 - 提供统一的异常分类和处理
"""

from typing import Optional


class SimpleAgentException(Exception):
    """SimpleAgent 基础异常类"""
    
    def __init__(self, message: str, recoverable: bool = True, suggestion: Optional[str] = None):
        self.message = message
        self.recoverable = recoverable
        self.suggestion = suggestion
        super().__init__(self.message)


class APIError(SimpleAgentException):
    """API 相关错误（基类）"""
    
    def __init__(self, message: str, suggestion: Optional[str] = None, retry_after: Optional[int] = None):
        self.retry_after = retry_after  # 建议重试等待秒数
        super().__init__(
            message=message,
            recoverable=True,
            suggestion=suggestion or "请检查网络连接和 API 配置，然后重试"
        )


class AuthenticationError(APIError):
    """API 认证失败（密钥错误或无效）"""
    
    def __init__(self, message: str = "API 认证失败", suggestion: Optional[str] = None):
        super().__init__(
            message=message,
            suggestion=suggestion or "请检查 OPENAI_API_KEY 环境变量是否正确设置",
            retry_after=None
        )


class RateLimitError(APIError):
    """API 调用频率超限"""
    
    def __init__(self, message: str = "API 调用频率超限", retry_after: Optional[int] = 60):
        super().__init__(
            message=message,
            suggestion=f"请等待 {retry_after} 秒后重试，或检查您的 API 配额",
            retry_after=retry_after
        )


class NetworkError(APIError):
    """网络连接失败"""
    
    def __init__(self, message: str = "网络连接失败", suggestion: Optional[str] = None):
        super().__init__(
            message=message,
            suggestion=suggestion or "请检查网络连接，确认 API 地址可访问",
            retry_after=5
        )


class ModelNotFoundError(APIError):
    """模型不可用"""
    
    def __init__(self, model_name: Optional[str] = None):
        msg = "模型不可用"
        if model_name:
            msg = f"模型 '{model_name}' 不可用"
        super().__init__(
            message=msg,
            suggestion="请检查模型名称是否正确，或使用 --model 参数切换模型",
            retry_after=None
        )


class ToolError(SimpleAgentException):
    """工具执行错误"""
    
    def __init__(self, message: str, suggestion: Optional[str] = None):
        super().__init__(
            message=message,
            recoverable=True,  # 工具错误可以恢复
            suggestion=suggestion or "请检查工具参数，然后重试"
        )


class SystemError(SimpleAgentException):
    """系统级错误"""
    
    def __init__(self, message: str, suggestion: Optional[str] = None):
        super().__init__(
            message=message,
            recoverable=False,  # 系统错误通常不可恢复
            suggestion=suggestion or "请重启 SimpleAgent 或检查系统配置"
        )


def classify_exception(e: Exception) -> SimpleAgentException:
    """将原始异常分类为 SimpleAgent 异常
    
    优先识别 OpenAI 官方异常类型，其次根据错误字符串进行匹配。
    """
    
    # 尝试导入 OpenAI 异常类型
    try:
        from openai import (
            AuthenticationError as OpenAIAuthError,
            RateLimitError as OpenAIRateLimitError,
            APIConnectionError,
            APITimeoutError,
            NotFoundError,
            BadRequestError,
        )
        
        # 优先匹配 OpenAI 异常类型（最精确）
        if isinstance(e, OpenAIAuthError):
            return AuthenticationError("API 认证失败")
        
        if isinstance(e, OpenAIRateLimitError):
            return RateLimitError("API 调用频率超限", retry_after=60)
        
        if isinstance(e, APIConnectionError):
            return NetworkError("无法连接到 API 服务器")
        
        if isinstance(e, APITimeoutError):
            return NetworkError("API 请求超时", suggestion="请检查网络连接或稍后重试")
        
        if isinstance(e, NotFoundError):
            # 可能是模型不存在或端点不存在
            error_str = str(e).lower()
            if "model" in error_str:
                return ModelNotFoundError()
            return APIError("API 资源不存在", suggestion="请检查 API 端点配置")
        
        if isinstance(e, BadRequestError):
            error_str = str(e).lower()
            if "model" in error_str:
                return ModelNotFoundError()
            return APIError("请求参数错误", suggestion="请检查请求参数是否正确")
            
    except ImportError:
        # OpenAI 库未安装或版本不支持，降级到字符串匹配
        pass
    
    # 降级：基于错误字符串的模糊匹配
    error_str = str(e).lower()
    
    if "authentication" in error_str or "api key" in error_str or "unauthorized" in error_str:
        return AuthenticationError("API 认证失败")
    
    if "rate limit" in error_str or "quota" in error_str:
        return RateLimitError("API 调用频率超限", retry_after=60)
    
    if "network" in error_str or "connection" in error_str or "timeout" in error_str:
        return NetworkError("网络连接失败")
    
    if "model" in error_str and ("not found" in error_str or "does not exist" in error_str):
        import re
        match = re.search(r"model\s+['\"]?([^'\"\s]+)['\"]?\s+(not found|does not exist)", error_str)
        model_name = match.group(1) if match else None
        return ModelNotFoundError(model_name)
    
    # 文件操作相关异常
    if "filenotfounderror" in type(e).__name__.lower() or "no such file" in error_str:
        return ToolError(
            "文件不存在",
            "请确认文件路径正确，或使用 list_files 查看可用文件"
        )
    
    if "permission" in error_str:
        return ToolError(
            "权限不足",
            "请检查文件权限或使用其他路径"
        )
    
    # 系统级异常
    if "memory" in error_str or "out of memory" in error_str:
        return SystemError(
            "内存不足",
            "请关闭其他应用程序或重启 SimpleAgent"
        )
    
    # 默认：可恢复的通用错误
    return SimpleAgentException(
        message=f"发生未知错误: {str(e)}",
        recoverable=True,
        suggestion="如果问题持续，请尝试 /clear 清空对话或重启 SimpleAgent"
    )


def format_error_message(exception: SimpleAgentException) -> str:
    """格式化错误消息为用户友好的文本"""
    
    msg = f"\n❌ 错误: {exception.message}"
    
    if exception.suggestion:
        msg += f"\n💡 建议: {exception.suggestion}"
    
    if exception.recoverable:
        msg += "\n✓ 会话继续，您可以继续输入命令"
    else:
        msg += "\n⚠ 会话需要退出，请根据建议处理后重新启动"
    
    return msg