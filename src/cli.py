"""
CLI 交互和显示模块
"""
import sys

# ANSI color helpers
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
CYAN = "\x1b[36m"
RED = "\x1b[31m"

# 默认模型名称
DEFAULT_MODEL = 'Pro/zai-org/GLM-5'


def print_banner():
    """打印欢迎横幅"""
    print(f"\n{BOLD}{CYAN}  SimpleAgent{RESET} {DIM}— a coding agent growing up in public{RESET}")
    print(f"{DIM}  Type /quit to exit, /clear to reset{RESET}\n")


def print_usage(usage):
    """打印 Token 使用统计"""
    if usage.input > 0 or usage.output > 0:
        print(f"\n{DIM}  tokens: {usage.input} in / {usage.output} out{RESET}")


def truncate(s: str, max_len: int) -> str:
    """截断字符串显示"""
    if len(s) <= max_len:
        return s
    return s[:max_len]


def print_version():
    """打印版本信息"""
    try:
        from . import __version__
        print(f"SimpleAgent {__version__}")
    except ImportError:
        print("SimpleAgent (unknown version)")