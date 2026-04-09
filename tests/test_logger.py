"""SessionLogger 会话日志测试。"""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.logger import SessionLogger


class TestSessionLoggerInit:
    """SessionLogger 初始化测试。"""

    def test_creates_log_directory(self, tmp_path):
        """日志目录不存在时自动创建。"""
        log_dir = tmp_path / "logs"
        logger = SessionLogger(log_dir=str(log_dir))
        assert log_dir.is_dir()
        logger.close()

    def test_creates_log_file(self, tmp_path):
        """初始化时创建 JSONL 日志文件。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        assert os.path.isfile(logger.filepath)
        logger.close()

    def test_log_filename_contains_timestamp(self, tmp_path):
        """日志文件名包含时间戳。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        basename = os.path.basename(logger.filepath)
        assert basename.startswith("transcript-")
        assert basename.endswith(".jsonl")
        logger.close()

    def test_log_filepath_is_absolute(self, tmp_path):
        """filepath 是绝对路径或指向实际文件。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        assert os.path.exists(logger.filepath)
        logger.close()

    def test_writes_session_start_event(self, tmp_path):
        """初始化时写入 session_start 事件。"""
        logger = SessionLogger(log_dir=str(tmp_path), model="test-model")
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) >= 1
        first = json.loads(lines[0])
        assert first["type"] == "session_start"
        assert first["model"] == "test-model"
        assert "timestamp" in first

    def test_default_log_dir(self, monkeypatch, tmp_path):
        """默认日志目录为 'logs'。"""
        monkeypatch.chdir(tmp_path)
        logger = SessionLogger()
        assert "logs" in logger.filepath
        logger.close()


class TestSessionLoggerLog:
    """SessionLogger.log() 方法测试。"""

    def test_log_appends_jsonl(self, tmp_path):
        """每次 log 追加一行 JSON。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.log("user_input", {"content": "hello"})
        logger.log("agent_response", {"content": "hi"})
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # session_start + 2 log + session_end
        assert len(lines) >= 3  # at least start + 2 logs

    def test_log_includes_timestamp(self, tmp_path):
        """每条日志都有时间戳。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.log("user_input", {"content": "test"})
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # 第二行（第一行是 session_start）
        entry = json.loads(lines[1])
        assert "timestamp" in entry
        # 验证时间戳格式可被 ISO 解析
        datetime.fromisoformat(entry["timestamp"])

    def test_log_includes_type(self, tmp_path):
        """每条日志都有类型。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.log("tool_call", {"tool": "read_file", "args": {"path": "test.py"}})
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entry = json.loads(lines[1])
        assert entry["type"] == "tool_call"

    def test_log_preserves_data(self, tmp_path):
        """日志保留原始数据。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        data = {"content": "hello world", "extra": [1, 2, 3]}
        logger.log("custom", data)
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entry = json.loads(lines[1])
        assert entry["content"] == "hello world"
        assert entry["extra"] == [1, 2, 3]

    def test_log_empty_data(self, tmp_path):
        """空数据日志正常记录。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.log("empty_event")
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entry = json.loads(lines[1])
        assert entry["type"] == "empty_event"

    def test_log_unicode_content(self, tmp_path):
        """Unicode 内容正确保存。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.log("user_input", {"content": "你好世界 🌍"})
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entry = json.loads(lines[1])
        assert entry["content"] == "你好世界 🌍"


class TestSessionLoggerClose:
    """SessionLogger.close() 方法测试。"""

    def test_close_writes_session_end(self, tmp_path):
        """关闭时写入 session_end 事件。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.log("user_input", {"content": "test"})
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last = json.loads(lines[-1])
        assert last["type"] == "session_end"
        assert "timestamp" in last

    def test_close_idempotent(self, tmp_path):
        """多次 close 不报错。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.close()
        logger.close()  # 不应抛异常

    def test_log_after_close_no_crash(self, tmp_path):
        """close 后 log 不崩溃（静默忽略）。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.close()
        # 不应抛异常
        logger.log("after_close", {"content": "should be ignored"})

    def test_close_includes_message_count(self, tmp_path):
        """session_end 包含消息计数。"""
        logger = SessionLogger(log_dir=str(tmp_path))
        logger.log("user_input", {"content": "q1"})
        logger.log("agent_response", {"content": "a1"})
        logger.log("user_input", {"content": "q2"})
        logger.close()
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last = json.loads(lines[-1])
        assert last["type"] == "session_end"
        assert last["event_count"] == 3  # 不含 session_start 和 session_end


class TestSessionLoggerContextManager:
    """SessionLogger 上下文管理器测试。"""

    def test_context_manager(self, tmp_path):
        """with 语句自动 close。"""
        with SessionLogger(log_dir=str(tmp_path)) as logger:
            logger.log("user_input", {"content": "test"})
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        last = json.loads(lines[-1])
        assert last["type"] == "session_end"

    def test_context_manager_returns_logger(self, tmp_path):
        """with 语句返回 logger 实例。"""
        with SessionLogger(log_dir=str(tmp_path)) as logger:
            assert isinstance(logger, SessionLogger)


class TestSessionLoggerIntegration:
    """集成测试。"""

    def test_full_session_roundtrip(self, tmp_path):
        """完整会话周期：start → logs → end。"""
        with SessionLogger(log_dir=str(tmp_path), model="gpt-4") as logger:
            logger.log("user_input", {"content": "请读取 test.py"})
            logger.log("tool_call", {"tool": "read_file", "args": {"path": "test.py"}})
            logger.log("tool_result", {"tool": "read_file", "success": True, "content": "..."})
            logger.log("agent_response", {"content": "文件内容如下..."})
            logger.log("user_input", {"content": "谢谢"})
            logger.log("agent_response", {"content": "不客气"})

        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # session_start + 6 events + session_end = 8 lines
        assert len(lines) == 8
        
        events = [json.loads(line) for line in lines]
        assert events[0]["type"] == "session_start"
        assert events[0]["model"] == "gpt-4"
        assert events[1]["type"] == "user_input"
        assert events[2]["type"] == "tool_call"
        assert events[3]["type"] == "tool_result"
        assert events[4]["type"] == "agent_response"
        assert events[5]["type"] == "user_input"
        assert events[6]["type"] == "agent_response"
        assert events[7]["type"] == "session_end"
        assert events[7]["event_count"] == 6

    def test_large_content_handling(self, tmp_path):
        """大内容不截断（日志保留完整内容）。"""
        large_content = "x" * 100000
        with SessionLogger(log_dir=str(tmp_path)) as logger:
            logger.log("user_input", {"content": large_content})
        
        with open(logger.filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entry = json.loads(lines[1])
        assert len(entry["content"]) == 100000


class TestLoadTranscript:
    """load_transcript() 测试。"""

    def test_load_basic_transcript(self, tmp_path):
        """加载包含用户输入的日志文件。"""
        from src.logger import load_transcript
        f = tmp_path / "test.jsonl"
        f.write_text(
            '{"type": "session_start", "model": "gpt-4"}\n'
            '{"type": "user_input", "content": "hello"}\n'
            '{"type": "agent_response", "content": "hi"}\n'
            '{"type": "user_input", "content": "bye"}\n'
            '{"type": "session_end"}\n',
            encoding="utf-8",
        )
        result = load_transcript(str(f))
        assert result["success"] is True
        assert result["inputs"] == ["hello", "bye"]
        assert result["model"] == "gpt-4"

    def test_load_empty_inputs(self, tmp_path):
        """日志中无用户输入。"""
        from src.logger import load_transcript
        f = tmp_path / "empty.jsonl"
        f.write_text(
            '{"type": "session_start", "model": "test"}\n'
            '{"type": "session_end"}\n',
            encoding="utf-8",
        )
        result = load_transcript(str(f))
        assert result["success"] is True
        assert result["inputs"] == []

    def test_load_nonexistent_file(self, tmp_path):
        """文件不存在。"""
        from src.logger import load_transcript
        result = load_transcript(str(tmp_path / "nope.jsonl"))
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_load_corrupt_lines_skipped(self, tmp_path):
        """损坏的行被跳过，不影响其他行。"""
        from src.logger import load_transcript
        f = tmp_path / "corrupt.jsonl"
        f.write_text(
            '{"type": "session_start", "model": "m"}\n'
            'this is not json\n'
            '{"type": "user_input", "content": "valid"}\n',
            encoding="utf-8",
        )
        result = load_transcript(str(f))
        assert result["success"] is True
        assert result["inputs"] == ["valid"]

    def test_load_empty_content_skipped(self, tmp_path):
        """user_input 的 content 为空时跳过。"""
        from src.logger import load_transcript
        f = tmp_path / "empty_content.jsonl"
        f.write_text(
            '{"type": "session_start", "model": "m"}\n'
            '{"type": "user_input", "content": ""}\n'
            '{"type": "user_input", "content": "real"}\n',
            encoding="utf-8",
        )
        result = load_transcript(str(f))
        assert result["inputs"] == ["real"]

    def test_load_real_session_logger_output(self, tmp_path):
        """从 SessionLogger 生成的真实日志文件加载。"""
        from src.logger import load_transcript
        with SessionLogger(log_dir=str(tmp_path), model="test-model") as logger:
            logger.log("user_input", {"content": "first question"})
            logger.log("agent_response", {"content": "answer"})
            logger.log("user_input", {"content": "second question"})
        result = load_transcript(logger.filepath)
        assert result["success"] is True
        assert result["inputs"] == ["first question", "second question"]
        assert result["model"] == "test-model"
