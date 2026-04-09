"""tests/test_session.py — 对话持久化（/save、/load）测试"""

import json
import os
import pytest
from unittest.mock import patch
from src.agent import Agent
from src.models import Usage


class TestExportSession:
    """测试 Agent.export_session() 方法"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            return a

    def test_export_empty_session(self, agent):
        """空会话导出应包含必要字段"""
        data = agent.export_session()
        assert data["model"] == "test-model"
        assert data["conversation_history"] == []
        assert "version" in data
        assert "timestamp" in data

    def test_export_with_history(self, agent):
        """有对话历史时，导出应包含完整历史"""
        agent.conversation_history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        data = agent.export_session()
        assert len(data["conversation_history"]) == 2
        assert data["conversation_history"][0]["role"] == "user"
        assert data["conversation_history"][1]["content"] == "hi there"

    def test_export_is_json_serializable(self, agent):
        """导出结果应可以直接 JSON 序列化"""
        agent.conversation_history = [
            {"role": "user", "content": "测试中文"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "test.txt"}'}}
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"success": true}'},
        ]
        data = agent.export_session()
        # 不应抛异常
        json_str = json.dumps(data, ensure_ascii=False)
        assert len(json_str) > 0

    def test_export_contains_version(self, agent):
        """导出应包含 SimpleAgent 版本号"""
        from src import __version__
        data = agent.export_session()
        assert data["version"] == __version__


class TestImportSession:
    """测试 Agent.import_session() 方法"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="original-model")
            return a

    def test_import_restores_history(self, agent):
        """导入应恢复对话历史"""
        data = {
            "model": "imported-model",
            "conversation_history": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
            "version": "0.18.0",
            "timestamp": "2026-04-03T08:00:00",
        }
        agent.import_session(data)
        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0]["content"] == "hello"

    def test_import_restores_model(self, agent):
        """导入应恢复模型名称"""
        data = {
            "model": "restored-model",
            "conversation_history": [],
            "version": "0.18.0",
            "timestamp": "2026-04-03T08:00:00",
        }
        agent.import_session(data)
        assert agent.model == "restored-model"

    def test_import_clears_old_history(self, agent):
        """导入新会话应替换（而非追加）旧历史"""
        agent.conversation_history = [
            {"role": "user", "content": "old message"},
        ]
        data = {
            "model": "new-model",
            "conversation_history": [
                {"role": "user", "content": "new message"},
            ],
            "version": "0.18.0",
            "timestamp": "2026-04-03T08:00:00",
        }
        agent.import_session(data)
        assert len(agent.conversation_history) == 1
        assert agent.conversation_history[0]["content"] == "new message"

    def test_import_missing_model_keeps_current(self, agent):
        """如果导入数据缺少 model 字段，保持当前模型不变"""
        data = {
            "conversation_history": [
                {"role": "user", "content": "hello"},
            ],
            "version": "0.18.0",
            "timestamp": "2026-04-03T08:00:00",
        }
        agent.import_session(data)
        assert agent.model == "original-model"

    def test_import_missing_history_sets_empty(self, agent):
        """如果导入数据缺少 conversation_history，设为空列表"""
        agent.conversation_history = [{"role": "user", "content": "old"}]
        data = {
            "model": "some-model",
            "version": "0.18.0",
            "timestamp": "2026-04-03T08:00:00",
        }
        agent.import_session(data)
        assert agent.conversation_history == []

    def test_roundtrip_export_import(self, agent):
        """export → import 应完美恢复状态"""
        agent.conversation_history = [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
        agent.model = "roundtrip-model"
        data = agent.export_session()

        # 创建新的 agent 并导入
        with patch("src.agent.OpenAI"):
            agent2 = Agent(api_key="test-key", model="different-model")
            agent2.import_session(data)

        assert agent2.model == "roundtrip-model"
        assert len(agent2.conversation_history) == 2
        assert agent2.conversation_history[0]["content"] == "question"
        assert agent2.conversation_history[1]["content"] == "answer"


class TestExportImportSystemPromptOverride:
    """测试 system_prompt_override 的导出/导入（#134）"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            return a

    def test_export_without_override_has_no_key(self, agent):
        """未设置 system_prompt_override 时，导出不应包含该字段"""
        data = agent.export_session()
        assert "system_prompt_override" not in data

    def test_export_with_override_includes_it(self, agent):
        """设置了 system_prompt_override 后，导出应包含该字段"""
        agent.with_system_prompt("请专注于安全审计")
        data = agent.export_session()
        assert data["system_prompt_override"] == "请专注于安全审计"

    def test_import_restores_override(self, agent):
        """导入含 system_prompt_override 的数据应恢复该字段"""
        data = {
            "model": "test-model",
            "conversation_history": [],
            "system_prompt_override": "自定义提示词",
        }
        agent.import_session(data)
        assert agent.system_prompt_override == "自定义提示词"

    def test_import_without_override_resets_to_none(self, agent):
        """导入不含 system_prompt_override 的旧数据，应重置为 None"""
        agent.system_prompt_override = None
        data = {
            "model": "test-model",
            "conversation_history": [],
        }
        agent.import_session(data)
        assert agent.system_prompt_override is None

    def test_import_without_override_clears_existing_override(self, agent):
        """导入不含 system_prompt_override 的数据时，已有的 override 应被清除（#172）"""
        agent.system_prompt_override = "旧的自定义提示词"
        data = {
            "model": "test-model",
            "conversation_history": [],
        }
        agent.import_session(data)
        assert agent.system_prompt_override is None, \
            "system_prompt_override 应被重置为 None，防止旧值泄漏到新会话"

    def test_roundtrip_with_override(self, agent):
        """export → import 应完美恢复 system_prompt_override"""
        agent.with_system_prompt("请专注于代码重构")
        agent.conversation_history = [
            {"role": "user", "content": "hello"},
        ]
        data = agent.export_session()

        with patch("src.agent.OpenAI"):
            agent2 = Agent(api_key="test-key", model="other")
            agent2.import_session(data)

        assert agent2.system_prompt_override == "请专注于代码重构"
        assert agent2.model == "test-model"
        assert len(agent2.conversation_history) == 1

    def test_save_load_roundtrip_with_override(self, agent, tmp_path):
        """save → load 文件持久化应完美恢复 system_prompt_override"""
        agent.with_system_prompt("安全审计模式")
        agent.conversation_history = [
            {"role": "user", "content": "test"},
        ]
        filepath = str(tmp_path / "override_session.json")
        agent.save_session(filepath)

        with patch("src.agent.OpenAI"):
            agent2 = Agent(api_key="test-key", model="other")
            result = agent2.load_session(filepath)

        assert result["success"] is True
        assert agent2.system_prompt_override == "安全审计模式"


class TestSaveLoadSession:
    """测试 Agent.save_session() 和 Agent.load_session() 文件 I/O"""

    @pytest.fixture
    def agent(self):
        with patch("src.agent.OpenAI"):
            a = Agent(api_key="test-key", model="test-model")
            return a

    def test_save_creates_file(self, agent, tmp_path):
        """save_session 应创建 JSON 文件"""
        filepath = str(tmp_path / "test_session.json")
        result = agent.save_session(filepath)
        assert result["success"] is True
        assert os.path.isfile(filepath)

    def test_save_file_is_valid_json(self, agent, tmp_path):
        """保存的文件应是有效的 JSON"""
        agent.conversation_history = [
            {"role": "user", "content": "hello"},
        ]
        filepath = str(tmp_path / "valid.json")
        agent.save_session(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["model"] == "test-model"
        assert len(data["conversation_history"]) == 1

    def test_save_creates_parent_directory(self, agent, tmp_path):
        """如果父目录不存在，save_session 应自动创建"""
        filepath = str(tmp_path / "subdir" / "nested" / "session.json")
        result = agent.save_session(filepath)
        assert result["success"] is True
        assert os.path.isfile(filepath)

    def test_save_returns_filepath(self, agent, tmp_path):
        """save_session 返回值应包含保存的文件路径"""
        filepath = str(tmp_path / "session.json")
        result = agent.save_session(filepath)
        assert result["path"] == filepath

    def test_load_restores_session(self, agent, tmp_path):
        """load_session 应从文件恢复会话"""
        agent.conversation_history = [
            {"role": "user", "content": "saved message"},
        ]
        agent.model = "saved-model"
        filepath = str(tmp_path / "load_test.json")
        agent.save_session(filepath)

        # 创建新 agent 并加载
        with patch("src.agent.OpenAI"):
            agent2 = Agent(api_key="test-key", model="different-model")
            result = agent2.load_session(filepath)

        assert result["success"] is True
        assert agent2.model == "saved-model"
        assert len(agent2.conversation_history) == 1
        assert agent2.conversation_history[0]["content"] == "saved message"

    def test_load_nonexistent_file_returns_error(self, agent, tmp_path):
        """加载不存在的文件应返回错误"""
        filepath = str(tmp_path / "nonexistent.json")
        result = agent.load_session(filepath)
        assert result["success"] is False
        assert "error" in result

    def test_load_invalid_json_returns_error(self, agent, tmp_path):
        """加载无效 JSON 文件应返回错误"""
        filepath = str(tmp_path / "invalid.json")
        with open(filepath, "w") as f:
            f.write("not valid json {{{")
        result = agent.load_session(filepath)
        assert result["success"] is False
        assert "error" in result

    def test_load_returns_metadata(self, agent, tmp_path):
        """load_session 返回值应包含加载的元信息"""
        agent.conversation_history = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ]
        filepath = str(tmp_path / "meta_test.json")
        agent.save_session(filepath)

        with patch("src.agent.OpenAI"):
            agent2 = Agent(api_key="test-key", model="other")
            result = agent2.load_session(filepath)

        assert result["success"] is True
        assert result["model"] == "test-model"
        assert result["message_count"] == 2

    def test_import_with_archival_memory_refreshes_system_prompt(self, agent, tmp_path):
        """导入含 archival memory 的会话后，system prompt 应包含 archival 内容（#145）"""
        # 使用临时目录隔离 archival 存储，避免跨测试污染
        agent.memory._archival_dir = str(tmp_path / "archival")
        agent.memory._archival_path = str(tmp_path / "archival" / "archival.jsonl")
        agent.memory.archival = []  # 清理 __init__ 中 load_archival 加载的脏数据

        # 导出一个含 archival memory 但无 system_prompt_override 的会话
        agent.memory.add_archival("important-fact-12345", source="test")
        data = agent.export_session()
        assert "system_prompt_override" not in data
        assert len(data["memory"]["archival"]) == 1

        # 创建新 agent（无 archival memory），导入
        with patch("src.agent.OpenAI"):
            agent2 = Agent(api_key="test-key", model="other")
            # 也隔离 agent2 的 archival 目录
            agent2.memory._archival_dir = str(tmp_path / "archival2")
            agent2.memory._archival_path = str(tmp_path / "archival2" / "archival.jsonl")
            agent2.memory.archival = []  # 确保干净状态
            assert len(agent2.memory.archival) == 0
            agent2.import_session(data)

        # archival memory 应被恢复
        assert len(agent2.memory.archival) == 1
        assert agent2.memory.archival[0].content == "important-fact-12345"
        # system prompt 应包含 archival 内容
        assert "important-fact-12345" in agent2.system_prompt

    def test_save_load_roundtrip_with_tool_calls(self, agent, tmp_path):
        """包含 tool_calls 的复杂对话历史应能完整保存和恢复"""
        agent.conversation_history = [
            {"role": "user", "content": "read file"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "test.txt"}'}}
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"success": true, "content": "hello"}'},
            {"role": "assistant", "content": "文件内容是 hello"},
        ]
        filepath = str(tmp_path / "complex.json")
        agent.save_session(filepath)

        with patch("src.agent.OpenAI"):
            agent2 = Agent(api_key="test-key", model="other")
            agent2.load_session(filepath)

        assert len(agent2.conversation_history) == 4
        assert agent2.conversation_history[1]["tool_calls"][0]["id"] == "c1"
        assert agent2.conversation_history[2]["role"] == "tool"

    def test_save_session_atomic_write_preserves_existing_on_error(self, agent, tmp_path):
        """save_session 使用原子写入：如果序列化失败，已有文件不应被破坏"""
        filepath = str(tmp_path / "atomic_test.json")
        # 首次保存成功
        agent.conversation_history = [{"role": "user", "content": "original data"}]
        result = agent.save_session(filepath)
        assert result["success"] is True

        # 读取原始文件内容
        with open(filepath, "r", encoding="utf-8") as f:
            original_content = f.read()
        assert "original data" in original_content

        # 制造一个无法 JSON 序列化的对象来使第二次保存失败
        agent.conversation_history = [{"role": "user", "content": "new data"}]
        import json as _json
        original_dumps = _json.dumps

        def failing_dump(obj, f, **kwargs):
            raise IOError("模拟写入失败")

        with patch("json.dump", side_effect=failing_dump):
            result2 = agent.save_session(filepath)

        assert result2["success"] is False

        # 验证原始文件未被破坏
        with open(filepath, "r", encoding="utf-8") as f:
            preserved_content = f.read()
        assert preserved_content == original_content, "原子写入失败后，原始文件应保持不变"

    def test_save_session_no_leftover_tmp_files(self, agent, tmp_path):
        """save_session 成功后不应留下 .tmp 文件"""
        filepath = str(tmp_path / "clean_test.json")
        agent.conversation_history = [{"role": "user", "content": "test"}]
        agent.save_session(filepath)

        tmp_files = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
        assert tmp_files == [], f"不应有残留的临时文件，但发现：{tmp_files}"

    def test_import_session_clears_undo_stack(self, agent):
        """import_session 应清空 undo_stack，防止旧会话的 undo 泄漏到新会话（#173）"""
        # 模拟会话 A 中修改了文件
        agent.tools.record_undo("/tmp/old_session_file.py", "old content")
        assert len(agent.tools._undo_stack) == 1

        # 加载会话 B
        data = {
            "model": "new-model",
            "conversation_history": [{"role": "user", "content": "new session"}],
        }
        agent.import_session(data)

        # undo_stack 应被清空，/undo 不应恢复会话 A 的文件
        assert agent.tools._undo_stack == [], \
            "import_session 后 undo_stack 应为空，防止 /undo 意外恢复上一个会话的文件更改"
