"""tests/test_models.py — ToolCallRequest、Usage 数据类测试"""

import json
from src.models import ToolCallRequest, Usage


class TestToolCallRequest:
    def test_basic_creation(self):
        tc = ToolCallRequest(id="call_1", name="read_file", arguments={"path": "foo.txt"})
        assert tc.id == "call_1"
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "foo.txt"}

    def test_to_openai_tool_call(self):
        tc = ToolCallRequest(id="call_2", name="write_file", arguments={"path": "a.txt", "content": "hello"})
        result = tc.to_openai_tool_call()
        assert result["id"] == "call_2"
        assert result["type"] == "function"
        assert result["function"]["name"] == "write_file"
        # arguments 应被序列化为 JSON 字符串
        args = json.loads(result["function"]["arguments"])
        assert args["path"] == "a.txt"
        assert args["content"] == "hello"

    def test_to_openai_tool_call_no_provider_fields(self):
        tc = ToolCallRequest(id="call_3", name="list_files", arguments={})
        result = tc.to_openai_tool_call()
        assert "provider_specific_fields" not in result
        assert "provider_specific_fields" not in result["function"]

    def test_to_openai_tool_call_with_provider_fields(self):
        tc = ToolCallRequest(
            id="call_4",
            name="read_file",
            arguments={"path": "x"},
            provider_specific_fields={"extra": True},
            function_provider_specific_fields={"fn_extra": 42},
        )
        result = tc.to_openai_tool_call()
        assert result["provider_specific_fields"] == {"extra": True}
        assert result["function"]["provider_specific_fields"] == {"fn_extra": 42}

    def test_arguments_unicode(self):
        tc = ToolCallRequest(id="call_5", name="write_file", arguments={"path": "中文.txt", "content": "你好"})
        result = tc.to_openai_tool_call()
        args = json.loads(result["function"]["arguments"])
        assert args["content"] == "你好"


class TestUsage:
    def test_defaults(self):
        u = Usage()
        assert u.input == 0
        assert u.output == 0

    def test_custom_values(self):
        u = Usage(input=100, output=50)
        assert u.input == 100
        assert u.output == 50

    def test_mutable(self):
        u = Usage()
        u.input += 10
        u.output += 5
        assert u.input == 10
        assert u.output == 5
