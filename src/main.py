#!/usr/bin/env python3
"""
SimpleAgent — a coding agent that evolves itself.

Started as a Rust project. Now converted to Python without external agent frameworks.

Usage:
  python main.py
  python main.py --model DeepSeek-V3_2-Online-32k
  python main.py --provider deepseek
  python main.py --provider groq --model llama-3.3-70b-versatile
  python main.py --skills ./skills
  python main.py --system "请专注于安全性"
  python main.py --system ./my_prompt.txt
  python -m src.main

Commands:
  /help              Show available commands
  /quit, /exit       Exit the agent
  /clear             Clear conversation history
  /model <name>      Switch model mid-session
  /usage             Show session token stats
  /compact           Summarize old messages and free context space
  /undo              Revert last file change
  /diff              Show git diff of all session changes
  /commit [msg]      Git commit modified files
  /save [name]       Save session to file
  /load <name>       Load session from file
  /replay <logfile>  Re-execute user inputs from a JSONL session log
  /spec <specfile>   Generate implementation plan from a spec file
  \"\"\" or '''         Enter multi-line input mode (paste code blocks)
"""

import asyncio

# 使用相对导入，与包内其他模块保持一致
from .colors import RESET, BOLD, DIM, GREEN, YELLOW, CYAN, RED
from .models import ToolCallRequest, Usage
from .tools import ToolExecutor, TOOL_DEFINITIONS, default_tools
from .skills import Skill, SkillSet
from .prompt import (
    PROMPT_CONTEXT_FILES,
    read_prompt_file,
    render_prompt_context,
    build_system_prompt,
    check_context_truncation,
    detect_project_info,
    emit_truncation_warnings,
)
from .agent import Agent
from .git import is_git_repo, get_git_branch, get_git_status_summary, git_add_and_commit, git_diff_files
from .providers import ProviderConfig, PROVIDERS, get_provider, list_providers, resolve_provider
from .logger import SessionLogger, DEFAULT_LOG_DIR, load_transcript
from .mcp_client import MCPClient, parse_mcp_arg
from .memory import MemoryManager, WorkingSummary, ArchivalEntry
from .router import ModelRouter, RouterConfig, TaskComplexity, classify_complexity
from .cli import (
    DEFAULT_MODEL,
    SESSIONS_DIR,
    LOGS_DIR,
    MarkdownRenderer,
    format_diff_lines,
    format_elapsed,
    match_command,
    print_banner,
    print_usage,
    truncate,
    read_user_input,
    load_system_prompt,
    parse_args,
    resolve_model_for_provider,
    handle_slash_command,
    render_event,
    main,
    run,
)

# 保留模块级 SYSTEM_PROMPT 以兼容外部引用
SYSTEM_PROMPT = build_system_prompt()

if __name__ == "__main__":
    asyncio.run(main())
