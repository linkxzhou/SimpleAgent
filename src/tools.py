"""工具模块 - 提供文件操作、命令执行和网络搜索功能，以及 OpenAI function calling 工具定义。"""

import os
import glob
import difflib
import subprocess
from typing import Dict, Any, Optional, List


class ToolExecutor:
    """简单的工具执行类"""
    
    def __init__(self):
        # undo 栈：每个元素是 (path, old_content)，old_content 为 None 表示文件之前不存在
        self._undo_stack: list = []
    
    def record_undo(self, path: str, old_content: Optional[str]) -> None:
        """记录一次文件修改前的状态，用于后续 undo。
        
        Args:
            path: 被修改的文件路径
            old_content: 修改前的文件内容，None 表示文件之前不存在
        """
        self._undo_stack.append((path, old_content))
    
    def get_modified_files(self) -> list:
        """返回本会话中被修改过的文件路径列表（去重，保持首次出现顺序）。
        
        Returns:
            文件路径的有序列表
        """
        seen = set()
        result = []
        for path, _ in self._undo_stack:
            if path not in seen:
                seen.add(path)
                result.append(path)
        return result
    
    def undo(self) -> Dict[str, Any]:
        """撤销上一次文件更改，恢复文件到修改前的状态。
        
        Returns:
            包含 success、path 和可选 diff 的结果字典
        """
        if not self._undo_stack:
            return {"success": False, "error": "没有可撤销的更改"}
        
        path, old_content = self._undo_stack.pop()
        
        try:
            # 读取当前内容用于生成 diff
            current_content = ""
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        current_content = f.read()
                except Exception:
                    current_content = ""
            
            if old_content is None:
                # 文件之前不存在，删除它
                if os.path.isfile(path):
                    os.remove(path)
                diff = ToolExecutor._generate_diff(current_content, "", path)
            else:
                # 恢复旧内容
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(old_content)
                diff = ToolExecutor._generate_diff(current_content, old_content, path)
            
            result: Dict[str, Any] = {"success": True, "path": path}
            if diff:
                result["diff"] = diff
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}
    
    @staticmethod
    def _generate_diff(old_content: str, new_content: str, path: str) -> str:
        """生成 unified diff 格式的差异文本。
        
        超过 MAX_DIFF_LINES 行时截断，保留头部并附加省略标记。
        
        Args:
            old_content: 修改前的内容
            new_content: 修改后的内容
            path: 文件路径（用于 diff 头部显示）
        
        Returns:
            unified diff 字符串，无差异时返回空字符串
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        ))
        if not diff_lines:
            return ""
        max_lines = ToolExecutor.MAX_DIFF_LINES
        if len(diff_lines) > max_lines:
            omitted = len(diff_lines) - max_lines
            diff_lines = diff_lines[:max_lines]
            diff_lines.append(f"... (省略 {omitted} 行)")
        # 去除每行末尾换行（difflib 输出带 keepends），用 join 统一换行
        return "\n".join(line.rstrip("\n") for line in diff_lines)
    
    @staticmethod
    def read_file(path: str) -> Dict[str, Any]:
        """读取文件内容。超过 MAX_READ_SIZE 时截断并附加警告。"""
        try:
            file_size = os.path.getsize(path)
            truncated = file_size > ToolExecutor.MAX_READ_SIZE
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read(ToolExecutor.MAX_READ_SIZE) if truncated else f.read()
            result: Dict[str, Any] = {"success": True, "content": content, "path": path}
            if truncated:
                result["truncated"] = True
                result["file_size"] = file_size
                result["read_size"] = ToolExecutor.MAX_READ_SIZE
                result["warning"] = (
                    f"文件过大（{file_size:,} 字节），已截断为前 {ToolExecutor.MAX_READ_SIZE:,} 字节。"
                    f"如需查看特定部分，请使用 execute_command 配合 head/tail/sed 等命令。"
                )
            return result
        except UnicodeDecodeError:
            return {
                "success": False,
                "error": f"无法读取：{path} 是二进制文件，不是 UTF-8 文本。请使用 execute_command 配合 file、xxd、hexdump 等命令查看。",
                "path": path,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}
    
    @staticmethod
    def write_file(path: str, content: str) -> Dict[str, Any]:
        """写入文件内容。返回结果中包含 old_content 供调用方使用（如 undo 备份）。"""
        try:
            # 读取旧内容（如果文件已存在）用于生成 diff 和 undo 备份
            old_content: Optional[str] = None
            if os.path.isfile(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        old_content = f.read()
                except Exception:
                    old_content = None
            
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            diff = ToolExecutor._generate_diff(old_content or "", content, path)
            result: Dict[str, Any] = {"success": True, "path": path, "old_content": old_content}
            if diff:
                result["diff"] = diff
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "path": path}
    
    @staticmethod
    def edit_file(path: str, old_content: str, new_content: str) -> Dict[str, Any]:
        """编辑文件内容（替换）。返回结果中包含 old_content_full（完整旧文件内容）供调用方使用（如 undo 备份）。"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_content not in content:
                return {"success": False, "error": "Old content not found", "path": path}
            
            new_content_full = content.replace(old_content, new_content, 1)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content_full)
            
            diff = ToolExecutor._generate_diff(content, new_content_full, path)
            result: Dict[str, Any] = {"success": True, "path": path, "old_content_full": content}
            if diff:
                result["diff"] = diff
            return result
        except UnicodeDecodeError:
            return {
                "success": False,
                "error": f"无法编辑：{path} 是二进制文件，不是 UTF-8 文本。edit_file 仅支持文本文件。",
                "path": path,
            }
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
    
    DEFAULT_COMMAND_TIMEOUT = 120  # 默认超时秒数
    MAX_DIFF_LINES = 50  # diff 最大行数，超过则截断
    MAX_READ_SIZE = 100 * 1024  # read_file 最大读取字节数（100KB ≈ ~25k tokens）

    @staticmethod
    def execute_command(command: str, cwd: Optional[str] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """执行 shell 命令"""
        if timeout is None:
            timeout = ToolExecutor.DEFAULT_COMMAND_TIMEOUT
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=cwd or os.getcwd(),
                capture_output=True, 
                text=True,
                timeout=timeout
            )
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {timeout}s", "command": command}
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

    @staticmethod
    def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
        """使用 DuckDuckGo 搜索网络内容，无需 API Key"""
        try:
            # 优先尝试新包名 ddgs，回退到旧包名 duckduckgo_search
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
        except ImportError:
            return {
                "success": False,
                "error": "DuckDuckGo 搜索库未安装，请执行: pip install ddgs",
                "query": query,
            }

        # 限制最大结果数量在合理范围内
        max_results = max(1, min(max_results, 20))

        try:
            # 抑制 duckduckgo_search 包改名产生的 RuntimeWarning
            # 注：DDGS.__init__ 内部用 simplefilter("always") 覆盖外部 filter，
            # 因此必须用 record=True 捕获再选择性重发
            import warnings
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                ddgs = DDGS()
            # 重新发出非改名的 warning
            for w in caught:
                if not (issubclass(w.category, RuntimeWarning)
                        and "renamed" in str(w.message).lower()):
                    warnings.warn_explicit(
                        w.message, w.category, w.filename, w.lineno,
                        source=w.source,
                    )
            results: List[Dict[str, str]] = ddgs.text(query, max_results=max_results)

            # 每条结果包含 title、href、body
            items = []
            for r in results:
                items.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })

            return {
                "success": True,
                "query": query,
                "results": items,
                "count": len(items),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "query": query}


def default_tools() -> ToolExecutor:
    """返回默认的工具执行器"""
    return ToolExecutor()


# ============================================================
# OpenAI Function Calling 工具定义
# ============================================================

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
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "命令超时秒数（可选），默认为 120 秒。长时间命令（如 pip install、pytest 大项目）可设置更大值"
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
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "使用 DuckDuckGo 搜索网络内容，无需 API Key。适用于查找文档、技术方案、最新信息等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数量（1-20），默认为 5",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }
]
