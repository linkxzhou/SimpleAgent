"""MCP 客户端模块 - 连接 MCP 服务器并将工具桥接到 Agent。

通过 stdio transport 连接 MCP 服务器，发现服务器提供的工具，
将 MCP Tool 转换为 OpenAI function calling 格式，并代理工具调用。

Usage:
    client = MCPClient("npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    await client.connect()
    tool_defs = client.get_tool_definitions()  # OpenAI 格式
    result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
    await client.close()
"""

import json
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional


class MCPClient:
    """MCP 客户端：连接单个 MCP 服务器并代理工具调用。
    
    Attributes:
        command: 启动 MCP 服务器的可执行文件
        args: 传递给服务器的命令行参数
        tools: 服务器提供的工具列表（MCP Tool 对象）
        connected: 是否已连接
    """

    def __init__(self, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None):
        """初始化 MCP 客户端。
        
        Args:
            command: MCP 服务器可执行文件路径（如 "npx", "python"）
            args: 命令行参数列表
            env: 环境变量覆盖（None 使用当前环境）
        """
        self.command = command
        self.args = args or []
        self.env = env
        self.tools: list = []
        self.connected = False
        self._session = None
        self._exit_stack = AsyncExitStack()

    async def connect(self) -> Dict[str, Any]:
        """连接到 MCP 服务器并发现工具。
        
        Returns:
            {"success": True, "tool_count": int, "tools": [tool_name, ...]}
            或 {"success": False, "error": str}
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            return {
                "success": False,
                "error": "MCP SDK 未安装，请执行: pip install mcp",
            }

        try:
            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env,
            )

            # 启动 stdio transport
            transport = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read_stream, write_stream = transport

            # 创建 ClientSession
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            # 初始化连接
            await self._session.initialize()

            # 发现工具
            result = await self._session.list_tools()
            self.tools = list(result.tools)
            self.connected = True

            tool_names = [t.name for t in self.tools]
            return {
                "success": True,
                "tool_count": len(self.tools),
                "tools": tool_names,
            }

        except Exception as e:
            self.connected = False
            return {"success": False, "error": str(e)}

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """调用 MCP 服务器上的工具。
        
        Args:
            name: 工具名称
            arguments: 工具参数字典
        
        Returns:
            {"success": True, "content": str} 或 {"success": False, "error": str}
        """
        if not self.connected or self._session is None:
            return {"success": False, "error": "MCP 客户端未连接"}

        try:
            result = await self._session.call_tool(name, arguments or {})

            # 提取文本内容
            texts = []
            for item in result.content:
                if hasattr(item, "text"):
                    texts.append(item.text)
                elif hasattr(item, "data"):
                    texts.append(f"[binary: {len(item.data)} bytes]")
                else:
                    texts.append(str(item))

            content = "\n".join(texts)

            if result.isError:
                return {"success": False, "error": content}

            return {"success": True, "content": content}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """将 MCP 工具转换为 OpenAI function calling 格式。
        
        Returns:
            OpenAI tools 格式的工具定义列表
        """
        definitions = []
        for tool in self.tools:
            definition = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema or {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            definitions.append(definition)
        return definitions

    def get_tool_names(self) -> List[str]:
        """返回所有 MCP 工具的名称列表。"""
        return [t.name for t in self.tools]

    async def close(self) -> None:
        """关闭 MCP 连接。幂等操作。"""
        self.connected = False
        self._session = None
        self.tools = []
        try:
            await self._exit_stack.aclose()
        except Exception:
            pass

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


def parse_mcp_arg(mcp_arg: str) -> Dict[str, Any]:
    """解析 --mcp 参数为 MCPClient 构造参数。
    
    支持两种格式：
    1. 简单命令字符串: "npx -y @modelcontextprotocol/server-filesystem /tmp"
    2. JSON 格式: '{"command": "python", "args": ["server.py"], "env": {"KEY": "val"}}'
    
    Args:
        mcp_arg: --mcp 参数值
    
    Returns:
        {"command": str, "args": list, "env": dict|None}
    
    Raises:
        ValueError: 参数格式无效
    """
    stripped = mcp_arg.strip()

    # 尝试 JSON 格式
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if "command" not in data:
                raise ValueError("JSON 格式的 --mcp 参数必须包含 'command' 字段")
            return {
                "command": data["command"],
                "args": data.get("args", []),
                "env": data.get("env"),
            }
        except json.JSONDecodeError as e:
            raise ValueError(f"--mcp JSON 解析失败: {e}") from e

    # 简单命令字符串：按空格分割
    parts = stripped.split()
    if not parts:
        raise ValueError("--mcp 参数不能为空")

    return {
        "command": parts[0],
        "args": parts[1:],
        "env": None,
    }
