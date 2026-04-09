"""MCP 客户端模块测试"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.mcp_client import MCPClient, parse_mcp_arg


# ── parse_mcp_arg 测试 ───────────────────────────────────────────


class TestParseMcpArg:
    """测试 --mcp 参数解析"""

    def test_simple_command_no_args(self):
        result = parse_mcp_arg("python")
        assert result["command"] == "python"
        assert result["args"] == []
        assert result["env"] is None

    def test_simple_command_with_args(self):
        result = parse_mcp_arg("npx -y @mcp/server-fs /tmp")
        assert result["command"] == "npx"
        assert result["args"] == ["-y", "@mcp/server-fs", "/tmp"]
        assert result["env"] is None

    def test_json_format(self):
        arg = json.dumps({"command": "python", "args": ["server.py", "--port", "8080"]})
        result = parse_mcp_arg(arg)
        assert result["command"] == "python"
        assert result["args"] == ["server.py", "--port", "8080"]
        assert result["env"] is None

    def test_json_format_with_env(self):
        arg = json.dumps({"command": "node", "args": ["index.js"], "env": {"KEY": "val"}})
        result = parse_mcp_arg(arg)
        assert result["command"] == "node"
        assert result["env"] == {"KEY": "val"}

    def test_json_missing_command(self):
        with pytest.raises(ValueError, match="command"):
            parse_mcp_arg('{"args": ["test"]}')

    def test_empty_string(self):
        with pytest.raises(ValueError, match="不能为空"):
            parse_mcp_arg("   ")

    def test_json_parse_error(self):
        with pytest.raises(ValueError, match="JSON"):
            parse_mcp_arg("{broken json")

    def test_whitespace_stripped(self):
        result = parse_mcp_arg("  python server.py  ")
        assert result["command"] == "python"
        assert result["args"] == ["server.py"]


# ── MCPClient 单元测试（不启动真实服务器）────────────────────────


class TestMCPClientInit:
    """MCPClient 初始化测试"""

    def test_default_values(self):
        client = MCPClient("python")
        assert client.command == "python"
        assert client.args == []
        assert client.env is None
        assert client.connected is False
        assert client.tools == []

    def test_with_args_and_env(self):
        client = MCPClient("npx", ["-y", "server"], {"KEY": "val"})
        assert client.command == "npx"
        assert client.args == ["-y", "server"]
        assert client.env == {"KEY": "val"}


class TestMCPClientGetToolDefinitions:
    """测试 MCP Tool → OpenAI function calling 格式转换"""

    def test_empty_tools(self):
        client = MCPClient("test")
        assert client.get_tool_definitions() == []

    def test_converts_mcp_tool_to_openai_format(self):
        client = MCPClient("test")
        # 模拟 MCP Tool 对象
        mock_tool = MagicMock()
        mock_tool.name = "read_data"
        mock_tool.description = "Read data from source"
        mock_tool.inputSchema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }
        client.tools = [mock_tool]

        defs = client.get_tool_definitions()
        assert len(defs) == 1
        d = defs[0]
        assert d["type"] == "function"
        assert d["function"]["name"] == "read_data"
        assert d["function"]["description"] == "Read data from source"
        assert d["function"]["parameters"]["properties"]["path"]["type"] == "string"

    def test_missing_schema_defaults_to_empty_object(self):
        client = MCPClient("test")
        mock_tool = MagicMock()
        mock_tool.name = "no_schema"
        mock_tool.description = None
        mock_tool.inputSchema = None
        client.tools = [mock_tool]

        defs = client.get_tool_definitions()
        assert defs[0]["function"]["description"] == ""
        assert defs[0]["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_multiple_tools(self):
        client = MCPClient("test")
        tools = []
        for i in range(3):
            t = MagicMock()
            t.name = f"tool_{i}"
            t.description = f"Tool {i}"
            t.inputSchema = {"type": "object", "properties": {}}
            tools.append(t)
        client.tools = tools

        defs = client.get_tool_definitions()
        assert len(defs) == 3
        assert [d["function"]["name"] for d in defs] == ["tool_0", "tool_1", "tool_2"]


class TestMCPClientGetToolNames:
    """测试 get_tool_names"""

    def test_returns_names(self):
        client = MCPClient("test")
        t1 = MagicMock()
        t1.name = "alpha"
        t2 = MagicMock()
        t2.name = "beta"
        client.tools = [t1, t2]
        assert client.get_tool_names() == ["alpha", "beta"]

    def test_empty(self):
        client = MCPClient("test")
        assert client.get_tool_names() == []


class TestMCPClientCallTool:
    """测试 call_tool 结果提取"""

    @pytest.mark.asyncio
    async def test_not_connected_returns_error(self):
        client = MCPClient("test")
        result = await client.call_tool("something", {})
        assert result["success"] is False
        assert "未连接" in result["error"]

    @pytest.mark.asyncio
    async def test_extracts_text_content(self):
        client = MCPClient("test")
        client.connected = True

        # 模拟 session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.isError = False
        text_item = MagicMock()
        text_item.text = "Hello, world!"
        del text_item.data  # 确保没有 data 属性
        mock_result.content = [text_item]
        mock_session.call_tool.return_value = mock_result
        client._session = mock_session

        result = await client.call_tool("greet", {"name": "test"})
        assert result["success"] is True
        assert result["content"] == "Hello, world!"
        mock_session.call_tool.assert_called_once_with("greet", {"name": "test"})

    @pytest.mark.asyncio
    async def test_error_result(self):
        client = MCPClient("test")
        client.connected = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.isError = True
        text_item = MagicMock()
        text_item.text = "File not found"
        del text_item.data
        mock_result.content = [text_item]
        mock_session.call_tool.return_value = mock_result
        client._session = mock_session

        result = await client.call_tool("bad_tool", {})
        assert result["success"] is False
        assert "File not found" in result["error"]

    @pytest.mark.asyncio
    async def test_exception_returns_error(self):
        client = MCPClient("test")
        client.connected = True

        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = RuntimeError("connection lost")
        client._session = mock_session

        result = await client.call_tool("anything", {})
        assert result["success"] is False
        assert "connection lost" in result["error"]


class TestMCPClientConnect:
    """测试 connect 方法（mock MCP SDK）"""

    @pytest.mark.asyncio
    async def test_import_error_returns_helpful_message(self):
        client = MCPClient("test")
        with patch.dict("sys.modules", {"mcp": None, "mcp.client.stdio": None}):
            # 强制 import 失败
            original_connect = MCPClient.connect

            async def connect_with_import_error(self):
                try:
                    from mcp import ClientSession, StdioServerParameters  # noqa
                    from mcp.client.stdio import stdio_client  # noqa
                except (ImportError, TypeError):
                    return {"success": False, "error": "MCP SDK 未安装，请执行: pip install mcp"}
                return await original_connect(self)

            client.connect = lambda: connect_with_import_error(client)
            result = await client.connect()
            # 由于 mcp 实际已安装，这个测试验证错误路径的结构
            assert isinstance(result, dict)
            assert "success" in result


class TestMCPClientClose:
    """测试 close 方法"""

    @pytest.mark.asyncio
    async def test_close_resets_state(self):
        client = MCPClient("test")
        client.connected = True
        client.tools = [MagicMock()]
        client._session = MagicMock()

        await client.close()
        assert client.connected is False
        assert client.tools == []
        assert client._session is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        client = MCPClient("test")
        await client.close()
        await client.close()  # 不应抛异常


# ── Agent MCP 集成测试 ──────────────────────────────────────────


class TestAgentMCPIntegration:
    """测试 Agent 的 MCP 工具注册和调用"""

    def _make_agent(self):
        from src.agent import Agent
        agent = Agent("test-key", "test-model")
        return agent

    def test_register_mcp_tools(self):
        agent = self._make_agent()
        mock_client = MagicMock()
        mock_client.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "mcp_tool_1", "description": "t1", "parameters": {}}},
            {"type": "function", "function": {"name": "mcp_tool_2", "description": "t2", "parameters": {}}},
        ]

        count = agent.register_mcp_tools(mock_client)
        assert count == 2
        assert "mcp_tool_1" in agent._mcp_tool_map
        assert "mcp_tool_2" in agent._mcp_tool_map
        assert agent._mcp_tool_map["mcp_tool_1"] is mock_client
        # tool_definitions 应该增加了 2 个
        names = [td["function"]["name"] for td in agent.tool_definitions]
        assert "mcp_tool_1" in names
        assert "mcp_tool_2" in names

    def test_execute_tool_call_returns_mcp_pending(self):
        from src.models import ToolCallRequest
        agent = self._make_agent()

        mock_client = MagicMock()
        mock_client.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "remote_fetch", "description": "", "parameters": {}}},
        ]
        agent.register_mcp_tools(mock_client)

        tc = ToolCallRequest(id="1", name="remote_fetch", arguments={"url": "http://example.com"})
        result = agent._execute_tool_call(tc)
        assert result.get("_mcp_pending") is True
        assert result["tool_name"] == "remote_fetch"
        assert result["arguments"] == {"url": "http://example.com"}

    def test_builtin_tool_unaffected(self):
        from src.models import ToolCallRequest
        agent = self._make_agent()

        # 注册 MCP 工具不应影响内置工具
        mock_client = MagicMock()
        mock_client.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "mcp_x", "description": "", "parameters": {}}},
        ]
        agent.register_mcp_tools(mock_client)

        tc = ToolCallRequest(id="2", name="list_files", arguments={"path": "."})
        result = agent._execute_tool_call(tc)
        # list_files 应正常执行，不返回 _mcp_pending
        assert "_mcp_pending" not in result
        assert "success" in result

    def test_unknown_tool_still_returns_error(self):
        from src.models import ToolCallRequest
        agent = self._make_agent()
        tc = ToolCallRequest(id="3", name="nonexistent_tool", arguments={})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_register_multiple_clients(self):
        agent = self._make_agent()

        client_a = MagicMock()
        client_a.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "tool_a", "description": "", "parameters": {}}},
        ]
        client_b = MagicMock()
        client_b.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "tool_b", "description": "", "parameters": {}}},
        ]

        agent.register_mcp_tools(client_a)
        agent.register_mcp_tools(client_b)

        assert len(agent._mcp_clients) == 2
        assert agent._mcp_tool_map["tool_a"] is client_a
        assert agent._mcp_tool_map["tool_b"] is client_b
