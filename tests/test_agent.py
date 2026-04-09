"""tests/test_agent.py — Agent 核心逻辑测试（不依赖真实 API）"""

import pytest
from unittest.mock import MagicMock, patch
from src.agent import Agent
from src.models import ToolCallRequest
from src.memory import WorkingSummary


class TestDetectFakeToolCalls:
    """测试 _detect_fake_tool_calls 静态方法"""

    # === 应检测到的真正伪工具调用 ===

    def test_detects_read_file_call(self):
        assert Agent._detect_fake_tool_calls('read_file("path")') is True

    def test_detects_write_file_call(self):
        assert Agent._detect_fake_tool_calls("write_file('a.txt', 'content')") is True

    def test_detects_edit_file_call(self):
        assert Agent._detect_fake_tool_calls('edit_file("f", "old", "new")') is True

    def test_detects_execute_command_call(self):
        assert Agent._detect_fake_tool_calls("execute_command('ls')") is True

    def test_detects_list_files_call(self):
        assert Agent._detect_fake_tool_calls('list_files(".")') is True

    def test_detects_search_files_call(self):
        assert Agent._detect_fake_tool_calls('search_files("*.py")') is True

    def test_detects_web_search_call(self):
        assert Agent._detect_fake_tool_calls('web_search("python tutorial")') is True

    # === 不应触发的场景 ===

    def test_normal_text_no_detection(self):
        assert Agent._detect_fake_tool_calls("这是一段普通文本，没有工具调用。") is False

    def test_empty_string(self):
        assert Agent._detect_fake_tool_calls("") is False

    def test_mentions_tool_without_parens(self):
        """仅提到工具名但不带括号时不应触发"""
        assert Agent._detect_fake_tool_calls("使用 read_file 来读取文件") is False

    # === 代码块和行内代码内不应触发（误报修复） ===

    def test_inline_code_not_detected(self):
        """行内代码 `read_file(path)` 不应触发"""
        assert Agent._detect_fake_tool_calls("可以用 `read_file(path)` 来读取") is False

    def test_fenced_code_block_not_detected(self):
        """围栏代码块内的工具调用不应触发"""
        text = '下面是示例：\n```python\nresult = read_file("test.txt")\nprint(result)\n```\n以上就是用法。'
        assert Agent._detect_fake_tool_calls(text) is False

    def test_fenced_code_block_tilde_not_detected(self):
        """用 ~~~ 围栏的代码块也不应触发"""
        text = '示例：\n~~~\nexecute_command("ls -la")\n~~~\n完成。'
        assert Agent._detect_fake_tool_calls(text) is False

    def test_multiple_inline_codes_not_detected(self):
        """多个行内代码都不应触发"""
        text = "使用 `read_file(path)` 读取文件，然后用 `write_file(path, content)` 写入。"
        assert Agent._detect_fake_tool_calls(text) is False

    def test_mixed_code_block_and_plain_text(self):
        """代码块内不触发，但代码块外的伪调用仍应触发"""
        text = '```python\nread_file("safe.txt")\n```\n现在我来执行 write_file("danger.txt", "bad")'
        assert Agent._detect_fake_tool_calls(text) is True

    def test_inline_code_safe_but_plain_text_detected(self):
        """行内代码安全，但行内代码外的伪调用仍检测"""
        text = '你可以用 `read_file(path)` 读取。我来帮你执行 edit_file("a", "b", "c")'
        assert Agent._detect_fake_tool_calls(text) is True

    def test_code_block_with_no_language_tag(self):
        """无语言标记的围栏代码块也不触发"""
        text = '```\nlist_files(".")\n```'
        assert Agent._detect_fake_tool_calls(text) is False

    def test_plain_text_fake_call_still_detected(self):
        """纯文本中的伪调用（无代码块包裹）仍应触发"""
        assert Agent._detect_fake_tool_calls("我来帮你执行 read_file(\"config.yaml\")") is True


class TestStripCodeBlocks:
    """测试 _strip_code_blocks 辅助方法"""

    def test_strips_fenced_code_block(self):
        text = "前文\n```python\ncode here\n```\n后文"
        result = Agent._strip_code_blocks(text)
        assert "code here" not in result
        assert "前文" in result
        assert "后文" in result

    def test_strips_inline_code(self):
        text = "使用 `read_file(path)` 来读取"
        result = Agent._strip_code_blocks(text)
        assert "read_file(path)" not in result
        assert "使用" in result
        assert "来读取" in result

    def test_strips_tilde_fence(self):
        text = "~~~\nsome_code()\n~~~"
        result = Agent._strip_code_blocks(text)
        assert "some_code()" not in result

    def test_preserves_plain_text(self):
        text = "这是一段没有代码的普通文本"
        result = Agent._strip_code_blocks(text)
        assert result == text

    def test_empty_string(self):
        assert Agent._strip_code_blocks("") == ""

    def test_multiple_code_blocks(self):
        text = "```\nblock1\n```\n中间文字\n```\nblock2\n```"
        result = Agent._strip_code_blocks(text)
        assert "block1" not in result
        assert "block2" not in result
        assert "中间文字" in result


class TestExecuteToolCall:
    """测试 _execute_tool_call 分发逻辑"""

    @pytest.fixture
    def agent(self):
        """创建一个 Agent 实例，mock 掉 OpenAI client"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            # 用 MagicMock 替换 tools，方便验证分发
            a.tools = MagicMock()
            return a

    def test_dispatch_read_file(self, agent):
        tc = ToolCallRequest(id="1", name="read_file", arguments={"path": "foo.txt"})
        agent._execute_tool_call(tc)
        agent.tools.read_file.assert_called_once_with("foo.txt")

    def test_dispatch_write_file(self, agent):
        tc = ToolCallRequest(id="2", name="write_file", arguments={"path": "a.txt", "content": "hi"})
        agent._execute_tool_call(tc)
        agent.tools.write_file.assert_called_once_with("a.txt", "hi")

    def test_dispatch_edit_file(self, agent):
        tc = ToolCallRequest(id="3", name="edit_file", arguments={"path": "f", "old_content": "a", "new_content": "b"})
        agent._execute_tool_call(tc)
        agent.tools.edit_file.assert_called_once_with("f", "a", "b")

    def test_dispatch_list_files(self, agent):
        tc = ToolCallRequest(id="4", name="list_files", arguments={"path": "/tmp"})
        agent._execute_tool_call(tc)
        agent.tools.list_files.assert_called_once_with("/tmp")

    def test_dispatch_list_files_default(self, agent):
        tc = ToolCallRequest(id="5", name="list_files", arguments={})
        agent._execute_tool_call(tc)
        agent.tools.list_files.assert_called_once_with(".")

    def test_dispatch_execute_command(self, agent):
        tc = ToolCallRequest(id="6", name="execute_command", arguments={"command": "ls", "cwd": "/tmp"})
        agent._execute_tool_call(tc)
        agent.tools.execute_command.assert_called_once_with("ls", "/tmp", None)

    def test_dispatch_execute_command_with_timeout(self, agent):
        tc = ToolCallRequest(id="6b", name="execute_command", arguments={"command": "sleep 60", "timeout": 300})
        agent._execute_tool_call(tc)
        agent.tools.execute_command.assert_called_once_with("sleep 60", None, 300)

    def test_dispatch_search_files(self, agent):
        tc = ToolCallRequest(id="7", name="search_files", arguments={"pattern": "*.py"})
        agent._execute_tool_call(tc)
        agent.tools.search_files.assert_called_once_with("*.py", ".")

    def test_dispatch_web_search(self, agent):
        tc = ToolCallRequest(id="7b", name="web_search", arguments={"query": "python tutorial"})
        agent._execute_tool_call(tc)
        agent.tools.web_search.assert_called_once_with("python tutorial", 5)

    def test_dispatch_web_search_with_max_results(self, agent):
        tc = ToolCallRequest(id="7c", name="web_search", arguments={"query": "rust lang", "max_results": 10})
        agent._execute_tool_call(tc)
        agent.tools.web_search.assert_called_once_with("rust lang", 10)

    def test_unknown_tool(self, agent):
        tc = ToolCallRequest(id="8", name="nonexistent_tool", arguments={})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    def test_missing_required_arg_read_file(self, agent):
        """read_file 缺少 path 参数时应返回友好错误而非崩溃"""
        tc = ToolCallRequest(id="9", name="read_file", arguments={})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]
        assert "'path'" in result["error"]

    def test_missing_required_arg_write_file(self, agent):
        """write_file 缺少 content 参数时应返回友好错误"""
        tc = ToolCallRequest(id="10", name="write_file", arguments={"path": "a.txt"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]
        assert "'content'" in result["error"]

    def test_missing_required_arg_edit_file(self, agent):
        """edit_file 缺少 old_content 参数时应返回友好错误"""
        tc = ToolCallRequest(id="11", name="edit_file", arguments={"path": "f", "new_content": "b"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_missing_required_arg_execute_command(self, agent):
        """execute_command 缺少 command 参数时应返回友好错误"""
        tc = ToolCallRequest(id="12", name="execute_command", arguments={})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_missing_required_arg_search_files(self, agent):
        """search_files 缺少 pattern 参数时应返回友好错误"""
        tc = ToolCallRequest(id="13", name="search_files", arguments={})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_missing_required_arg_web_search(self, agent):
        """web_search 缺少 query 参数时应返回友好错误"""
        tc = ToolCallRequest(id="13b", name="web_search", arguments={})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_empty_arguments(self, agent):
        """所有参数都缺失时应返回友好错误而非崩溃"""
        tc = ToolCallRequest(id="14", name="write_file", arguments={})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_none_arguments_returns_error(self, agent):
        """arguments 为 None 时（LLM 返回 null）应返回友好错误而非 TypeError 崩溃（#169）"""
        tc = ToolCallRequest(id="15", name="read_file", arguments=None)
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_list_arguments_returns_error(self, agent):
        """arguments 为 list 时（LLM 返回数组）应返回友好错误而非 TypeError 崩溃（#169）"""
        tc = ToolCallRequest(id="16", name="write_file", arguments=["path", "content"])
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_string_arguments_returns_error(self, agent):
        """arguments 为 string 时应返回友好错误而非 TypeError 崩溃（#169）"""
        tc = ToolCallRequest(id="17", name="execute_command", arguments="ls -la")
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]

    def test_int_arguments_returns_error(self, agent):
        """arguments 为 int 时应返回友好错误而非 TypeError 崩溃（#169）"""
        tc = ToolCallRequest(id="18", name="search_files", arguments=42)
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "Missing required argument" in result["error"]


class TestAgentInit:
    """测试 Agent 初始化"""

    def test_init_with_mock(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            assert a.model == "test-model"
            assert a.conversation_history == []
            assert a.system_prompt is not None
            assert len(a.system_prompt) > 0

    def test_clear_conversation(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a.conversation_history.append({"role": "user", "content": "hi"})
            a.clear_conversation()
            assert a.conversation_history == []

    def test_clear_conversation_resets_edit_fail_counts(self):
        """clear_conversation 应清理 _edit_fail_counts，避免状态泄露到新对话"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a._edit_fail_counts = {"test.py": 3, "main.py": 1}
            a.clear_conversation()
            assert a._edit_fail_counts == {}

    def test_clear_conversation_resets_last_prompt_tokens(self):
        """clear_conversation 应重置 _last_prompt_tokens"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a._last_prompt_tokens = 5000
            a.clear_conversation()
            assert a._last_prompt_tokens == 0

    def test_clear_conversation_resets_working_summary(self):
        """clear_conversation 应重置 working_summary"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a.memory.working_summary.intent = "old goal"
            a.memory.working_summary.changes = "old changes"
            a.clear_conversation()
            assert a.memory.working_summary.is_empty()

    def test_clear_conversation_resets_router_stats(self):
        """clear_conversation 应重置 router.stats，避免旧对话统计泄漏"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            from src.router import TaskComplexity
            a.router.stats[TaskComplexity.LOW] = 10
            a.router.stats[TaskComplexity.HIGH] = 5
            a.clear_conversation()
            assert all(v == 0 for v in a.router.stats.values())

    def test_import_session_resets_edit_fail_counts(self):
        """import_session 应清理 _edit_fail_counts，避免旧会话失败计数器泄露"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a._edit_fail_counts = {"old_file.py": 5}
            a.import_session({"conversation_history": []})
            assert a._edit_fail_counts == {}

    def test_import_session_resets_last_prompt_tokens(self):
        """import_session 应重置 _last_prompt_tokens"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a._last_prompt_tokens = 8000
            a.import_session({"conversation_history": []})
            assert a._last_prompt_tokens == 0

    def test_import_session_resets_router_stats(self):
        """import_session 应重置 router.stats，避免旧会话统计泄漏到新会话"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            from src.router import TaskComplexity
            a.router.stats[TaskComplexity.MIDDLE] = 20
            a.import_session({"conversation_history": []})
            assert all(v == 0 for v in a.router.stats.values())

    def test_init_declares_spec_prompt_and_replay_queue(self):
        """Agent.__init__ 应声明 _spec_prompt 和 _replay_queue 属性"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            assert a._spec_prompt is None
            assert a._replay_queue is None

    def test_clear_conversation_resets_spec_prompt_and_replay_queue(self):
        """clear_conversation 应重置 _spec_prompt 和 _replay_queue"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a._spec_prompt = "some spec prompt"
            a._replay_queue = ["input1", "input2"]
            a.clear_conversation()
            assert a._spec_prompt is None
            assert a._replay_queue is None

    def test_import_session_resets_spec_prompt_and_replay_queue(self):
        """import_session 应重置 _spec_prompt 和 _replay_queue"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            a._spec_prompt = "old spec"
            a._replay_queue = ["old input"]
            a.import_session({"conversation_history": []})
            assert a._spec_prompt is None
            assert a._replay_queue is None

    def test_import_session_resets_memory_when_no_memory_field(self):
        """#170: 旧版会话文件无 memory 字段时，应重置 working_summary 和 archival。"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            # 模拟已有 stale memory
            a.memory.working_summary = WorkingSummary(intent="stale goal")
            a.memory.add_archival("stale fact")
            # 加载旧版会话（无 memory 字段）
            a.import_session({"conversation_history": [{"role": "user", "content": "hi"}]})
            assert a.memory.working_summary.is_empty()
            assert len(a.memory.archival) == 0

    def test_with_model(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="model-a")
            a.with_model("model-b")
            assert a.model == "model-b"

    def test_default_max_tokens(self):
        """未指定 max_tokens 时使用 DEFAULT_MAX_TOKENS。"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            assert a.max_tokens == Agent.DEFAULT_MAX_TOKENS
            assert a.max_tokens == 20480

    def test_custom_max_tokens(self):
        """显式指定 max_tokens。"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", max_tokens=8192)
            assert a.max_tokens == 8192

    def test_none_max_tokens_uses_default(self):
        """max_tokens=None 时使用默认值。"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", max_tokens=None)
            assert a.max_tokens == Agent.DEFAULT_MAX_TOKENS


class TestAPIErrorHandling:
    """测试 API 调用的错误分类处理"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            return a

    @staticmethod
    async def _collect_events(agent, user_input="hello"):
        events = []
        async for event in agent.prompt_stream(user_input):
            events.append(event)
        return events

    @pytest.mark.asyncio
    async def test_authentication_error(self, agent):
        from openai import AuthenticationError
        from unittest.mock import PropertyMock
        mock_response = MagicMock()
        type(mock_response).status_code = PropertyMock(return_value=401)
        type(mock_response).headers = PropertyMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
        agent.client.chat.completions.create.side_effect = AuthenticationError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "认证失败" in error_events[0]["message"]
        assert "OPENAI_API_KEY" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, agent):
        from openai import RateLimitError
        mock_response = MagicMock()
        type(mock_response).status_code = MagicMock(return_value=429)
        type(mock_response).headers = MagicMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}
        agent.client.chat.completions.create.side_effect = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "速率限制" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_api_connection_error(self, agent):
        from openai import APIConnectionError
        agent.client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock(),
        )
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "连接失败" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_api_timeout_error(self, agent):
        from openai import APITimeoutError
        agent.client.chat.completions.create.side_effect = APITimeoutError(
            request=MagicMock(),
        )
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "超时" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_bad_request_context_length(self, agent):
        from openai import BadRequestError
        mock_response = MagicMock()
        type(mock_response).status_code = MagicMock(return_value=400)
        type(mock_response).headers = MagicMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "context_length_exceeded"}}
        agent.client.chat.completions.create.side_effect = BadRequestError(
            message="This model's maximum context_length is 8192 tokens",
            response=mock_response,
            body={"error": {"message": "context_length_exceeded"}},
        )
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "上下文过长" in error_events[0]["message"]
        assert "/clear" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_bad_request_generic(self, agent):
        from openai import BadRequestError
        mock_response = MagicMock()
        type(mock_response).status_code = MagicMock(return_value=400)
        type(mock_response).headers = MagicMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "Invalid param"}}
        agent.client.chat.completions.create.side_effect = BadRequestError(
            message="Invalid param",
            response=mock_response,
            body={"error": {"message": "Invalid param"}},
        )
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "参数错误" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_unknown_exception_fallback(self, agent):
        agent.client.chat.completions.create.side_effect = RuntimeError("something unexpected")
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "未知错误" in error_events[0]["message"]
        assert "something unexpected" in error_events[0]["message"]


class TestKeyboardInterruptHandling:
    """测试 Ctrl+C (KeyboardInterrupt) 优雅处理"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            a.tools = MagicMock()
            return a

    @staticmethod
    async def _collect_events(agent, user_input="hello"):
        events = []
        async for event in agent.prompt_stream(user_input):
            events.append(event)
        return events

    @pytest.mark.asyncio
    async def test_interrupt_during_api_call(self, agent):
        """API 请求过程中按 Ctrl+C 应返回 interrupted 事件"""
        agent.client.chat.completions.create.side_effect = KeyboardInterrupt()
        events = await self._collect_events(agent)
        interrupted_events = [e for e in events if e["type"] == "interrupted"]
        assert len(interrupted_events) == 1
        assert "中断" in interrupted_events[0]["message"]

    @pytest.mark.asyncio
    async def test_interrupt_during_api_call_preserves_user_message(self, agent):
        """API 请求中断后，用户消息应已追加到对话历史"""
        agent.client.chat.completions.create.side_effect = KeyboardInterrupt()
        await self._collect_events(agent, "test input")
        # 用户消息已追加（在 API 调用之前）
        assert len(agent.conversation_history) == 1
        assert agent.conversation_history[0]["role"] == "user"
        assert agent.conversation_history[0]["content"] == "test input"

    @pytest.mark.asyncio
    async def test_interrupt_during_tool_execution(self, agent):
        """工具执行过程中按 Ctrl+C 应返回 interrupted 事件"""
        # 模拟 LLM 返回一个工具调用
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [MagicMock()]
        mock_message.tool_calls[0].id = "call_1"
        mock_message.tool_calls[0].function.name = "execute_command"
        mock_message.tool_calls[0].function.arguments = '{"command": "sleep 100"}'
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        agent.client.chat.completions.create.return_value = _response_to_chunks(mock_response)
        # 工具执行时抛出 KeyboardInterrupt
        agent.tools.execute_command.side_effect = KeyboardInterrupt()

        events = await self._collect_events(agent)
        
        # 应该有 tool_start 和 interrupted 事件
        tool_start_events = [e for e in events if e["type"] == "tool_start"]
        assert len(tool_start_events) == 1
        assert tool_start_events[0]["tool_name"] == "execute_command"
        
        interrupted_events = [e for e in events if e["type"] == "interrupted"]
        assert len(interrupted_events) == 1
        assert "execute_command" in interrupted_events[0]["message"]

    @pytest.mark.asyncio
    async def test_interrupt_during_tool_cleans_history(self, agent):
        """工具执行中断后，应清理不完整的 assistant 消息"""
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [MagicMock()]
        mock_message.tool_calls[0].id = "call_1"
        mock_message.tool_calls[0].function.name = "read_file"
        mock_message.tool_calls[0].function.arguments = '{"path": "test.txt"}'
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        agent.client.chat.completions.create.return_value = _response_to_chunks(mock_response)
        agent.tools.read_file.side_effect = KeyboardInterrupt()

        await self._collect_events(agent, "read test.txt")
        
        # 对话历史应只有用户消息，不含不完整的 assistant 消息
        assert len(agent.conversation_history) == 1
        assert agent.conversation_history[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_interrupt_no_error_event(self, agent):
        """中断应产生 interrupted 事件而非 error 事件"""
        agent.client.chat.completions.create.side_effect = KeyboardInterrupt()
        events = await self._collect_events(agent)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 0
        interrupted_events = [e for e in events if e["type"] == "interrupted"]
        assert len(interrupted_events) == 1

    @pytest.mark.asyncio
    async def test_interrupt_second_tool_cleans_entire_group(self, agent):
        """多工具调用中，第 2 个工具中断时应清理整个 tool_calls 组（assistant + 已完成的 tool 消息）"""
        # 模拟 LLM 返回 2 个工具调用
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = None
        mock_tc1 = MagicMock()
        mock_tc1.id = "call_1"
        mock_tc1.function.name = "read_file"
        mock_tc1.function.arguments = '{"path": "a.txt"}'
        mock_tc2 = MagicMock()
        mock_tc2.id = "call_2"
        mock_tc2.function.name = "read_file"
        mock_tc2.function.arguments = '{"path": "b.txt"}'
        mock_message.tool_calls = [mock_tc1, mock_tc2]
        mock_choice.message = mock_message
        mock_choice.finish_reason = "tool_calls"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        agent.client.chat.completions.create.return_value = _response_to_chunks(mock_response)
        call_count = {"n": 0}
        def read_side_effect(path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"success": True, "content": "aaa", "path": path}
            raise KeyboardInterrupt()
        agent.tools.read_file.side_effect = read_side_effect

        events = await self._collect_events(agent, "read both files")

        # 应有 interrupted 事件
        interrupted_events = [e for e in events if e["type"] == "interrupted"]
        assert len(interrupted_events) == 1

        # 关键断言：对话历史不应残留不完整的 tool_calls 组
        # 应该只有 user 消息，不含 assistant(tool_calls) 或 tool 消息
        assert len(agent.conversation_history) == 1
        assert agent.conversation_history[0]["role"] == "user"


class TestTrimHistory:
    """测试对话历史截断机制"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model", max_history=10)
            return a

    def test_no_trim_when_under_limit(self, agent):
        """历史未超限时不截断"""
        for i in range(5):
            agent.conversation_history.append({"role": "user", "content": f"msg {i}"})
        removed = agent._trim_history()
        assert removed == 0
        assert len(agent.conversation_history) == 5

    def test_no_trim_at_exact_limit(self, agent):
        """历史刚好等于上限时不截断"""
        for i in range(10):
            agent.conversation_history.append({"role": "user", "content": f"msg {i}"})
        removed = agent._trim_history()
        assert removed == 0
        assert len(agent.conversation_history) == 10

    def test_trim_removes_oldest(self, agent):
        """超限时删除最早的消息，保留最新的"""
        for i in range(15):
            agent.conversation_history.append({"role": "user", "content": f"msg {i}"})
        removed = agent._trim_history()
        assert removed == 5
        assert len(agent.conversation_history) == 10
        # 最早的消息应该是 msg 5（前 5 条被删了）
        assert agent.conversation_history[0]["content"] == "msg 5"
        # 最新的消息应该是 msg 14
        assert agent.conversation_history[-1]["content"] == "msg 14"

    def test_trim_does_not_split_tool_group(self, agent):
        """截断时不能拆开 assistant(tool_calls) + tool 消息组"""
        # 构造历史：[user, assistant(tool_calls), tool, tool, user, ...更多消息]
        agent.conversation_history = [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}, {"id": "c2"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "result1"},
            {"role": "tool", "tool_call_id": "c2", "content": "result2"},
            {"role": "user", "content": "follow up"},
        ]
        # 再追加足够多的消息让总量超限（max_history=10）
        for i in range(8):
            agent.conversation_history.append({"role": "user", "content": f"new msg {i}"})
        # 总共 13 条，需要截掉 3 条
        # 截断点 cut=3，但 history[3] 是 tool 消息，需要跳过
        removed = agent._trim_history()
        # 应该跳过 tool 消息，cut 移到第 4 条（index 4, role=user）
        assert removed == 4
        assert len(agent.conversation_history) == 9
        # 第一条应该是 "follow up"（不是 tool 消息）
        assert agent.conversation_history[0]["role"] == "user"
        assert agent.conversation_history[0]["content"] == "follow up"

    def test_trim_skips_multiple_tool_messages(self, agent):
        """截断点落在连续多个 tool 消息中间时，全部跳过"""
        # max_history=10
        agent.conversation_history = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "tool", "tool_call_id": "c2", "content": "r2"},
            {"role": "tool", "tool_call_id": "c3", "content": "r3"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "q2"},
        ]
        # 追加 5 条凑到 12 条
        for i in range(5):
            agent.conversation_history.append({"role": "assistant", "content": f"a{i}"})
        # 12 条，需要截掉 2 条。cut=2，history[2] 是 tool，继续跳
        removed = agent._trim_history()
        # 应该跳过所有 tool 到 index 5（assistant "answer"）
        assert removed == 5
        assert agent.conversation_history[0]["role"] == "assistant"
        assert agent.conversation_history[0]["content"] == "answer"

    def test_trim_default_max_history(self):
        """默认 max_history 应为 DEFAULT_MAX_HISTORY"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            assert a.max_history == Agent.DEFAULT_MAX_HISTORY
            assert a.max_history == 100

    @pytest.mark.asyncio
    async def test_trim_yields_warning_event(self):
        """截断时应 yield warning 事件"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model", max_history=5)
            # 填入 5 条历史（刚好满）
            for i in range(5):
                agent.conversation_history.append({"role": "user", "content": f"old {i}"})
            # 下一次 prompt 会追加第 6 条，触发截断
            agent.client.chat.completions.create.side_effect = KeyboardInterrupt()
            events = []
            async for event in agent.prompt_stream("new message"):
                events.append(event)
            warning_events = [e for e in events if e["type"] == "warning"]
            assert len(warning_events) == 1
            assert "丢弃" in warning_events[0]["message"]

    def test_trim_all_tool_messages_does_not_clear_history(self):
        """当 cut 处及之后全部是 tool 消息时，不应清空历史（#166）"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model", max_history=3)
            a.conversation_history = [
                {"role": "tool", "tool_call_id": "1", "content": "r1"},
                {"role": "tool", "tool_call_id": "2", "content": "r2"},
                {"role": "tool", "tool_call_id": "3", "content": "r3"},
                {"role": "tool", "tool_call_id": "4", "content": "r4"},
                {"role": "tool", "tool_call_id": "5", "content": "r5"},
            ]
            removed = a._trim_history()
            assert removed == 0, "无安全截断点时应返回 0"
            assert len(a.conversation_history) == 5, "所有消息应保留"

    def test_trim_tool_at_cut_then_end_does_not_clear(self):
        """cut 处是 tool，跳过后到达末尾，不应截断（#166）"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model", max_history=2)
            a.conversation_history = [
                {"role": "user", "content": "q1"},
                {"role": "tool", "tool_call_id": "1", "content": "r1"},
                {"role": "tool", "tool_call_id": "2", "content": "r2"},
                {"role": "tool", "tool_call_id": "3", "content": "r3"},
            ]
            removed = a._trim_history()
            # cut=2, history[2] 是 tool, 跳到 cut=4 == len(history), 应返回 0
            assert removed == 0
            assert len(a.conversation_history) == 4


class TestUndoRecording:
    """测试 Agent._execute_tool_call 自动记录 undo"""

    @pytest.fixture
    def agent(self, tmp_path):
        """创建一个使用真实 ToolExecutor 的 Agent（mock OpenAI client）"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            # 使用真实 ToolExecutor（不 mock），这样可以测试完整的 undo 流程
            return a

    def test_write_file_records_undo(self, agent, tmp_path):
        """write_file 成功后应自动记录 undo，且 old_content 不暴露在返回结果中"""
        f = tmp_path / "undo_test.txt"
        f.write_text("original", encoding="utf-8")
        tc = ToolCallRequest(id="1", name="write_file",
                             arguments={"path": str(f), "content": "modified"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is True
        # old_content 不应暴露给 LLM
        assert "old_content" not in result
        assert f.read_text(encoding="utf-8") == "modified"
        # undo 应恢复
        undo_result = agent.tools.undo()
        assert undo_result["success"] is True
        assert f.read_text(encoding="utf-8") == "original"

    def test_edit_file_records_undo(self, agent, tmp_path):
        """edit_file 成功后应自动记录 undo"""
        f = tmp_path / "edit_undo.txt"
        f.write_text("hello world", encoding="utf-8")
        tc = ToolCallRequest(id="2", name="edit_file",
                             arguments={"path": str(f), "old_content": "world", "new_content": "earth"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "hello earth"
        undo_result = agent.tools.undo()
        assert undo_result["success"] is True
        assert f.read_text(encoding="utf-8") == "hello world"

    def test_write_new_file_records_undo_none(self, agent, tmp_path):
        """write_file 创建新文件时，undo 应删除该文件"""
        import os
        target = str(tmp_path / "new_file.txt")
        tc = ToolCallRequest(id="3", name="write_file",
                             arguments={"path": target, "content": "new"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is True
        assert os.path.isfile(target)
        undo_result = agent.tools.undo()
        assert undo_result["success"] is True
        assert not os.path.isfile(target)

    def test_failed_write_does_not_record_undo(self, agent):
        """write_file 失败时不应记录 undo"""
        # 写入一个不存在的目录中的文件（路径中包含空字节会导致失败）
        tc = ToolCallRequest(id="4", name="write_file",
                             arguments={"path": "/nonexistent\x00dir/file.txt", "content": "x"})
        agent._execute_tool_call(tc)
        # undo 栈应为空
        result = agent.tools.undo()
        assert result["success"] is False

    def test_failed_edit_does_not_record_undo(self, agent, tmp_path):
        """edit_file 失败时（old_content 未找到）不应记录 undo"""
        f = tmp_path / "no_match.txt"
        f.write_text("hello", encoding="utf-8")
        tc = ToolCallRequest(id="5", name="edit_file",
                             arguments={"path": str(f), "old_content": "missing", "new_content": "new"})
        agent._execute_tool_call(tc)
        result = agent.tools.undo()
        assert result["success"] is False

    def test_read_file_does_not_record_undo(self, agent, tmp_path):
        """read_file 不应记录 undo"""
        f = tmp_path / "read_only.txt"
        f.write_text("content", encoding="utf-8")
        tc = ToolCallRequest(id="6", name="read_file",
                             arguments={"path": str(f)})
        agent._execute_tool_call(tc)
        result = agent.tools.undo()
        assert result["success"] is False

    def test_edit_file_undo_uses_old_content_from_result(self, agent, tmp_path):
        """edit_file 成功时，agent 从返回结果的 old_content_full 记录 undo，
        而不是单独读取文件。验证 undo 能正确恢复原始内容。"""
        f = tmp_path / "edit_undo.txt"
        f.write_text("hello world", encoding="utf-8")
        path_str = str(f)

        tc = ToolCallRequest(id="7", name="edit_file",
                             arguments={"path": path_str, "old_content": "hello", "new_content": "HELLO"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is True
        # old_content_full 不应暴露给 LLM（已被 pop）
        assert "old_content_full" not in result
        assert f.read_text(encoding="utf-8") == "HELLO world"
        # undo 应恢复原始内容
        undo_result = agent.tools.undo()
        assert undo_result["success"] is True
        assert f.read_text(encoding="utf-8") == "hello world"


class TestContextManagement:
    """测试上下文 token 管理：警告和自动 compaction"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model", max_context_tokens=1000)
            return a

    # --- 常量和初始化 ---

    def test_default_max_context_tokens(self):
        """默认 max_context_tokens 应为 DEFAULT_MAX_CONTEXT_TOKENS"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key")
            assert a.max_context_tokens == Agent.DEFAULT_MAX_CONTEXT_TOKENS

    def test_custom_max_context_tokens(self):
        """可自定义 max_context_tokens"""
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", max_context_tokens=8192)
            assert a.max_context_tokens == 8192

    def test_context_ratios_exist(self):
        """警告和自动 compaction 的阈值常量应存在且合理"""
        assert hasattr(Agent, "CONTEXT_WARNING_RATIO")
        assert hasattr(Agent, "CONTEXT_AUTO_COMPACT_RATIO")
        assert 0 < Agent.CONTEXT_WARNING_RATIO < Agent.CONTEXT_AUTO_COMPACT_RATIO <= 1.0

    def test_last_prompt_tokens_init_zero(self, agent):
        """初始化时 _last_prompt_tokens 应为 0"""
        assert agent._last_prompt_tokens == 0

    # --- _check_context_usage ---

    def test_check_context_ok(self, agent):
        """低于警告阈值时返回 'ok'"""
        agent._last_prompt_tokens = 100  # 10% of 1000
        status = agent._check_context_usage()
        assert status == "ok"

    def test_check_context_warning(self, agent):
        """达到警告阈值但未达自动 compaction 时返回 'warning'"""
        agent._last_prompt_tokens = int(1000 * Agent.CONTEXT_WARNING_RATIO) + 1
        status = agent._check_context_usage()
        assert status == "warning"

    def test_check_context_critical(self, agent):
        """达到自动 compaction 阈值时返回 'critical'"""
        agent._last_prompt_tokens = int(1000 * Agent.CONTEXT_AUTO_COMPACT_RATIO) + 1
        status = agent._check_context_usage()
        assert status == "critical"

    def test_check_context_zero_tokens(self, agent):
        """prompt_tokens 为 0 时返回 'ok'"""
        agent._last_prompt_tokens = 0
        assert agent._check_context_usage() == "ok"

    def test_check_context_exactly_at_warning(self, agent):
        """刚好等于警告阈值（80%）应返回 'warning'"""
        agent._last_prompt_tokens = int(1000 * Agent.CONTEXT_WARNING_RATIO)
        status = agent._check_context_usage()
        assert status == "warning"

    def test_check_context_exactly_at_critical(self, agent):
        """刚好等于 compaction 阈值（90%）应返回 'critical'"""
        agent._last_prompt_tokens = int(1000 * Agent.CONTEXT_AUTO_COMPACT_RATIO)
        status = agent._check_context_usage()
        assert status == "critical"

    # --- _context_pct ---

    def test_context_pct_normal(self, agent):
        """正常情况下返回百分比整数"""
        agent._last_prompt_tokens = 500
        agent.max_context_tokens = 1000
        assert agent._context_pct() == 50

    def test_context_pct_zero_max(self, agent):
        """max_context_tokens 为 0 时返回 0"""
        agent._last_prompt_tokens = 500
        agent.max_context_tokens = 0
        assert agent._context_pct() == 0

    def test_context_pct_over_100(self, agent):
        """超出上限时返回 > 100"""
        agent._last_prompt_tokens = 1500
        agent.max_context_tokens = 1000
        assert agent._context_pct() == 150

    # --- _context_warning_message ---

    def test_context_warning_message_format(self, agent):
        """验证格式包含 pct、token 数和 suffix"""
        agent._last_prompt_tokens = 800
        agent.max_context_tokens = 1000
        msg = agent._context_warning_message("建议使用 /compact。")
        assert "80%" in msg
        assert "800" in msg
        assert "1000" in msg
        assert "建议使用 /compact。" in msg
        assert msg.startswith("⚠️")

    def test_context_warning_message_different_suffix(self, agent):
        """不同 suffix 正确拼接"""
        agent._last_prompt_tokens = 950
        agent.max_context_tokens = 1000
        msg = agent._context_warning_message("自动压缩失败。")
        assert "95%" in msg
        assert "自动压缩失败。" in msg

    # --- prompt_stream() 中的警告事件 ---

    @pytest.mark.asyncio
    async def test_prompt_emits_context_warning(self):
        """prompt_tokens 达到 80% 时应 yield context_warning 事件"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model", max_context_tokens=1000)
            # 模拟 LLM 返回：prompt_tokens 为 810（>80%）
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "hello"
            mock_message.tool_calls = None
            mock_choice.message = mock_message
            mock_choice.finish_reason = "stop"
            mock_response.choices = [mock_choice]
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 810
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 830
            agent.client.chat.completions.create.return_value = _response_to_chunks(mock_response)

            events = []
            async for event in agent.prompt_stream("test"):
                events.append(event)

            warning_events = [e for e in events if e["type"] == "context_warning"]
            assert len(warning_events) == 1
            assert "80%" in warning_events[0]["message"] or "上下文" in warning_events[0]["message"]

    @pytest.mark.asyncio
    async def test_prompt_no_warning_when_under_threshold(self):
        """prompt_tokens 低于 80% 时不应 yield context_warning"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model", max_context_tokens=1000)
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "hello"
            mock_message.tool_calls = None
            mock_choice.message = mock_message
            mock_choice.finish_reason = "stop"
            mock_response.choices = [mock_choice]
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 300  # 30%
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 320
            agent.client.chat.completions.create.return_value = _response_to_chunks(mock_response)

            events = []
            async for event in agent.prompt_stream("test"):
                events.append(event)

            warning_events = [e for e in events if e["type"] == "context_warning"]
            assert len(warning_events) == 0

    @pytest.mark.asyncio
    async def test_prompt_auto_compact_on_critical(self):
        """prompt_tokens 达到 90% 时应自动执行 compaction 并 yield auto_compact 事件"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model", max_context_tokens=1000)
            # 先填入足够多的对话历史（compact 要求 > MIN_MESSAGES_TO_COMPACT）
            for i in range(20):
                role = "user" if i % 2 == 0 else "assistant"
                agent.conversation_history.append({"role": role, "content": f"old msg {i}"})

            # 第一次 API 调用：返回高 prompt_tokens 触发 auto compact
            mock_response_1 = MagicMock()
            mock_choice_1 = MagicMock()
            mock_message_1 = MagicMock()
            mock_message_1.content = "response text"
            mock_message_1.tool_calls = None
            mock_choice_1.message = mock_message_1
            mock_choice_1.finish_reason = "stop"
            mock_response_1.choices = [mock_choice_1]
            mock_response_1.usage = MagicMock()
            mock_response_1.usage.prompt_tokens = 920  # 92% → critical
            mock_response_1.usage.completion_tokens = 30
            mock_response_1.usage.total_tokens = 950

            # 第二次 API 调用：LLM 生成摘要
            mock_response_2 = MagicMock()
            mock_choice_2 = MagicMock()
            mock_message_2 = MagicMock()
            mock_message_2.content = "这是对话摘要。"
            mock_choice_2.message = mock_message_2
            mock_choice_2.finish_reason = "stop"
            mock_response_2.choices = [mock_choice_2]
            mock_response_2.usage = MagicMock()
            mock_response_2.usage.prompt_tokens = 100
            mock_response_2.usage.completion_tokens = 50
            mock_response_2.usage.total_tokens = 150

            agent.client.chat.completions.create.side_effect = [_response_to_chunks(mock_response_1), mock_response_2]

            events = []
            async for event in agent.prompt_stream("new question"):
                events.append(event)

            # 应有 auto_compact 事件
            compact_events = [e for e in events if e["type"] == "auto_compact"]
            assert len(compact_events) == 1
            assert compact_events[0]["removed"] > 0

            # 对话历史应已被压缩
            assert len(agent.conversation_history) < 22  # 20 old + 1 new question + 1 response

    @pytest.mark.asyncio
    async def test_prompt_auto_compact_skipped_if_too_short(self):
        """即使 prompt_tokens 很高，对话太短时不应自动 compact，而是降级为警告"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model", max_context_tokens=1000)
            # 只有 2 条历史（不够 compact）
            agent.conversation_history = [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ]

            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "response"
            mock_message.tool_calls = None
            mock_choice.message = mock_message
            mock_choice.finish_reason = "stop"
            mock_response.choices = [mock_choice]
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 950  # 95% → critical
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 970
            agent.client.chat.completions.create.return_value = _response_to_chunks(mock_response)

            events = []
            async for event in agent.prompt_stream("test"):
                events.append(event)

            # 不应有 auto_compact 事件（对话太短无法 compact）
            compact_events = [e for e in events if e["type"] == "auto_compact"]
            assert len(compact_events) == 0
            # 应有 context_warning 事件（降级为警告）
            warning_events = [e for e in events if e["type"] == "context_warning"]
            assert len(warning_events) == 1

    @pytest.mark.asyncio
    async def test_last_prompt_tokens_updated(self):
        """每次 API 调用后 _last_prompt_tokens 应更新"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model", max_context_tokens=1000)
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_message = MagicMock()
            mock_message.content = "hello"
            mock_message.tool_calls = None
            mock_choice.message = mock_message
            mock_choice.finish_reason = "stop"
            mock_response.choices = [mock_choice]
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 456
            mock_response.usage.completion_tokens = 20
            mock_response.usage.total_tokens = 476
            agent.client.chat.completions.create.return_value = _response_to_chunks(mock_response)

            async for _ in agent.prompt_stream("test"):
                pass

            assert agent._last_prompt_tokens == 456


class TestDangerousCommandDetection:
    """测试 _is_dangerous_command 静态方法"""

    # === 应检测到的危险命令 ===

    def test_rm_file(self):
        assert Agent._is_dangerous_command("rm file.txt") is not None

    def test_rm_rf(self):
        assert Agent._is_dangerous_command("rm -rf /tmp/data") is not None

    def test_rm_with_flags(self):
        assert Agent._is_dangerous_command("rm -f *.log") is not None

    def test_rmdir(self):
        assert Agent._is_dangerous_command("rmdir /tmp/empty") is not None

    def test_chmod(self):
        assert Agent._is_dangerous_command("chmod 777 /etc/passwd") is not None

    def test_chown(self):
        assert Agent._is_dangerous_command("chown root:root file") is not None

    def test_mkfs(self):
        assert Agent._is_dangerous_command("mkfs.ext4 /dev/sda1") is not None

    def test_dd(self):
        assert Agent._is_dangerous_command("dd if=/dev/zero of=/dev/sda") is not None

    def test_redirect_overwrite(self):
        assert Agent._is_dangerous_command("> important.txt") is not None

    def test_redirect_in_command(self):
        assert Agent._is_dangerous_command("echo '' > /etc/hosts") is not None

    def test_truncate_command(self):
        assert Agent._is_dangerous_command("truncate -s 0 data.db") is not None

    def test_mv_to_dev_null(self):
        assert Agent._is_dangerous_command("mv important.txt /dev/null") is not None

    def test_pipe_to_rm(self):
        assert Agent._is_dangerous_command("find . -name '*.tmp' | xargs rm") is not None

    def test_sudo_rm(self):
        assert Agent._is_dangerous_command("sudo rm -rf /") is not None

    # === 不应触发的安全命令 ===

    def test_ls_is_safe(self):
        assert Agent._is_dangerous_command("ls -la") is None

    def test_cat_is_safe(self):
        assert Agent._is_dangerous_command("cat file.txt") is None

    def test_grep_is_safe(self):
        assert Agent._is_dangerous_command("grep -r 'pattern' .") is None

    def test_python_is_safe(self):
        assert Agent._is_dangerous_command("python -m pytest") is None

    def test_git_status_is_safe(self):
        assert Agent._is_dangerous_command("git status") is None

    def test_echo_is_safe(self):
        """echo 不带重定向是安全的"""
        assert Agent._is_dangerous_command("echo hello world") is None

    def test_mkdir_is_safe(self):
        assert Agent._is_dangerous_command("mkdir -p /tmp/newdir") is None

    def test_pip_install_is_safe(self):
        assert Agent._is_dangerous_command("pip install requests") is None

    def test_wc_is_safe(self):
        assert Agent._is_dangerous_command("wc -l file.txt") is None

    def test_empty_command_is_safe(self):
        assert Agent._is_dangerous_command("") is None

    # === 返回值包含原因 ===

    def test_reason_contains_command_keyword(self):
        reason = Agent._is_dangerous_command("rm -rf /tmp")
        assert reason is not None
        assert isinstance(reason, str)
        assert len(reason) > 0

    # === 引号内的 > 不应误报（#104）===

    def test_python_c_comparison_is_safe(self):
        """python3 -c 中的 > 比较运算符不是重定向"""
        assert Agent._is_dangerous_command('python3 -c "x = 1; print(x > 0)"') is None

    def test_python_c_gt_in_single_quotes_is_safe(self):
        """单引号内的 > 不是重定向"""
        assert Agent._is_dangerous_command("python3 -c 'print(x > 0)'") is None

    def test_grep_with_gt_pattern_is_safe(self):
        """grep 模式中的 > 不是重定向"""
        assert Agent._is_dangerous_command('grep "x > 0" file.txt') is None

    def test_echo_quoted_gt_is_safe(self):
        """echo 引号内的 > 不是重定向"""
        assert Agent._is_dangerous_command('echo "a > b"') is None

    def test_real_redirect_still_detected(self):
        """真正的顶层重定向仍然被检测"""
        assert Agent._is_dangerous_command("echo hello > file.txt") is not None

    def test_real_redirect_after_pipe_still_detected(self):
        """管道后的真正重定向仍然被检测"""
        assert Agent._is_dangerous_command("sort data.txt > sorted.txt") is not None

    def test_bare_redirect_still_detected(self):
        """裸重定向仍然被检测"""
        assert Agent._is_dangerous_command("> file.txt") is not None

    def test_redirect_outside_quotes_detected(self):
        """引号外的重定向仍然被检测"""
        assert Agent._is_dangerous_command('echo "hello" > file.txt') is not None


class TestConfirmCallback:
    """测试 confirm_callback 权限确认机制"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            return a

    def test_confirm_callback_default_none(self, agent):
        """默认 confirm_callback 应为 None"""
        assert agent.confirm_callback is None

    def test_confirm_callback_settable(self, agent):
        """confirm_callback 应可设置"""
        agent.confirm_callback = lambda cmd, reason: True
        assert agent.confirm_callback is not None

    def test_dangerous_command_denied_without_callback(self, agent):
        """无 confirm_callback 时，危险命令应被拒绝"""
        agent.tools = MagicMock()
        tc = ToolCallRequest(id="1", name="execute_command",
                             arguments={"command": "rm -rf /tmp/data"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        assert "拒绝" in result["error"] or "危险" in result["error"]
        # execute_command 不应被调用
        agent.tools.execute_command.assert_not_called()

    def test_dangerous_command_allowed_with_callback_true(self, agent):
        """confirm_callback 返回 True 时，危险命令应执行"""
        agent.confirm_callback = lambda cmd, reason: True
        agent.tools = MagicMock()
        agent.tools.execute_command.return_value = {"success": True, "stdout": "", "stderr": ""}
        tc = ToolCallRequest(id="2", name="execute_command",
                             arguments={"command": "rm -rf /tmp/data"})
        result = agent._execute_tool_call(tc)
        agent.tools.execute_command.assert_called_once()

    def test_dangerous_command_denied_with_callback_false(self, agent):
        """confirm_callback 返回 False 时，危险命令应被拒绝"""
        agent.confirm_callback = lambda cmd, reason: False
        agent.tools = MagicMock()
        tc = ToolCallRequest(id="3", name="execute_command",
                             arguments={"command": "rm -rf /tmp/data"})
        result = agent._execute_tool_call(tc)
        assert result["success"] is False
        agent.tools.execute_command.assert_not_called()

    def test_safe_command_no_callback_needed(self, agent):
        """安全命令不需要确认，直接执行"""
        agent.confirm_callback = None
        agent.tools = MagicMock()
        agent.tools.execute_command.return_value = {"success": True, "stdout": "hello", "stderr": ""}
        tc = ToolCallRequest(id="4", name="execute_command",
                             arguments={"command": "echo hello"})
        result = agent._execute_tool_call(tc)
        agent.tools.execute_command.assert_called_once()

    def test_non_execute_command_unaffected(self, agent):
        """非 execute_command 工具不受权限系统影响"""
        agent.confirm_callback = None
        agent.tools = MagicMock()
        agent.tools.read_file.return_value = {"success": True, "content": "hi"}
        tc = ToolCallRequest(id="5", name="read_file",
                             arguments={"path": "test.txt"})
        result = agent._execute_tool_call(tc)
        agent.tools.read_file.assert_called_once()


class TestEnrichToolError:
    """测试 _enrich_tool_error 智能错误增强机制"""

    # === 成功结果不受影响 ===

    def test_success_result_unchanged(self):
        """成功结果不应被修改"""
        result = {"success": True, "content": "hello"}
        enriched = Agent._enrich_tool_error("read_file", result)
        assert enriched is result  # 同一对象，未修改
        assert "hint" not in enriched

    def test_success_result_no_hint(self):
        """成功的 write_file 不应添加 hint"""
        result = {"success": True, "path": "test.txt"}
        enriched = Agent._enrich_tool_error("write_file", result)
        assert "hint" not in enriched

    # === edit_file 错误增强 ===

    def test_edit_file_old_content_not_found(self):
        """edit_file 报 'Old content not found' 时应提示先 read_file"""
        result = {"success": False, "error": "Old content not found", "path": "test.py"}
        enriched = Agent._enrich_tool_error("edit_file", result)
        assert "hint" in enriched
        assert "read_file" in enriched["hint"]

    def test_edit_file_file_not_found(self):
        """edit_file 报文件不存在时应提示检查路径"""
        result = {"success": False, "error": "[Errno 2] No such file or directory: 'missing.py'", "path": "missing.py"}
        enriched = Agent._enrich_tool_error("edit_file", result)
        assert "hint" in enriched
        assert ("list_files" in enriched["hint"] or "search_files" in enriched["hint"])

    # === read_file 错误增强 ===

    def test_read_file_not_found(self):
        """read_file 文件不存在时应提示查找文件"""
        result = {"success": False, "error": "[Errno 2] No such file or directory: 'config.yaml'", "path": "config.yaml"}
        enriched = Agent._enrich_tool_error("read_file", result)
        assert "hint" in enriched
        assert ("list_files" in enriched["hint"] or "search_files" in enriched["hint"])

    def test_read_file_permission_denied(self):
        """read_file 权限不足时应提示"""
        result = {"success": False, "error": "[Errno 13] Permission denied: '/etc/shadow'", "path": "/etc/shadow"}
        enriched = Agent._enrich_tool_error("read_file", result)
        assert "hint" in enriched
        assert "权限" in enriched["hint"]

    def test_read_file_binary_file_hint(self):
        """read_file 二进制文件应提示使用 file/xxd 命令（#176）"""
        result = {"success": False, "error": "无法读取：test.bin 是二进制文件，不是 UTF-8 文本。请使用 execute_command 配合 file、xxd、hexdump 等命令查看。", "path": "test.bin"}
        enriched = Agent._enrich_tool_error("read_file", result)
        assert "hint" in enriched
        assert "二进制" in enriched["hint"]
        assert "file" in enriched["hint"] or "xxd" in enriched["hint"]

    def test_edit_file_binary_file_hint(self):
        """edit_file 二进制文件应提示无法使用 edit_file（#176）"""
        result = {"success": False, "error": "无法编辑：test.bin 是二进制文件，不是 UTF-8 文本。edit_file 仅支持文本文件。", "path": "test.bin"}
        enriched = Agent._enrich_tool_error("edit_file", result)
        assert "hint" in enriched
        assert "二进制" in enriched["hint"]

    # === execute_command 错误增强 ===

    def test_execute_command_timeout(self):
        """execute_command 超时应提示增大 timeout"""
        result = {"success": False, "error": "Command timed out after 120s", "command": "make build"}
        enriched = Agent._enrich_tool_error("execute_command", result)
        assert "hint" in enriched
        assert "timeout" in enriched["hint"]

    def test_execute_command_not_found(self):
        """命令不存在时应提示检查安装"""
        result = {"success": False, "returncode": 127, "stdout": "", "stderr": "bash: cargo: command not found", "command": "cargo build"}
        enriched = Agent._enrich_tool_error("execute_command", result)
        assert "hint" in enriched
        assert ("not found" in enriched["hint"] or "安装" in enriched["hint"] or "未安装" in enriched["hint"])

    def test_execute_command_nonzero_exit(self):
        """命令返回非零退出码时应提示查看 stderr"""
        result = {"success": False, "returncode": 1, "stdout": "", "stderr": "error: something failed", "command": "python test.py"}
        enriched = Agent._enrich_tool_error("execute_command", result)
        assert "hint" in enriched

    # === write_file 错误增强 ===

    def test_write_file_permission_denied(self):
        """write_file 权限不足时应提示"""
        result = {"success": False, "error": "[Errno 13] Permission denied: '/etc/config'", "path": "/etc/config"}
        enriched = Agent._enrich_tool_error("write_file", result)
        assert "hint" in enriched
        assert "权限" in enriched["hint"]

    # === 未知工具的失败不添加 hint（除非有通用模式）===

    def test_unknown_tool_error_gets_generic_hint(self):
        """未知工具的失败应返回通用 hint"""
        result = {"success": False, "error": "Unknown tool: foo_tool"}
        enriched = Agent._enrich_tool_error("foo_tool", result)
        # 未知工具也应有基本提示
        assert "hint" in enriched

    # === 边界情况 ===

    def test_no_error_field_in_failed_result(self):
        """success=False 但没有 error 字段时不应崩溃"""
        result = {"success": False}
        enriched = Agent._enrich_tool_error("read_file", result)
        assert enriched["success"] is False
        # 应有某种 hint 或不崩溃
        assert "hint" in enriched

    def test_search_files_no_matches(self):
        """search_files 成功但没有匹配时不算错误"""
        result = {"success": True, "matches": [], "pattern": "*.xyz"}
        enriched = Agent._enrich_tool_error("search_files", result)
        assert "hint" not in enriched

    def test_enriched_result_preserves_original_fields(self):
        """添加 hint 后不应丢失原始字段"""
        result = {"success": False, "error": "Old content not found", "path": "test.py"}
        enriched = Agent._enrich_tool_error("edit_file", result)
        assert enriched["error"] == "Old content not found"
        assert enriched["path"] == "test.py"
        assert enriched["success"] is False

    def test_enrich_does_not_mutate_original_result(self):
        """_enrich_tool_error 不应修改传入的原始 result 字典（无副作用）"""
        result = {"success": False, "error": "Old content not found", "path": "test.py"}
        original_keys = set(result.keys())
        enriched = Agent._enrich_tool_error("edit_file", result)
        # 原始 result 不应被添加 hint 字段
        assert "hint" not in result
        assert set(result.keys()) == original_keys
        # 返回的 enriched 应是不同的对象
        assert enriched is not result
        # enriched 应有 hint
        assert "hint" in enriched


class TestEditFailRecovery:
    """测试 edit_file 连续失败时的错误恢复机制（升级建议 write_file 替代）"""

    def test_edit_fail_counts_initialized_empty(self):
        """Agent 初始化时 edit_fail_counts 应为空字典"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            assert agent._edit_fail_counts == {}

    def test_edit_fail_count_increments_on_failure(self):
        """edit_file 失败时对应文件路径的计数应递增"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            agent.tools.edit_file.return_value = {
                "success": False, "error": "Old content not found", "path": "test.py"
            }
            tc = ToolCallRequest(id="c1", name="edit_file",
                                 arguments={"path": "test.py", "old_content": "old", "new_content": "new"})
            agent._execute_tool_call(tc)
            assert agent._edit_fail_counts.get("test.py") == 1
            # 第二次失败
            agent._execute_tool_call(tc)
            assert agent._edit_fail_counts.get("test.py") == 2

    def test_edit_fail_count_resets_on_success(self):
        """edit_file 成功后对应文件路径的计数应清零"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            # 先失败
            agent.tools.edit_file.return_value = {
                "success": False, "error": "Old content not found", "path": "test.py"
            }
            tc = ToolCallRequest(id="c1", name="edit_file",
                                 arguments={"path": "test.py", "old_content": "old", "new_content": "new"})
            agent._execute_tool_call(tc)
            assert agent._edit_fail_counts.get("test.py") == 1
            # 再成功
            agent.tools.edit_file.return_value = {
                "success": True, "path": "test.py"
            }
            agent._execute_tool_call(tc)
            assert agent._edit_fail_counts.get("test.py", 0) == 0

    def test_edit_fail_count_per_file(self):
        """不同文件的失败计数应独立"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            agent.tools.edit_file.return_value = {
                "success": False, "error": "Old content not found", "path": "a.py"
            }
            tc_a = ToolCallRequest(id="c1", name="edit_file",
                                   arguments={"path": "a.py", "old_content": "x", "new_content": "y"})
            agent._execute_tool_call(tc_a)
            agent._execute_tool_call(tc_a)
            tc_b = ToolCallRequest(id="c2", name="edit_file",
                                   arguments={"path": "b.py", "old_content": "x", "new_content": "y"})
            agent.tools.edit_file.return_value = {
                "success": False, "error": "Old content not found", "path": "b.py"
            }
            agent._execute_tool_call(tc_b)
            assert agent._edit_fail_counts.get("a.py") == 2
            assert agent._edit_fail_counts.get("b.py") == 1

    def test_enrich_first_failure_suggests_read_file(self):
        """首次失败（fail_count=1）应建议 read_file"""
        result = {"success": False, "error": "Old content not found", "path": "test.py"}
        enriched = Agent._enrich_tool_error("edit_file", result, fail_count=1)
        assert "hint" in enriched
        assert "read_file" in enriched["hint"]
        # 首次失败不应该建议 write_file
        assert "write_file" not in enriched["hint"]

    def test_enrich_repeated_failure_suggests_write_file(self):
        """连续 2+ 次失败同一文件应升级建议 write_file"""
        result = {"success": False, "error": "Old content not found", "path": "test.py"}
        enriched = Agent._enrich_tool_error("edit_file", result, fail_count=2)
        assert "hint" in enriched
        assert "write_file" in enriched["hint"]

    def test_enrich_repeated_failure_still_mentions_read_file(self):
        """连续失败的升级建议应同时包含 read_file 和 write_file"""
        result = {"success": False, "error": "Old content not found", "path": "test.py"}
        enriched = Agent._enrich_tool_error("edit_file", result, fail_count=3)
        assert "read_file" in enriched["hint"]
        assert "write_file" in enriched["hint"]

    def test_enrich_zero_fail_count_same_as_default(self):
        """fail_count=0（默认）应与无参数调用行为一致"""
        result = {"success": False, "error": "Old content not found", "path": "test.py"}
        enriched_default = Agent._enrich_tool_error("edit_file", result)
        enriched_zero = Agent._enrich_tool_error("edit_file", result, fail_count=0)
        assert enriched_default["hint"] == enriched_zero["hint"]

    def test_enrich_non_edit_file_ignores_fail_count(self):
        """非 edit_file 工具不受 fail_count 影响"""
        result = {"success": False, "error": "[Errno 2] No such file or directory: 'missing.txt'", "path": "missing.txt"}
        enriched = Agent._enrich_tool_error("read_file", result, fail_count=5)
        # read_file 的 hint 不应包含 write_file 建议
        assert "write_file" not in enriched["hint"]

    def test_write_file_success_does_not_affect_edit_counts(self):
        """write_file 成功不应影响 edit_fail_counts"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            # 先让 edit_file 失败
            agent.tools.edit_file.return_value = {
                "success": False, "error": "Old content not found", "path": "test.py"
            }
            tc_edit = ToolCallRequest(id="c1", name="edit_file",
                                      arguments={"path": "test.py", "old_content": "x", "new_content": "y"})
            agent._execute_tool_call(tc_edit)
            assert agent._edit_fail_counts.get("test.py") == 1
            # write_file 成功不应重置 edit 计数
            agent.tools.write_file.return_value = {"success": True, "path": "test.py"}
            tc_write = ToolCallRequest(id="c2", name="write_file",
                                       arguments={"path": "test.py", "content": "new content"})
            agent._execute_tool_call(tc_write)
            # edit_fail_counts 不受 write_file 影响
            assert agent._edit_fail_counts.get("test.py") == 1


class TestEnrichToolErrorIntegration:
    """测试智能错误增强在 prompt_stream() 工具循环中的集成"""

    @staticmethod
    async def _collect_events(agent, user_input="hello"):
        events = []
        async for event in agent.prompt_stream(user_input):
            events.append(event)
        return events

    @pytest.mark.asyncio
    async def test_hint_in_tool_message_to_llm(self):
        """工具失败时，发送给 LLM 的 tool 消息应包含 hint"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            agent.tools.read_file.return_value = {
                "success": False,
                "error": "[Errno 2] No such file or directory: 'missing.txt'",
                "path": "missing.txt",
            }

            # 第一次 API 调用：返回 read_file 工具调用
            mock_response_1 = MagicMock()
            mock_choice_1 = MagicMock()
            mock_message_1 = MagicMock()
            mock_message_1.content = None
            mock_tc = MagicMock()
            mock_tc.id = "call_1"
            mock_tc.function.name = "read_file"
            mock_tc.function.arguments = '{"path": "missing.txt"}'
            mock_message_1.tool_calls = [mock_tc]
            mock_choice_1.message = mock_message_1
            mock_choice_1.finish_reason = "tool_calls"
            mock_response_1.choices = [mock_choice_1]
            mock_response_1.usage = MagicMock()
            mock_response_1.usage.prompt_tokens = 100
            mock_response_1.usage.completion_tokens = 20
            mock_response_1.usage.total_tokens = 120

            # 第二次 API 调用：LLM 看到错误后正常回复
            mock_response_2 = MagicMock()
            mock_choice_2 = MagicMock()
            mock_message_2 = MagicMock()
            mock_message_2.content = "文件不存在，让我查找一下。"
            mock_message_2.tool_calls = None
            mock_choice_2.message = mock_message_2
            mock_choice_2.finish_reason = "stop"
            mock_response_2.choices = [mock_choice_2]
            mock_response_2.usage = MagicMock()
            mock_response_2.usage.prompt_tokens = 150
            mock_response_2.usage.completion_tokens = 30
            mock_response_2.usage.total_tokens = 180

            agent.client.chat.completions.create.side_effect = [_response_to_chunks(mock_response_1), _response_to_chunks(mock_response_2)]

            events = await self._collect_events(agent, "read missing.txt")

            # 检查对话历史中的 tool 消息是否包含 hint
            tool_messages = [m for m in agent.conversation_history if m.get("role") == "tool"]
            assert len(tool_messages) >= 1
            import json
            tool_content = json.loads(tool_messages[0]["content"])
            assert "hint" in tool_content
            assert "list_files" in tool_content["hint"] or "search_files" in tool_content["hint"]

    @pytest.mark.asyncio
    async def test_success_result_no_hint_in_message(self):
        """工具成功时，发送给 LLM 的 tool 消息不应包含 hint"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            agent.tools.read_file.return_value = {
                "success": True,
                "content": "file content here",
                "path": "test.txt",
            }

            # 第一次 API 调用：返回 read_file 工具调用
            mock_response_1 = MagicMock()
            mock_choice_1 = MagicMock()
            mock_message_1 = MagicMock()
            mock_message_1.content = None
            mock_tc = MagicMock()
            mock_tc.id = "call_1"
            mock_tc.function.name = "read_file"
            mock_tc.function.arguments = '{"path": "test.txt"}'
            mock_message_1.tool_calls = [mock_tc]
            mock_choice_1.message = mock_message_1
            mock_choice_1.finish_reason = "tool_calls"
            mock_response_1.choices = [mock_choice_1]
            mock_response_1.usage = MagicMock()
            mock_response_1.usage.prompt_tokens = 100
            mock_response_1.usage.completion_tokens = 20
            mock_response_1.usage.total_tokens = 120

            # 第二次 API 调用
            mock_response_2 = MagicMock()
            mock_choice_2 = MagicMock()
            mock_message_2 = MagicMock()
            mock_message_2.content = "文件内容如下。"
            mock_message_2.tool_calls = None
            mock_choice_2.message = mock_message_2
            mock_choice_2.finish_reason = "stop"
            mock_response_2.choices = [mock_choice_2]
            mock_response_2.usage = MagicMock()
            mock_response_2.usage.prompt_tokens = 150
            mock_response_2.usage.completion_tokens = 30
            mock_response_2.usage.total_tokens = 180

            agent.client.chat.completions.create.side_effect = [_response_to_chunks(mock_response_1), _response_to_chunks(mock_response_2)]

            events = await self._collect_events(agent, "read test.txt")

            # 检查对话历史中的 tool 消息不应包含 hint
            tool_messages = [m for m in agent.conversation_history if m.get("role") == "tool"]
            assert len(tool_messages) >= 1
            import json
            tool_content = json.loads(tool_messages[0]["content"])
            assert "hint" not in tool_content


# === 流式辅助函数 ===

def _response_to_chunks(mock_response):
    """将非流式 mock response 转换为流式 chunk 列表（iter），便于迁移旧测试。

    接受一个具有 .choices[0].message.content/.tool_calls 和 .usage 的 MagicMock，
    返回一个 iter(chunks) 可直接赋值给 create.return_value 或 side_effect 列表。
    """
    msg = mock_response.choices[0].message
    content = msg.content
    tool_calls = msg.tool_calls

    chunks = []

    if content:
        chunks.append(_make_stream_chunk(delta_content=content))

    if tool_calls:
        for i, tc in enumerate(tool_calls):
            chunks.append(_make_stream_chunk(delta_tool_calls=[
                _make_tool_call_delta(
                    i,
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
            ]))
        chunks.append(_make_stream_chunk(finish_reason="tool_calls"))
    else:
        chunks.append(_make_stream_chunk(finish_reason="stop"))

    usage = mock_response.usage
    chunks.append(_make_stream_chunk(usage={
        "prompt_tokens": usage.prompt_tokens or 0,
        "completion_tokens": usage.completion_tokens or 0,
        "total_tokens": usage.total_tokens or 0,
    }))

    return iter(chunks)


def _make_stream_chunk(delta_content=None, delta_tool_calls=None, finish_reason=None, usage=None):
    """构造一个模拟的流式 chunk 对象。"""
    chunk = MagicMock()
    if usage is not None and not delta_content and not delta_tool_calls and finish_reason is None:
        # usage-only chunk（最后一个），没有 choices
        chunk.choices = []
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = usage.get("prompt_tokens", 0)
        mock_usage.completion_tokens = usage.get("completion_tokens", 0)
        mock_usage.total_tokens = usage.get("total_tokens", 0)
        chunk.usage = mock_usage
        return chunk

    mock_choice = MagicMock()
    mock_delta = MagicMock()
    mock_delta.content = delta_content
    mock_delta.tool_calls = delta_tool_calls
    # 默认无 reasoning_content
    mock_delta.reasoning_content = None
    mock_choice.delta = mock_delta
    mock_choice.finish_reason = finish_reason
    chunk.choices = [mock_choice]

    if usage is not None:
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = usage.get("prompt_tokens", 0)
        mock_usage.completion_tokens = usage.get("completion_tokens", 0)
        mock_usage.total_tokens = usage.get("total_tokens", 0)
        chunk.usage = mock_usage
    else:
        chunk.usage = None

    return chunk


def _make_tool_call_delta(index, id=None, name=None, arguments=None):
    """构造一个模拟的工具调用 delta。"""
    tc = MagicMock()
    tc.index = index
    tc.id = id
    if name is not None or arguments is not None:
        tc.function = MagicMock()
        tc.function.name = name
        tc.function.arguments = arguments
    else:
        tc.function = None
    return tc


class TestPromptStream:
    """测试 prompt_stream() 流式输出"""

    @staticmethod
    async def _collect_events(agent, user_input="hello"):
        events = []
        async for event in agent.prompt_stream(user_input):
            events.append(event)
        return events

    @pytest.mark.asyncio
    async def test_text_streamed_in_multiple_deltas(self):
        """文本应通过多个 text_update 事件逐步输出"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")

            chunks = [
                _make_stream_chunk(delta_content="Hello"),
                _make_stream_chunk(delta_content=" world"),
                _make_stream_chunk(delta_content="!"),
                _make_stream_chunk(finish_reason="stop"),
                _make_stream_chunk(usage={"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}),
            ]
            agent.client.chat.completions.create.return_value = iter(chunks)

            events = await self._collect_events(agent)

            text_events = [e for e in events if e["type"] == "text_update"]
            assert len(text_events) == 3
            assert text_events[0]["delta"] == "Hello"
            assert text_events[1]["delta"] == " world"
            assert text_events[2]["delta"] == "!"

    @pytest.mark.asyncio
    async def test_agent_end_with_usage(self):
        """流式结束后应 yield agent_end 事件并包含 usage"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")

            chunks = [
                _make_stream_chunk(delta_content="hi"),
                _make_stream_chunk(finish_reason="stop"),
                _make_stream_chunk(usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}),
            ]
            agent.client.chat.completions.create.return_value = iter(chunks)

            events = await self._collect_events(agent)

            end_events = [e for e in events if e["type"] == "agent_end"]
            assert len(end_events) == 1
            assert end_events[0]["usage"].input == 100
            assert end_events[0]["usage"].output == 20

    @pytest.mark.asyncio
    async def test_tool_call_streamed(self):
        """工具调用的 arguments 应从多个 chunk 累积后正确解析"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            agent.tools.read_file.return_value = {"success": True, "content": "file content", "path": "test.txt"}

            # 第一轮：工具调用（分段到达）
            tc_chunks = [
                _make_stream_chunk(delta_tool_calls=[
                    _make_tool_call_delta(0, id="call_1", name="read_file", arguments='{"path":')
                ]),
                _make_stream_chunk(delta_tool_calls=[
                    _make_tool_call_delta(0, arguments=' "test.txt"}')
                ]),
                _make_stream_chunk(finish_reason="tool_calls"),
                _make_stream_chunk(usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}),
            ]

            # 第二轮：正常文本回复
            text_chunks = [
                _make_stream_chunk(delta_content="文件内容已读取。"),
                _make_stream_chunk(finish_reason="stop"),
                _make_stream_chunk(usage={"prompt_tokens": 80, "completion_tokens": 15, "total_tokens": 95}),
            ]

            agent.client.chat.completions.create.side_effect = [
                iter(tc_chunks),
                iter(text_chunks),
            ]

            events = await self._collect_events(agent, "read test.txt")

            # 应有 tool_start 和 tool_end 事件
            tool_start_events = [e for e in events if e["type"] == "tool_start"]
            assert len(tool_start_events) == 1
            assert tool_start_events[0]["tool_name"] == "read_file"
            assert tool_start_events[0]["args"]["path"] == "test.txt"

            tool_end_events = [e for e in events if e["type"] == "tool_end"]
            assert len(tool_end_events) == 1

            # 应有文本回复
            text_events = [e for e in events if e["type"] == "text_update"]
            assert any("文件内容" in e["delta"] for e in text_events)

    @pytest.mark.asyncio
    async def test_conversation_history_updated(self):
        """流式结束后对话历史应正确更新"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")

            chunks = [
                _make_stream_chunk(delta_content="Hi there!"),
                _make_stream_chunk(finish_reason="stop"),
                _make_stream_chunk(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}),
            ]
            agent.client.chat.completions.create.return_value = iter(chunks)

            await self._collect_events(agent, "hello")

            assert len(agent.conversation_history) == 2
            assert agent.conversation_history[0]["role"] == "user"
            assert agent.conversation_history[0]["content"] == "hello"
            assert agent.conversation_history[1]["role"] == "assistant"
            assert agent.conversation_history[1]["content"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_interrupt_during_stream(self):
        """流式响应被 Ctrl+C 中断时应返回 interrupted 事件"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")

            def interrupted_stream():
                yield _make_stream_chunk(delta_content="partial")
                raise KeyboardInterrupt()

            agent.client.chat.completions.create.return_value = interrupted_stream()

            events = await self._collect_events(agent, "test")

            interrupted_events = [e for e in events if e["type"] == "interrupted"]
            assert len(interrupted_events) == 1
            assert "中断" in interrupted_events[0]["message"]

    @pytest.mark.asyncio
    async def test_error_during_create(self):
        """create() 调用失败时应返回 error 事件"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.client.chat.completions.create.side_effect = RuntimeError("boom")

            events = await self._collect_events(agent, "test")

            error_events = [e for e in events if e["type"] == "error"]
            assert len(error_events) == 1
            assert "boom" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_last_prompt_tokens_updated(self):
        """流式完成后 _last_prompt_tokens 应更新"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")

            chunks = [
                _make_stream_chunk(delta_content="ok"),
                _make_stream_chunk(finish_reason="stop"),
                _make_stream_chunk(usage={"prompt_tokens": 789, "completion_tokens": 10, "total_tokens": 799}),
            ]
            agent.client.chat.completions.create.return_value = iter(chunks)

            await self._collect_events(agent, "test")

            assert agent._last_prompt_tokens == 789

    @pytest.mark.asyncio
    async def test_empty_content_not_in_history(self):
        """如果模型返回纯工具调用无文本，assistant content 应为 None"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")
            agent.tools = MagicMock()
            agent.tools.list_files.return_value = {"success": True, "matches": []}

            # 第一轮：纯工具调用，无文本
            tc_chunks = [
                _make_stream_chunk(delta_tool_calls=[
                    _make_tool_call_delta(0, id="call_1", name="list_files", arguments='{"path": "."}')
                ]),
                _make_stream_chunk(finish_reason="tool_calls"),
                _make_stream_chunk(usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}),
            ]

            # 第二轮：文本回复
            text_chunks = [
                _make_stream_chunk(delta_content="done"),
                _make_stream_chunk(finish_reason="stop"),
                _make_stream_chunk(usage={"prompt_tokens": 60, "completion_tokens": 5, "total_tokens": 65}),
            ]

            agent.client.chat.completions.create.side_effect = [
                iter(tc_chunks),
                iter(text_chunks),
            ]

            await self._collect_events(agent, "list files")

            # 找到工具调用的 assistant 消息
            assistant_msgs = [m for m in agent.conversation_history if m.get("role") == "assistant"]
            assert len(assistant_msgs) >= 1
            # 第一个 assistant 消息（工具调用）的 content 应为 None
            assert assistant_msgs[0]["content"] is None
            assert "tool_calls" in assistant_msgs[0]

    @pytest.mark.asyncio
    async def test_reasoning_content_emitted(self):
        """有 reasoning_content 时应 yield reasoning 事件"""
        with patch("src.agent.OpenAI"):
            agent = Agent(api_key="test-key", model="test-model")

            chunk1 = _make_stream_chunk(delta_content=None)
            chunk1.choices[0].delta.reasoning_content = "Let me think..."
            chunk2 = _make_stream_chunk(delta_content="Answer is 42.")
            chunk3 = _make_stream_chunk(finish_reason="stop")
            chunk4 = _make_stream_chunk(usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})

            agent.client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3, chunk4])

            events = await self._collect_events(agent, "what is 6*7?")

            reasoning_events = [e for e in events if e["type"] == "reasoning"]
            assert len(reasoning_events) == 1
            assert "think" in reasoning_events[0]["content"]


class TestAutoTest:
    """自动测试功能测试"""

    def test_auto_test_enabled_by_default(self):
        """auto_test 默认启用"""
        agent = Agent(api_key="test-key")
        assert agent.auto_test is True

    def test_auto_test_can_be_disabled(self):
        """auto_test 可以关闭"""
        agent = Agent(api_key="test-key")
        agent.auto_test = False
        assert agent.auto_test is False

    def test_is_code_file_python(self):
        """Python 文件被识别为代码文件"""
        assert Agent._is_code_file("src/agent.py") is True
        assert Agent._is_code_file("main.py") is True

    def test_is_code_file_javascript(self):
        """JavaScript/TypeScript 文件被识别为代码文件"""
        assert Agent._is_code_file("app.js") is True
        assert Agent._is_code_file("index.ts") is True
        assert Agent._is_code_file("Component.jsx") is True
        assert Agent._is_code_file("Component.tsx") is True

    def test_is_code_file_other_languages(self):
        """其他语言的代码文件被正确识别"""
        assert Agent._is_code_file("main.rs") is True
        assert Agent._is_code_file("main.go") is True
        assert Agent._is_code_file("App.java") is True
        assert Agent._is_code_file("main.c") is True
        assert Agent._is_code_file("main.cpp") is True

    def test_is_code_file_non_code(self):
        """非代码文件不被识别为代码文件"""
        assert Agent._is_code_file("README.md") is False
        assert Agent._is_code_file("data.json") is False
        assert Agent._is_code_file("style.css") is False
        assert Agent._is_code_file("config.yaml") is False
        assert Agent._is_code_file("image.png") is False
        assert Agent._is_code_file("") is False

    def test_is_code_file_case_insensitive(self):
        """扩展名检测不区分大小写"""
        assert Agent._is_code_file("Main.PY") is True
        assert Agent._is_code_file("app.JS") is True
        assert Agent._is_code_file("lib.Rs") is True

    def test_get_test_command_python_project(self):
        """Python + pytest 项目返回 pytest 命令"""
        agent = Agent(api_key="test-key")
        # 当前项目就是 Python + pytest
        cmd = agent._get_test_command()
        assert cmd is not None
        assert "pytest" in cmd

    def test_get_test_command_returns_string(self):
        """测试命令是字符串类型"""
        agent = Agent(api_key="test-key")
        cmd = agent._get_test_command()
        if cmd is not None:
            assert isinstance(cmd, str)
            assert len(cmd) > 0

    def test_run_auto_test_returns_dict(self, monkeypatch):
        """_run_auto_test 返回包含 success/command/stdout/stderr 的字典"""
        agent = Agent(api_key="test-key")
        # Mock subprocess.run 避免实际运行 pytest（会递归）
        import subprocess as _sp
        class FakeResult:
            returncode = 0
            stdout = "10 passed"
            stderr = ""
        monkeypatch.setattr(_sp, "run", lambda *a, **kw: FakeResult())
        result = agent._run_auto_test()
        assert result is not None
        assert "success" in result
        assert "command" in result
        assert "stdout" in result
        assert "stderr" in result
        assert "returncode" in result
        assert isinstance(result["success"], bool)

    def test_run_auto_test_passes_on_success(self, monkeypatch):
        """subprocess 返回 0 时，自动测试报告通过"""
        agent = Agent(api_key="test-key")
        import subprocess as _sp
        class FakeResult:
            returncode = 0
            stdout = "383 passed"
            stderr = ""
        monkeypatch.setattr(_sp, "run", lambda *a, **kw: FakeResult())
        result = agent._run_auto_test()
        assert result is not None
        assert result["success"] is True
        assert result["returncode"] == 0

    def test_run_auto_test_fails_on_nonzero_returncode(self, monkeypatch):
        """subprocess 返回非 0 时，自动测试报告失败"""
        agent = Agent(api_key="test-key")
        import subprocess as _sp
        class FakeResult:
            returncode = 1
            stdout = "1 failed"
            stderr = "FAILED test_example"
        monkeypatch.setattr(_sp, "run", lambda *a, **kw: FakeResult())
        result = agent._run_auto_test()
        assert result is not None
        assert result["success"] is False
        assert result["returncode"] == 1

    def test_run_auto_test_handles_timeout(self, monkeypatch):
        """测试超时时返回失败结果"""
        agent = Agent(api_key="test-key")
        import subprocess as _sp
        def timeout_run(*a, **kw):
            raise _sp.TimeoutExpired(cmd="pytest", timeout=60)
        monkeypatch.setattr(_sp, "run", timeout_run)
        result = agent._run_auto_test()
        assert result is not None
        assert result["success"] is False
        assert "超时" in result["stderr"]

    def test_test_commands_mapping_exists(self):
        """TEST_COMMANDS 映射包含主要框架"""
        assert "pytest" in Agent.TEST_COMMANDS
        assert "npm" in Agent.TEST_COMMANDS
        assert "cargo" in Agent.TEST_COMMANDS
        assert "go" in Agent.TEST_COMMANDS

    def test_code_file_extensions_contains_common(self):
        """CODE_FILE_EXTENSIONS 包含常见语言扩展名"""
        assert ".py" in Agent.CODE_FILE_EXTENSIONS
        assert ".js" in Agent.CODE_FILE_EXTENSIONS
        assert ".ts" in Agent.CODE_FILE_EXTENSIONS
        assert ".rs" in Agent.CODE_FILE_EXTENSIONS
        assert ".go" in Agent.CODE_FILE_EXTENSIONS
        assert ".java" in Agent.CODE_FILE_EXTENSIONS

    def test_auto_test_timeout_reasonable(self):
        """自动测试超时设置合理（30-120 秒）"""
        assert 30 <= Agent.AUTO_TEST_TIMEOUT <= 120


class TestAutoTestIntegration:
    """自动测试在工具调用流程中的集成测试"""

    @staticmethod
    def _make_agent():
        agent = Agent(api_key="test-key")
        agent.auto_test = True
        return agent

    def test_write_file_code_triggers_auto_test(self, tmp_path):
        """write_file 写入 .py 文件时触发自动测试"""
        agent = self._make_agent()
        test_ran = []

        original_run = agent._run_auto_test

        def mock_run():
            test_ran.append(True)
            return {"success": True, "command": "pytest", "stdout": "passed", "stderr": "", "returncode": 0}

        agent._run_auto_test = mock_run

        tc = ToolCallRequest(id="tc1", name="write_file",
                             arguments={"path": str(tmp_path / "hello.py"), "content": "print('hi')"})
        result = agent._execute_tool_call(tc)
        assert result.get("success") is True

        # 模拟 prompt 循环中的自动测试检查逻辑
        if (agent.auto_test
                and tc.name in ("write_file", "edit_file")
                and result.get("success")
                and Agent._is_code_file(tc.arguments.get("path", ""))):
            agent._run_auto_test()

        assert len(test_ran) == 1

    def test_write_file_non_code_no_auto_test(self, tmp_path):
        """write_file 写入 .md 文件时不触发自动测试"""
        agent = self._make_agent()
        test_ran = []

        def mock_run():
            test_ran.append(True)
            return {"success": True, "command": "pytest", "stdout": "", "stderr": "", "returncode": 0}

        agent._run_auto_test = mock_run

        tc = ToolCallRequest(id="tc1", name="write_file",
                             arguments={"path": str(tmp_path / "readme.md"), "content": "# Hello"})
        result = agent._execute_tool_call(tc)
        assert result.get("success") is True

        if (agent.auto_test
                and tc.name in ("write_file", "edit_file")
                and result.get("success")
                and Agent._is_code_file(tc.arguments.get("path", ""))):
            agent._run_auto_test()

        assert len(test_ran) == 0

    def test_disabled_auto_test_no_trigger(self, tmp_path):
        """auto_test=False 时不触发自动测试"""
        agent = self._make_agent()
        agent.auto_test = False
        test_ran = []

        def mock_run():
            test_ran.append(True)
            return {"success": True, "command": "pytest", "stdout": "", "stderr": "", "returncode": 0}

        agent._run_auto_test = mock_run

        tc = ToolCallRequest(id="tc1", name="write_file",
                             arguments={"path": str(tmp_path / "app.py"), "content": "x=1"})
        result = agent._execute_tool_call(tc)

        if (agent.auto_test
                and tc.name in ("write_file", "edit_file")
                and result.get("success")
                and Agent._is_code_file(tc.arguments.get("path", ""))):
            agent._run_auto_test()

        assert len(test_ran) == 0

    def test_failed_write_no_auto_test(self):
        """write_file 失败时不触发自动测试"""
        agent = self._make_agent()
        test_ran = []

        def mock_run():
            test_ran.append(True)
            return {"success": True, "command": "pytest", "stdout": "", "stderr": "", "returncode": 0}

        agent._run_auto_test = mock_run

        # 模拟失败的 write_file 结果
        result = {"success": False, "error": "Permission denied", "path": "/root/app.py"}

        if (agent.auto_test
                and "write_file" in ("write_file", "edit_file")
                and result.get("success")
                and Agent._is_code_file("/root/app.py")):
            agent._run_auto_test()

        assert len(test_ran) == 0

    def test_edit_file_code_triggers_auto_test(self, tmp_path):
        """edit_file 成功编辑 .py 文件时触发自动测试"""
        # 先创建文件
        py_file = tmp_path / "module.py"
        py_file.write_text("x = 1\n")

        agent = self._make_agent()
        test_ran = []

        def mock_run():
            test_ran.append(True)
            return {"success": True, "command": "pytest", "stdout": "ok", "stderr": "", "returncode": 0}

        agent._run_auto_test = mock_run

        tc = ToolCallRequest(id="tc1", name="edit_file",
                             arguments={"path": str(py_file), "old_content": "x = 1", "new_content": "x = 2"})
        result = agent._execute_tool_call(tc)
        assert result.get("success") is True

        if (agent.auto_test
                and tc.name in ("write_file", "edit_file")
                and result.get("success")
                and Agent._is_code_file(tc.arguments.get("path", ""))):
            agent._run_auto_test()

        assert len(test_ran) == 1

    def test_read_file_no_auto_test(self, tmp_path):
        """read_file 不触发自动测试"""
        py_file = tmp_path / "test.py"
        py_file.write_text("pass\n")

        agent = self._make_agent()
        test_ran = []

        def mock_run():
            test_ran.append(True)
            return {"success": True, "command": "pytest", "stdout": "", "stderr": "", "returncode": 0}

        agent._run_auto_test = mock_run

        tc = ToolCallRequest(id="tc1", name="read_file",
                             arguments={"path": str(py_file)})
        result = agent._execute_tool_call(tc)

        if (agent.auto_test
                and tc.name in ("write_file", "edit_file")
                and result.get("success")
                and Agent._is_code_file(tc.arguments.get("path", ""))):
            agent._run_auto_test()

        assert len(test_ran) == 0


class TestAutoTestResultIsolation:
    """验证 auto_test 附加到 enriched 时不污染原始 result dict"""

    def test_enriched_auto_test_does_not_mutate_original_result(self):
        """_enrich_tool_error 成功时返回原始引用，浅拷贝后附加 auto_test 不污染原始"""
        original_result = {"success": True, "path": "test.py"}
        enriched = Agent._enrich_tool_error("write_file", original_result)
        assert enriched is original_result

        enriched = {**enriched}
        enriched["auto_test"] = {"summary": "pass", "success": True}

        assert "auto_test" not in original_result

    def test_without_copy_original_result_would_be_mutated(self):
        """不做浅拷贝时，原始 result 会被污染（验证 bug 存在性）"""
        original_result = {"success": True, "path": "test.py"}
        enriched = Agent._enrich_tool_error("write_file", original_result)
        assert enriched is original_result

        enriched["auto_test"] = {"summary": "test"}
        assert "auto_test" in original_result

        del original_result["auto_test"]

    def test_failed_result_enriched_is_new_dict(self):
        """_enrich_tool_error 失败时返回新字典，不存在污染问题"""
        original_result = {"success": False, "error": "Old content not found", "path": "test.py"}
        enriched = Agent._enrich_tool_error("edit_file", original_result)
        assert enriched is not original_result
        assert "hint" in enriched
        assert "hint" not in original_result


class TestClassifyApiError:
    """测试 _classify_api_error 静态方法：将 API 异常转换为 (event_type, message) 元组"""

    def test_keyboard_interrupt(self):
        """KeyboardInterrupt 应返回 interrupted 事件"""
        event_type, msg = Agent._classify_api_error(KeyboardInterrupt())
        assert event_type == "interrupted"
        assert "中断" in msg

    def test_authentication_error(self):
        """AuthenticationError 应返回认证相关错误消息"""
        from openai import AuthenticationError
        from unittest.mock import MagicMock, PropertyMock
        mock_response = MagicMock()
        type(mock_response).status_code = PropertyMock(return_value=401)
        type(mock_response).headers = PropertyMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "Invalid API key"}}
        exc = AuthenticationError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "认证失败" in msg
        assert "OPENAI_API_KEY" in msg

    def test_rate_limit_error(self):
        """RateLimitError 应返回速率限制相关错误消息"""
        from openai import RateLimitError
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        type(mock_response).status_code = MagicMock(return_value=429)
        type(mock_response).headers = MagicMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "Rate limit"}}
        exc = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit"}},
        )
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "速率限制" in msg

    def test_api_timeout_error(self):
        """APITimeoutError 应返回超时相关错误消息"""
        from openai import APITimeoutError
        from unittest.mock import MagicMock
        exc = APITimeoutError(request=MagicMock())
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "超时" in msg

    def test_api_connection_error(self):
        """APIConnectionError 应返回连接失败相关错误消息"""
        from openai import APIConnectionError
        from unittest.mock import MagicMock
        exc = APIConnectionError(request=MagicMock())
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "连接失败" in msg

    def test_bad_request_context_length(self):
        """BadRequestError 含 context_length 时应提示上下文过长"""
        from openai import BadRequestError
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        type(mock_response).status_code = MagicMock(return_value=400)
        type(mock_response).headers = MagicMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "context_length_exceeded"}}
        exc = BadRequestError(
            message="This model's maximum context_length is 8192 tokens",
            response=mock_response,
            body={"error": {"message": "context_length_exceeded"}},
        )
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "上下文过长" in msg
        assert "/clear" in msg

    def test_bad_request_generic(self):
        """BadRequestError 不含 context_length 时应提示参数错误"""
        from openai import BadRequestError
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        type(mock_response).status_code = MagicMock(return_value=400)
        type(mock_response).headers = MagicMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "Invalid param"}}
        exc = BadRequestError(
            message="Invalid param",
            response=mock_response,
            body={"error": {"message": "Invalid param"}},
        )
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "参数错误" in msg

    def test_api_status_error(self):
        """APIStatusError 应返回含 HTTP 状态码的错误消息"""
        from openai import APIStatusError
        from unittest.mock import MagicMock, PropertyMock
        mock_response = MagicMock()
        type(mock_response).status_code = PropertyMock(return_value=503)
        type(mock_response).headers = PropertyMock(return_value={})
        mock_response.json.return_value = {"error": {"message": "Service unavailable"}}
        exc = APIStatusError(
            message="Service unavailable",
            response=mock_response,
            body={"error": {"message": "Service unavailable"}},
        )
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "503" in msg

    def test_unknown_exception(self):
        """未知异常应返回通用错误消息"""
        exc = RuntimeError("something unexpected")
        event_type, msg = Agent._classify_api_error(exc)
        assert event_type == "error"
        assert "未知错误" in msg
        assert "something unexpected" in msg

    def test_returns_tuple(self):
        """返回值应为 (str, str) 二元组"""
        result = Agent._classify_api_error(RuntimeError("test"))
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)


class TestProcessToolCalls:
    """测试 _process_tool_calls 共享方法"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            a.tools = MagicMock()
            a.auto_test = False  # 禁用自动测试以简化测试
            return a

    @pytest.mark.asyncio
    async def test_yields_tool_start_and_end(self, agent):
        """应为每个工具调用 yield tool_start 和 tool_end 事件"""
        agent.tools.read_file.return_value = {"success": True, "content": "hi", "path": "a.txt"}
        tc = ToolCallRequest(id="c1", name="read_file", arguments={"path": "a.txt"})
        messages = []

        events = []
        async for event in agent._process_tool_calls([tc], messages):
            events.append(event)

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_end" in types

    @pytest.mark.asyncio
    async def test_appends_tool_msg_to_messages(self, agent):
        """应将工具结果追加到 messages 和 conversation_history"""
        agent.tools.read_file.return_value = {"success": True, "content": "hello", "path": "f.txt"}
        tc = ToolCallRequest(id="c1", name="read_file", arguments={"path": "f.txt"})
        messages = []

        async for _ in agent._process_tool_calls([tc], messages):
            pass

        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "c1"
        # conversation_history 也应有对应 tool 消息
        tool_msgs = [m for m in agent.conversation_history if m.get("role") == "tool"]
        assert len(tool_msgs) == 1

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, agent):
        """多个工具调用应依次执行"""
        agent.tools.read_file.return_value = {"success": True, "content": "a", "path": "a.txt"}
        agent.tools.list_files.return_value = {"success": True, "items": []}
        tc1 = ToolCallRequest(id="c1", name="read_file", arguments={"path": "a.txt"})
        tc2 = ToolCallRequest(id="c2", name="list_files", arguments={"path": "."})
        messages = []

        events = []
        async for event in agent._process_tool_calls([tc1, tc2], messages):
            events.append(event)

        tool_starts = [e for e in events if e["type"] == "tool_start"]
        tool_ends = [e for e in events if e["type"] == "tool_end"]
        assert len(tool_starts) == 2
        assert len(tool_ends) == 2
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_interrupt_yields_interrupted_and_cleans_history(self, agent):
        """工具中断时应 yield interrupted 事件并清理历史"""
        # 先在历史中加入 assistant 消息（模拟正常流程）
        agent.conversation_history.append({"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]})
        agent.tools.read_file.side_effect = KeyboardInterrupt()
        tc = ToolCallRequest(id="c1", name="read_file", arguments={"path": "test.txt"})
        messages = []

        events = []
        async for event in agent._process_tool_calls([tc], messages):
            events.append(event)

        interrupted = [e for e in events if e["type"] == "interrupted"]
        assert len(interrupted) == 1
        # 历史应被清理（assistant 消息被移除）
        assert not any(m.get("role") == "assistant" for m in agent.conversation_history)

    @pytest.mark.asyncio
    async def test_enriched_hint_in_tool_msg(self, agent):
        """工具失败时，tool 消息中应包含 hint"""
        import json
        agent.tools.read_file.return_value = {
            "success": False, "error": "[Errno 2] No such file or directory: 'x.txt'", "path": "x.txt"
        }
        tc = ToolCallRequest(id="c1", name="read_file", arguments={"path": "x.txt"})
        messages = []

        async for _ in agent._process_tool_calls([tc], messages):
            pass

        assert len(messages) == 1
        content = json.loads(messages[0]["content"])
        assert "hint" in content


class TestHandleContextCheck:
    """测试 _handle_context_check 共享方法"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model", max_context_tokens=1000)
            return a

    @pytest.mark.asyncio
    async def test_ok_status_no_events(self, agent):
        """上下文使用率低时不应 yield 任何事件"""
        agent._last_prompt_tokens = 100  # 10%
        from src.models import Usage
        total_usage = Usage()
        events = []
        async for event in agent._handle_context_check(total_usage):
            events.append(event)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_warning_yields_context_warning(self, agent):
        """达到警告阈值时应 yield context_warning"""
        agent._last_prompt_tokens = 810  # 81%
        from src.models import Usage
        total_usage = Usage()
        events = []
        async for event in agent._handle_context_check(total_usage):
            events.append(event)
        assert len(events) == 1
        assert events[0]["type"] == "context_warning"

    @pytest.mark.asyncio
    async def test_critical_short_history_yields_warning(self, agent):
        """临界状态但对话太短时应降级为 context_warning"""
        agent._last_prompt_tokens = 920  # 92%
        agent.conversation_history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        from src.models import Usage
        total_usage = Usage()
        events = []
        async for event in agent._handle_context_check(total_usage):
            events.append(event)
        assert len(events) == 1
        assert events[0]["type"] == "context_warning"

    @pytest.mark.asyncio
    async def test_critical_with_enough_history_auto_compacts(self, agent):
        """临界状态且有足够历史时应自动 compact"""
        agent._last_prompt_tokens = 920  # 92%
        # 填入足够多的消息
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            agent.conversation_history.append({"role": role, "content": f"msg {i}"})

        # Mock LLM 摘要调用
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "对话摘要"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        agent.client.chat.completions.create.return_value = mock_response

        from src.models import Usage
        total_usage = Usage()
        events = []
        async for event in agent._handle_context_check(total_usage):
            events.append(event)

        compact_events = [e for e in events if e["type"] == "auto_compact"]
        assert len(compact_events) == 1
        assert compact_events[0]["removed"] > 0
        # total_usage 应包含摘要的 token 消耗
        assert total_usage.input == 100
        assert total_usage.output == 50
