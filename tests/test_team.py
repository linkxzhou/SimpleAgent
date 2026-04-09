"""测试 Team 协作功能（Issue #7）。

包含：
- TeamConfig 数据类验证
- create_team() 方法测试
- coordinate_team() 方法测试（并行/顺序）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.models import TeamConfig, Usage
from src.agent import Agent


class TestTeamConfig:
    """TeamConfig 数据类测试。"""
    
    def test_team_config_valid(self):
        """测试有效的 TeamConfig。"""
        config = TeamConfig(
            team_size=3,
            roles=["researcher", "coder", "reviewer"],
            shared_context={"project": "test"},
            parallel=True,
            max_workers=5,
        )
        assert config.team_size == 3
        assert len(config.roles) == 3
        assert config.shared_context["project"] == "test"
        assert config.parallel is True
        assert config.max_workers == 5
    
    def test_team_config_default_values(self):
        """测试 TeamConfig 默认值。"""
        config = TeamConfig(
            team_size=2,
            roles=["worker1", "worker2"],
        )
        assert config.shared_context == {}
        assert config.parallel is True
        assert config.max_workers == 5
    
    def test_team_config_invalid_team_size_zero(self):
        """测试 team_size=0 抛出异常。"""
        with pytest.raises(ValueError, match="team_size must be >= 1"):
            TeamConfig(team_size=0, roles=[])
    
    def test_team_config_invalid_team_size_too_large(self):
        """测试 team_size > 20 抛出异常。"""
        with pytest.raises(ValueError, match="team_size must be <= 20"):
            TeamConfig(team_size=21, roles=["worker"] * 21)
    
    def test_team_config_roles_mismatch(self):
        """测试 roles 长度与 team_size 不匹配抛出异常。"""
        with pytest.raises(ValueError, match="roles length.*must equal team_size"):
            TeamConfig(team_size=3, roles=["worker1", "worker2"])
    
    def test_team_config_invalid_max_workers(self):
        """测试 max_workers < 1 抛出异常。"""
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            TeamConfig(team_size=2, roles=["w1", "w2"], max_workers=0)


class TestCreateTeam:
    """create_team() 方法测试。"""
    
    def test_create_team_basic(self):
        """测试基本的 Team 创建。"""
        agent = Agent("test-key", "test-model")
        config = TeamConfig(
            team_size=3,
            roles=["researcher", "coder", "reviewer"],
        )
        team = agent.create_team(config)
        
        assert len(team) == 3
        assert len(agent.subagents) == 3
        for i, member in enumerate(team):
            assert isinstance(member, Agent)
            assert member.parent is agent
            assert member.shared_context["team_index"] == i
            assert member.shared_context["team_role"] == config.roles[i]
            assert member.shared_context["team_size"] == 3
    
    def test_create_team_context_lake(self):
        """测试 Context Lake（共享上下文）。"""
        agent = Agent("test-key", "test-model")
        config = TeamConfig(
            team_size=2,
            roles=["worker1", "worker2"],
            shared_context={"project": "autosearch", "version": "1.0"},
        )
        team = agent.create_team(config)
        
        for member in team:
            assert member.shared_context["project"] == "autosearch"
            assert member.shared_context["version"] == "1.0"
    
    def test_create_team_auto_test_disabled(self):
        """测试 Team 成员自动测试被禁用。"""
        agent = Agent("test-key", "test-model")
        agent.auto_test = True
        config = TeamConfig(team_size=2, roles=["w1", "w2"])
        team = agent.create_team(config)
        
        for member in team:
            assert member.auto_test is False
    
    def test_create_team_inherits_parent_config(self):
        """测试 Team 成员继承父 Agent 配置。"""
        agent = Agent("test-key", "test-model", max_history=50, max_tokens=1000)
        config = TeamConfig(team_size=2, roles=["w1", "w2"])
        team = agent.create_team(config)
        
        for member in team:
            assert member.model == "test-model"
            assert member.max_history == 50
            assert member.max_tokens == 1000
    
    def test_create_team_invalid_config_type(self):
        """测试传入非 TeamConfig 类型抛出异常。"""
        agent = Agent("test-key", "test-model")
        with pytest.raises(TypeError, match="config must be TeamConfig instance"):
            agent.create_team({"team_size": 2, "roles": ["w1", "w2"]})


class TestBuildTeamMemberPrompt:
    """_build_team_member_prompt() 方法测试。"""
    
    def test_prompt_includes_role(self):
        """测试 prompt 包含角色信息。"""
        agent = Agent("test-key", "test-model")
        prompt = agent._build_team_member_prompt("researcher", 0, 3)
        
        assert "researcher" in prompt
        assert "Member #1/3" in prompt
        assert "Supervisor" in prompt
        assert "Team 协作" in prompt
    
    def test_prompt_includes_constraints(self):
        """测试 prompt 包含约束条件。"""
        agent = Agent("test-key", "test-model")
        prompt = agent._build_team_member_prompt("coder", 1, 3)
        
        assert "专注于你的角色" in prompt
        assert "输出结构化信息" in prompt
        assert "不要重复其他成员的工作" in prompt


@pytest.mark.asyncio
class TestCoordinateTeam:
    """coordinate_team() 方法测试（异步）。"""
    
    async def test_coordinate_team_parallel_success(self):
        """测试并行执行成功（mock LLM）。"""
        agent = Agent("test-key", "test-model")
        config = TeamConfig(
            team_size=2,
            roles=["worker1", "worker2"],
            parallel=True,
        )
        team = agent.create_team(config)
        
        # Mock prompt_stream 返回简单事件流
        async def mock_prompt_stream(task):
            yield {"type": "text_update", "delta": f"Result: {task}"}
            yield {"type": "agent_end", "usage": Usage(input=10, output=20)}
        
        for member in team:
            member.prompt_stream = mock_prompt_stream
        
        tasks = ["Task 1", "Task 2"]
        result = await agent.coordinate_team(team, tasks)
        
        assert result["success"] is True
        assert len(result["results"]) == 2
        assert result["total_usage"].input == 20
        assert result["total_usage"].output == 40
        assert "Task 1" in result["aggregated_output"]
        assert "Task 2" in result["aggregated_output"]
    
    async def test_coordinate_team_sequential(self):
        """测试顺序执行（mock LLM）。"""
        agent = Agent("test-key", "test-model")
        config = TeamConfig(
            team_size=2,
            roles=["worker1", "worker2"],
            parallel=False,  # 顺序执行
        )
        config.parallel = False  # 确保设置到 shared_context
        team = agent.create_team(config)
        for member in team:
            member.shared_context["parallel"] = False
        
        async def mock_prompt_stream(task):
            yield {"type": "text_update", "delta": f"Result: {task}"}
            yield {"type": "agent_end", "usage": Usage(input=5, output=10)}
        
        for member in team:
            member.prompt_stream = mock_prompt_stream
        
        tasks = ["Task A", "Task B"]
        result = await agent.coordinate_team(team, tasks)
        
        assert result["success"] is True
        assert len(result["results"]) == 2
    
    async def test_coordinate_team_task_count_mismatch(self):
        """测试任务数量与 Team 大小不匹配。"""
        agent = Agent("test-key", "test-model")
        config = TeamConfig(team_size=2, roles=["w1", "w2"])
        team = agent.create_team(config)
        
        tasks = ["Task 1"]  # 只有 1 个任务，但有 2 个成员
        result = await agent.coordinate_team(team, tasks)
        
        assert result["success"] is False
        assert "must match tasks length" in result["error"]
    
    async def test_coordinate_team_member_exception(self):
        """测试成员执行抛出异常。"""
        agent = Agent("test-key", "test-model")
        config = TeamConfig(team_size=2, roles=["w1", "w2"])
        team = agent.create_team(config)
        
        async def mock_prompt_stream_error(task):
            yield {"type": "error", "message": "API error"}
        
        team[0].prompt_stream = mock_prompt_stream_error
        
        async def mock_prompt_stream_ok(task):
            yield {"type": "text_update", "delta": "OK"}
            yield {"type": "agent_end", "usage": Usage(input=1, output=1)}
        
        team[1].prompt_stream = mock_prompt_stream_ok
        
        tasks = ["Task 1", "Task 2"]
        result = await agent.coordinate_team(team, tasks)
        
        # 应该继续执行其他成员，即使一个失败
        assert result["success"] is True
        assert result["results"][0]["success"] is False
        assert result["results"][1]["success"] is True


class TestAggregateTeamResults:
    """_aggregate_team_results() 方法测试。"""
    
    def test_aggregate_results_all_success(self):
        """测试聚合全部成功的结果。"""
        agent = Agent("test-key", "test-model")
        results = [
            {
                "success": True,
                "index": 0,
                "role": "researcher",
                "output": "Research findings here",
                "usage": Usage(input=10, output=20),
            },
            {
                "success": True,
                "index": 1,
                "role": "coder",
                "output": "Code implementation here",
                "usage": Usage(input=15, output=25),
            },
        ]
        
        output = agent._aggregate_team_results(results)
        
        assert "Team 协作结果" in output
        assert "2/2 个成员成功完成任务" in output
        assert "researcher" in output
        assert "coder" in output
        assert "Research findings here" in output
        assert "Code implementation here" in output
    
    def test_aggregate_results_with_failure(self):
        """测试聚合包含失败的结果。"""
        agent = Agent("test-key", "test-model")
        results = [
            {
                "success": True,
                "index": 0,
                "role": "worker1",
                "output": "Success output",
                "usage": Usage(),
            },
            {
                "success": False,
                "index": 1,
                "role": "worker2",
                "output": "",
                "error": "API timeout",
                "usage": Usage(),
            },
        ]
        
        output = agent._aggregate_team_results(results)
        
        assert "1/2 个成员成功完成任务" in output
        assert "✅" in output
        assert "❌" in output
        assert "API timeout" in output
