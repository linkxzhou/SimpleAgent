"""SubAgent 功能测试（Issue #6）"""

import pytest
from src.agent import Agent
from unittest.mock import Mock


class TestSubAgentBasic:
    """SubAgent 基础功能测试"""
    
    def test_agent_has_subagent_attributes(self):
        """测试 Agent 是否包含 SubAgent 相关属性"""
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        
        assert hasattr(agent, "parent")
        assert hasattr(agent, "subagents")
        assert hasattr(agent, "shared_context")
        assert hasattr(agent, "delegate_task")
        assert hasattr(agent, "_build_subagent_prompt")
        assert hasattr(agent, "get_subagent_results")
    
    def test_agent_parent_is_none_by_default(self):
        """测试顶层 Agent 的 parent 默认为 None"""
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        assert agent.parent is None
    
    def test_agent_subagents_list_empty(self):
        """测试 SubAgent 列表初始为空"""
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        assert agent.subagents == []
    
    def test_agent_shared_context_empty(self):
        """测试共享上下文初始为空字典"""
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        assert agent.shared_context == {}
    
    def test_agent_with_parent(self):
        """测试创建带父 Agent 的 SubAgent"""
        parent = Agent(api_key="test-key", model="gpt-4o-mini")
        child = Agent(api_key="test-key", model="gpt-4o-mini", parent=parent)
        
        assert child.parent is parent
        assert child.parent.parent is None


class TestSubAgentContextLake:
    """Context Lake 模式测试（共享/隔离上下文）"""
    
    def test_shared_context_isolation(self):
        """测试共享上下文的独立性"""
        agent1 = Agent(api_key="test-key", model="gpt-4o-mini")
        agent2 = Agent(api_key="test-key", model="gpt-4o-mini")
        
        agent1.shared_context["project"] = "test-project"
        
        # agent2 的共享上下文应该是独立的
        assert "project" not in agent2.shared_context
    
    def test_conversation_history_isolation(self):
        """测试对话历史的独立性"""
        parent = Agent(api_key="test-key", model="gpt-4o-mini")
        child = Agent(api_key="test-key", model="gpt-4o-mini", parent=parent)
        
        parent.conversation_history.append({"role": "user", "content": "parent message"})
        child.conversation_history.append({"role": "user", "content": "child message"})
        
        assert len(parent.conversation_history) == 1
        assert len(child.conversation_history) == 1
        assert parent.conversation_history[0]["content"] == "parent message"
        assert child.conversation_history[0]["content"] == "child message"


class TestBuildSubAgentPrompt:
    """SubAgent prompt 构建测试"""
    
    def test_build_subagent_prompt_basic(self):
        """测试基础 SubAgent prompt 生成"""
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        
        prompt = agent._build_subagent_prompt(
            task="修复 bug #123",
            role="bug-fixer"
        )
        
        assert "SubAgent" in prompt
        assert "bug-fixer" in prompt
        assert "修复 bug #123" in prompt
        assert "专注完成上述任务" in prompt
    
    def test_build_subagent_prompt_with_shared_context(self):
        """测试包含共享上下文的 prompt"""
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        agent.shared_context = {
            "project_name": "SimpleAgent",
            "version": "0.68.0",
            "files_modified": ["src/agent.py", "tests/test_subagent.py"],
        }
        
        prompt = agent._build_subagent_prompt(
            task="添加新功能",
            role="developer"
        )
        
        assert "共享上下文" in prompt
        assert "project_name" in prompt
        assert "version" in prompt
        assert "files_modified" in prompt


class TestGetSubAgentResults:
    """SubAgent 结果获取测试"""
    
    def test_get_subagent_results_empty(self):
        """测试没有 SubAgent 时返回空列表"""
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        results = agent.get_subagent_results()
        assert results == []
    
    def test_get_subagent_results_with_subagents(self):
        """测试有 SubAgent 时返回摘要"""
        parent = Agent(api_key="test-key", model="gpt-4o-mini")
        
        # 创建 2 个 SubAgent
        child1 = Agent(api_key="test-key", model="gpt-4o-mini", parent=parent)
        child1.conversation_history.append({"role": "assistant", "content": "Child 1 output"})
        parent.subagents.append(child1)
        
        child2 = Agent(api_key="test-key", model="gpt-4o-mini", parent=parent)
        child2.conversation_history.append({"role": "assistant", "content": "Child 2 output with a very long message that should be truncated" * 5})
        parent.subagents.append(child2)
        
        results = parent.get_subagent_results()
        
        assert len(results) == 2
        assert results[0]["index"] == 0
        assert results[0]["conversation_length"] == 1
        assert "Child 1 output" in results[0]["last_message"]
        
        assert results[1]["index"] == 1
        assert results[1]["conversation_length"] == 1
        assert len(results[1]["last_message"]) <= 203  # 200 + "..."


class TestDelegateTaskAsync:
    """delegate_task 异步执行测试（Bug #195 修复）"""
    
    @pytest.mark.asyncio
    async def test_delegate_task_is_async(self):
        """测试 delegate_task 是异步方法"""
        import inspect
        from src.agent import Agent
        
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        assert inspect.iscoroutinefunction(agent.delegate_task)
    
    @pytest.mark.asyncio
    async def test_delegate_task_in_running_loop(self):
        """测试在已运行的事件循环中调用 delegate_task 不崩溃（Bug #195）"""
        import asyncio
        from unittest.mock import AsyncMock, patch
        
        agent = Agent(api_key="test-key", model="gpt-4o-mini")
        
        # 模拟 prompt_stream 返回简单事件
        async def mock_prompt_stream(user_input):
            yield {"type": "text_update", "delta": "测试输出"}
            yield {"type": "agent_end", "usage": None}
        
        # 确认当前在事件循环中
        assert asyncio.get_event_loop().is_running()
        
        # 使用 patch 替换 prompt_stream
        with patch.object(Agent, 'prompt_stream', side_effect=mock_prompt_stream):
            result = await agent.delegate_task(task="测试任务", role="worker")
        
        # 验证：不应崩溃，应返回成功结果
        assert result["success"] is True
        assert "测试输出" in result["output"]
        assert result["error"] is None
        assert len(agent.subagents) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
