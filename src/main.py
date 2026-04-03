#!/usr/bin/env python3
"""
SimpleAgent — a coding agent that evolves itself.

Started as a Rust project. Now converted to Python without external agent frameworks.

Usage:
  python src/main.py
  OPENAI_BASE_URL=https://api.siliconflow.cn/v1 python src/main.py
  OPENAI_MODEL=Pro/zai-org/GLM-5 python src/main.py
  python src/main.py --model Pro/zai-org/GLM-5
  python src/main.py --skills ./skills
  python src/main.py --version

Commands:
  /quit, /exit    Exit the agent
  /clear          Clear conversation history
  /model <name>   Switch model mid-session
"""

import os
import sys
import asyncio
import argparse
from dotenv import load_dotenv

from openai import OpenAI

from .agent import Agent
from .models import SkillSet
from .tools import default_tools
from .exceptions import classify_exception, format_error_message, SystemError
from .cli import (
    print_banner,
    print_usage,
    print_version,
    truncate,
    DEFAULT_MODEL,
    RESET,
    BOLD,
    DIM,
    GREEN,
    YELLOW,
    RED,
)


def parse_args():
    """解析命令行参数"""
    default_model = os.environ.get('OPENAI_MODEL', DEFAULT_MODEL)

    parser = argparse.ArgumentParser(
        description='SimpleAgent - A coding agent that evolves itself.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Usage:
  python main.py                              # Run with default settings

Environment Variables:
  OPENAI_API_KEY        Your OpenAI API key (required)
  OPENAI_BASE_URL       Custom API endpoint (optional)
  OPENAI_MODEL          Default model to use (optional)

Examples:
  OPENAI_API_KEY=sk-xxx python main.py
    Run with API key from environment variable

  OPENAI_BASE_URL=https://api.siliconflow.cn/v1 python main.py
    Run with custom API endpoint

  OPENAI_MODEL=Pro/zai-org/GLM-5 python main.py
    Run with specific model from environment

  python main.py --model Pro/zai-org/GLM-5
    Run with specific model (overrides env)

  python main.py --skills ./skills
    Load skills from directory

  python main.py --version
    Show version information

Interactive Commands:
  /quit, /exit    Exit the agent
  /clear          Clear conversation history
  /model <name>   Switch model mid-session

For more information: https://github.com/linkxzhou/SimpleAgent
        '''
    )

    parser.add_argument(
        '--model',
        default=default_model,
        metavar='NAME',
        help='Model to use (default: %(default)s, env: OPENAI_MODEL)'
    )
    parser.add_argument(
        '--skills',
        nargs='+',
        metavar='DIR',
        help='Skill directories to load'
    )
    parser.add_argument(
        '--version',
        action='store_true',
        help='Show version and exit'
    )

    return parser.parse_args()


async def main():
    """主入口函数"""
    # 加载 .env 文件中的环境变量
    load_dotenv()

    args = parse_args()

    # 处理 --version 参数
    if args.version:
        print_version()
        sys.exit(0)

    api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('API_KEY')
    if not api_key:
        print("Error: Set OPENAI_API_KEY or API_KEY environment variable")
        sys.exit(1)

    base_url = os.environ.get('OPENAI_BASE_URL')
    if not args.model or len(args.model) <= 0:
        args.model = os.environ.get('OPENAI_MODEL', DEFAULT_MODEL)

    skills = SkillSet()
    if args.skills:
        skills.load(args.skills)

    agent = Agent(api_key, args.model, base_url=base_url)
    agent.with_skills(skills)
    agent.with_tools(default_tools())

    print_banner()
    print(f"{DIM}  model: {args.model}{RESET}")
    if base_url:
        print(f"{DIM}  base_url: {base_url}{RESET}")
    if not skills.is_empty():
        print(f"{DIM}  skills: {len(skills)} loaded{RESET}")
    print(f"{DIM}  cwd:   {os.getcwd()}{RESET}\n")

    while True:
        try:
            user_input = input(f"{BOLD}{GREEN}> {RESET}").strip()

            if not user_input:
                continue

            if user_input in ['/quit', '/exit']:
                break
            elif user_input == '/clear':
                agent.clear_conversation()
                print(f"{DIM}  (conversation cleared){RESET}\n")
                continue
            elif user_input.startswith('/model '):
                new_model = user_input[7:].strip()
                agent.with_model(new_model)
                agent.clear_conversation()
                print(f"{DIM}  (switched to {new_model}, conversation cleared){RESET}\n")
                continue

            # 处理事件流
            in_text = False
            last_usage = None

            async for event in agent.prompt(user_input):
                if event["type"] == "tool_start":
                    if in_text:
                        print()
                        in_text = False
                    tool_name = event["tool_name"]
                    tool_args = event["args"]

                    if tool_name == "execute_command":
                        cmd = tool_args.get("command", "...")
                        summary = f"$ {truncate(cmd, 80)}"
                    elif tool_name == "read_file":
                        path = tool_args.get("path", "?")
                        summary = f"read {path}"
                    elif tool_name == "write_file":
                        path = tool_args.get("path", "?")
                        summary = f"write {path}"
                    elif tool_name == "edit_file":
                        path = tool_args.get("path", "?")
                        summary = f"edit {path}"
                    elif tool_name == "list_files":
                        path = tool_args.get("path", ".")
                        summary = f"ls {path}"
                    elif tool_name == "search_files":
                        pattern = tool_args.get("pattern", "?")
                        summary = f"search '{truncate(pattern, 60)}'"
                    else:
                        summary = tool_name

                    print(f"{YELLOW}  ▶ {summary}{RESET}")
                    sys.stdout.flush()

                elif event["type"] == "tool_end":
                    tool_name = event["tool_name"]
                    result = event["result"]
                    success = result.get("success", False)
                    status = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
                    print(f"{DIM}    {status} {tool_name} done{RESET}")
                    sys.stdout.flush()

                elif event["type"] == "reasoning":
                    if in_text:
                        print()
                    print(f"{DIM}  💭 {truncate(event['content'], 200)}{RESET}")
                    in_text = False

                elif event["type"] == "text_update":
                    if not in_text:
                        print()
                        in_text = True
                    print(event["delta"], end="")
                    sys.stdout.flush()

                elif event["type"] == "agent_end":
                    last_usage = event["usage"]

                elif event["type"] == "error":
                    print(f"{RED}Error: {event['message']}{RESET}")

            if in_text:
                print()

            if last_usage:
                print_usage(last_usage)
            print()

        except KeyboardInterrupt:
            print("\n")
            break
        except EOFError:
            break
        except SystemError as e:
            # 不可恢复的系统错误，需要退出
            print(format_error_message(e))
            print(f"{DIM}  正在退出...{RESET}\n")
            break
        except Exception as e:
            # 所有其他异常：分类、显示错误信息、继续会话
            classified_error = classify_exception(e)
            print(format_error_message(classified_error))
            
            # 如果是不可恢复错误，退出会话
            if not classified_error.recoverable:
                print(f"{DIM}  正在退出...{RESET}\n")
                break

    print(f"\n{DIM}  bye 👋{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())