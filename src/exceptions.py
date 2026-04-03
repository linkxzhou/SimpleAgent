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
    """API 相关错误"""
    
    def __init__(self, message: str, suggestion: Optional[str] = None):
        super().__init__(
            message=message,
            recoverable=True,  # API 错误通常可以恢复
            suggestion=suggestion or "请检查网络连接和 API 配置，然后重试"
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
    """将原始异常分类为 SimpleAgent 异常"""
    
    # OpenAI API 相关异常
    error_str = str(e).lower()
    
    if "authentication" in error_str or "api key" in error_str or "unauthorized" in error_str:
        return APIError(
            "API 认证失败",
            "请检查 OPENAI_API_KEY 环境变量是否正确设置"
        )
    
    if "rate limit" in error_str or "quota" in error_str:
        return APIError(
            "API 调用频率超限",
            "请等待几分钟后重试，或检查您的 API 配额"
        )
    
    if "network" in error_str or "connection" in error_str or "timeout" in error_str:
        return APIError(
            "网络连接失败",
            "请检查网络连接，确认 API 地址可访问"
        )
    
    if "model" in error_str or "not found" in error_str:
        return APIError(
            "模型不可用",
            "请检查模型名称是否正确，或切换到其他模型"
        )
    
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