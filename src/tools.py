"""
工具模块 - 提供文件操作和命令执行功能
"""

import os
import subprocess
import glob
from typing import Dict, Any, Optional


class ToolExecutor:
    """简单的工具执行类"""

    @staticmethod
    def read_file(path: str) -> Dict[str, Any]:
        """读取文件内容"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"success": True, "content": content, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}

    @staticmethod
    def write_file(path: str, content: str) -> Dict[str, Any]:
        """写入文件内容"""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}

    @staticmethod
    def edit_file(path: str, old_content: str, new_content: str, preview: bool = False) -> Dict[str, Any]:
        """编辑文件内容（仅替换第一个匹配）
        
        Args:
            path: 文件路径
            old_content: 要替换的旧内容
            new_content: 新内容
            preview: 是否仅预览而不写入文件
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            if old_content not in content:
                return {"success": False, "error": "Old content not found", "path": path}

            # 只替换第一个匹配，避免全局替换导致的数据泄漏
            new_content_full = content.replace(old_content, new_content, 1)
            
            # 生成 diff 信息（显示变更的上下文）
            diff_info = {
                "old_content": old_content,
                "new_content": new_content,
                "old_length": len(old_content),
                "new_length": len(new_content),
            }
            
            # 预览模式：不写入文件，返回 diff
            if preview:
                return {
                    "success": True,
                    "path": path,
                    "preview": True,
                    "diff": diff_info
                }
            
            # 实际写入文件
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content_full)

            return {"success": True, "path": path, "diff": diff_info}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}

    @staticmethod
    def list_files(path: str = ".") -> Dict[str, Any]:
        """列出目录内容"""
        try:
            if not os.path.exists(path):
                return {"success": False, "error": "Path does not exist", "path": path}

            items = []
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    items.append({"name": item, "type": "directory", "path": item_path})
                else:
                    items.append({"name": item, "type": "file", "path": item_path,
                                "size": os.path.getsize(item_path)})

            return {"success": True, "items": items, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}

    @staticmethod
    def execute_command(command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """执行 shell 命令"""
        # 拒绝空命令或纯空白命令
        if not command or not command.strip():
            return {"success": False, "error": "Command cannot be empty", "command": command}

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or os.getcwd(),
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timed out", "command": command}
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}

    @staticmethod
    def search_files(pattern: str, path: str = ".") -> Dict[str, Any]:
        """搜索匹配模式的文件"""
        try:
            matches = []
            search_path = os.path.join(path, "**", pattern) if pattern != "." else path

            for match in glob.glob(search_path, recursive=True):
                if os.path.isfile(match):
                    matches.append({
                        "path": match,
                        "size": os.path.getsize(match)
                    })

            return {"success": True, "matches": matches, "pattern": pattern}
        except Exception as e:
            return {"success": False, "error": str(e), "pattern": pattern}


def default_tools() -> ToolExecutor:
    """返回默认的工具执行器"""
    return ToolExecutor()


# OpenAI Function Calling 工具定义
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定路径的文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将内容写入指定路径的文件（会覆盖已有内容）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑文件内容，将旧内容替换为新内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的文件路径"
                    },
                    "old_content": {
                        "type": "string",
                        "description": "要被替换的旧内容（必须精确匹配）"
                    },
                    "new_content": {
                        "type": "string",
                        "description": "替换后的新内容"
                    },
                    "preview": {
                        "type": "boolean",
                        "description": "是否仅预览而不写入文件（默认 false）",
                        "default": False
                    }
                },
                "required": ["path", "old_content", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出指定目录下的文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出内容的目录路径，默认为当前目录",
                        "default": "."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "在 shell 中执行命令",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令"
                    },
                    "cwd": {
                        "type": "string",
                        "description": "命令执行的工作目录（可选）"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "搜索匹配指定模式的文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "文件名匹配模式（支持 glob 通配符，如 *.py）"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索的根目录路径，默认为当前目录",
                        "default": "."
                    }
                },
                "required": ["pattern"]
            }
        }
    }
]