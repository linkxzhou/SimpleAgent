"""测试 memory 模块 — 三层记忆管理。"""

import json
import os
import tempfile
import pytest

from src.memory import WorkingSummary, ArchivalEntry, MemoryManager


# === WorkingSummary 测试 ===

class TestWorkingSummary:
    def test_empty_by_default(self):
        ws = WorkingSummary()
        assert ws.is_empty()

    def test_not_empty_with_intent(self):
        ws = WorkingSummary(intent="修复 bug")
        assert not ws.is_empty()

    def test_not_empty_with_changes(self):
        ws = WorkingSummary(changes="修改了 agent.py")
        assert not ws.is_empty()

    def test_to_context_message_empty(self):
        ws = WorkingSummary()
        assert ws.to_context_message() is None

    def test_to_context_message_with_content(self):
        ws = WorkingSummary(
            intent="优化上下文压缩",
            changes="新增 memory.py 模块",
            decisions="采用 Anchored Iterative Summarization",
            next_steps="编写测试"
        )
        msg = ws.to_context_message()
        assert msg is not None
        assert msg["role"] == "user"
        assert "会话摘要" in msg["content"]
        assert "目标" in msg["content"]
        assert "优化上下文压缩" in msg["content"]
        assert "已完成的操作" in msg["content"]
        assert "memory.py" in msg["content"]
        assert "关键决策" in msg["content"]
        assert "后续步骤" in msg["content"]

    def test_to_context_message_partial(self):
        ws = WorkingSummary(intent="修复 bug")
        msg = ws.to_context_message()
        assert msg is not None
        assert "目标" in msg["content"]
        assert "修复 bug" in msg["content"]
        # 空字段不应出现
        assert "已完成的操作" not in msg["content"]

    def test_to_dict_roundtrip(self):
        ws = WorkingSummary(
            intent="测试",
            changes="改了文件",
            decisions="用方案 A",
            next_steps="写测试",
            merged_message_count=5,
        )
        d = ws.to_dict()
        ws2 = WorkingSummary.from_dict(d)
        assert ws2.intent == ws.intent
        assert ws2.changes == ws.changes
        assert ws2.decisions == ws.decisions
        assert ws2.next_steps == ws.next_steps
        assert ws2.merged_message_count == 5

    def test_from_dict_missing_fields(self):
        ws = WorkingSummary.from_dict({})
        assert ws.is_empty()
        assert ws.merged_message_count == 0

    def test_from_dict_partial(self):
        ws = WorkingSummary.from_dict({"intent": "hello"})
        assert ws.intent == "hello"
        assert ws.changes == ""


# === ArchivalEntry 测试 ===

class TestArchivalEntry:
    def test_auto_timestamp(self):
        entry = ArchivalEntry(content="重要事实")
        assert entry.timestamp  # 自动填充
        assert entry.content == "重要事实"

    def test_custom_timestamp(self):
        entry = ArchivalEntry(content="事实", timestamp="2025-01-01T00:00:00Z")
        assert entry.timestamp == "2025-01-01T00:00:00Z"

    def test_source_field(self):
        entry = ArchivalEntry(content="事实", source="第 42 次")
        assert entry.source == "第 42 次"


# === MemoryManager 测试 ===

class TestMemoryManager:
    def test_init_defaults(self):
        mm = MemoryManager()
        assert mm.working_summary.is_empty()
        assert mm.archival == []

    def test_add_archival(self):
        mm = MemoryManager()
        entry = mm.add_archival("Python 3.12 新特性", source="调研")
        assert entry.content == "Python 3.12 新特性"
        assert len(mm.archival) == 1

    def test_add_archival_max_limit(self):
        mm = MemoryManager()
        mm.MAX_ARCHIVAL_ENTRIES = 5
        for i in range(10):
            mm.add_archival(f"事实 {i}")
        assert len(mm.archival) == 5
        # 应保留最新的 5 条
        assert mm.archival[0].content == "事实 5"
        assert mm.archival[-1].content == "事实 9"

    def test_get_archival_context_empty(self):
        mm = MemoryManager()
        assert mm.get_archival_context() == ""

    def test_get_archival_context(self):
        mm = MemoryManager()
        mm.add_archival("事实 A")
        mm.add_archival("事实 B")
        ctx = mm.get_archival_context()
        assert "事实 A" in ctx
        assert "事实 B" in ctx

    def test_get_archival_context_truncation(self):
        mm = MemoryManager()
        mm.MAX_ARCHIVAL_CONTEXT_CHARS = 50
        for i in range(100):
            mm.add_archival(f"这是一个很长的事实描述 {i}")
        ctx = mm.get_archival_context()
        assert len(ctx) <= 100  # 大致范围内（含行符）


# === 持久化测试 ===

class TestArchivalPersistence:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(archival_dir=tmpdir)
            mm.add_archival("持久化事实 1")
            mm.add_archival("持久化事实 2")
            assert mm.save_archival()

            mm2 = MemoryManager(archival_dir=tmpdir)
            count = mm2.load_archival()
            assert count == 2
            assert mm2.archival[0].content == "持久化事实 1"
            assert mm2.archival[1].content == "持久化事实 2"

    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(archival_dir=tmpdir)
            count = mm.load_archival()
            assert count == 0

    def test_save_creates_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "sub", "dir")
            mm = MemoryManager(archival_dir=nested)
            mm.add_archival("test")
            assert mm.save_archival()
            assert os.path.isfile(os.path.join(nested, "archival.jsonl"))


# === parse_structured_summary 测试 ===

class TestParseStructuredSummary:
    def test_full_parse(self):
        text = """## 目标
优化上下文压缩

## 已完成的操作
新增了 memory.py 模块

## 关键决策
采用 Anchored Iterative Summarization

## 后续步骤
编写测试并验证"""
        ws = MemoryManager.parse_structured_summary(text)
        assert ws.intent == "优化上下文压缩"
        assert "memory.py" in ws.changes
        assert "Anchored" in ws.decisions
        assert "测试" in ws.next_steps

    def test_partial_parse(self):
        text = """## 目标
修复 bug

## 已完成的操作
改了三个文件"""
        ws = MemoryManager.parse_structured_summary(text)
        assert ws.intent == "修复 bug"
        assert "三个文件" in ws.changes
        assert ws.decisions == ""
        assert ws.next_steps == ""

    def test_fallback_no_headers(self):
        text = "这是一段没有结构的纯文本摘要"
        ws = MemoryManager.parse_structured_summary(text)
        # Fallback: 放入 intent
        assert ws.intent == text
        assert ws.changes == ""

    def test_fallback_truncation(self):
        text = "x" * 1000
        ws = MemoryManager.parse_structured_summary(text)
        assert len(ws.intent) <= 600

    def test_chinese_headers(self):
        text = """## 目标
完成 Issue #4

## 已完成的操作
实现了记忆分层

## 关键决策
使用结构化摘要

## 后续步骤
提交代码"""
        ws = MemoryManager.parse_structured_summary(text)
        assert ws.intent == "完成 Issue #4"
        assert "记忆分层" in ws.changes
        assert "结构化摘要" in ws.decisions
        assert "提交代码" in ws.next_steps


# === build_compaction_prompt 测试 ===

class TestBuildCompactionPrompt:
    def test_first_compaction_prompt(self):
        mm = MemoryManager()
        messages = [
            {"role": "user", "content": "帮我修复 bug"},
            {"role": "assistant", "content": "好的"},
        ]
        prompt = mm.build_compaction_prompt(messages)
        assert len(prompt) >= 3  # system + messages + user
        assert prompt[0]["role"] == "system"
        assert "结构化摘要" in prompt[0]["content"]
        assert "目标" in prompt[0]["content"]
        assert "已完成的操作" in prompt[0]["content"]

    def test_incremental_compaction_prompt(self):
        mm = MemoryManager()
        mm.working_summary = WorkingSummary(
            intent="修复 bug",
            changes="改了 agent.py",
        )
        messages = [
            {"role": "user", "content": "再修改一下 cli.py"},
            {"role": "assistant", "content": "完成"},
        ]
        prompt = mm.build_compaction_prompt(messages)
        assert prompt[0]["role"] == "system"
        # 增量合并 prompt 应包含已有摘要
        assert "修复 bug" in prompt[0]["content"]
        assert "agent.py" in prompt[0]["content"]
        assert "合并" in prompt[0]["content"]


# === compact_with_summary 测试 ===

class TestCompactWithSummary:
    def test_compact_basic(self):
        mm = MemoryManager()
        history = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        summary = WorkingSummary(intent="测试", changes="修改了文件")
        result = mm.compact_with_summary(history, summary, keep_recent=5)
        assert result["compacted"]
        assert result["removed"] == 15
        assert result["kept"] == 5
        new_hist = result["new_history"]
        assert len(new_hist) == 6  # 1 summary + 5 recent
        assert "会话摘要" in new_hist[0]["content"]

    def test_compact_too_short(self):
        mm = MemoryManager()
        history = [{"role": "user", "content": "msg"}]
        summary = WorkingSummary(intent="测试")
        result = mm.compact_with_summary(history, summary, keep_recent=5)
        assert not result["compacted"]

    def test_compact_empty_summary(self):
        mm = MemoryManager()
        history = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        summary = WorkingSummary()  # empty
        result = mm.compact_with_summary(history, summary, keep_recent=5)
        assert result["compacted"]
        new_hist = result["new_history"]
        # Empty summary → 无摘要消息，只有 recent
        assert len(new_hist) == 5


# === update_working_summary 测试 ===

class TestUpdateWorkingSummary:
    def test_update_increments_count(self):
        mm = MemoryManager()
        mm.working_summary.merged_message_count = 10
        new_ws = WorkingSummary(intent="更新后")
        mm.update_working_summary(new_ws, 5)
        assert mm.working_summary.intent == "更新后"
        assert mm.working_summary.merged_message_count == 15

    def test_update_from_zero(self):
        mm = MemoryManager()
        new_ws = WorkingSummary(intent="首次")
        mm.update_working_summary(new_ws, 8)
        assert mm.working_summary.merged_message_count == 8


# === export/import 状态测试 ===

class TestMemoryState:
    def test_export_import_roundtrip(self):
        mm = MemoryManager()
        mm.working_summary = WorkingSummary(
            intent="测试", changes="改了文件", merged_message_count=10
        )
        mm.add_archival("事实 1")
        state = mm.export_state()
        
        mm2 = MemoryManager()
        mm2.import_state(state)
        assert mm2.working_summary.intent == "测试"
        assert mm2.working_summary.changes == "改了文件"
        assert mm2.working_summary.merged_message_count == 10

    def test_import_empty_state(self):
        mm = MemoryManager()
        mm.import_state({})
        assert mm.working_summary.is_empty()


# === archival memory 完整链路测试（第 50 次新增） ===

class TestExportImportArchival:
    """验证 export_state/import_state 保存和恢复 archival memory。"""

    def test_export_includes_archival_data(self):
        mm = MemoryManager()
        mm.add_archival("事实 A", source="s1")
        mm.add_archival("事实 B", source="s2")
        state = mm.export_state()
        assert "archival" in state
        assert len(state["archival"]) == 2
        assert state["archival"][0]["content"] == "事实 A"
        assert state["archival"][1]["source"] == "s2"

    def test_export_empty_archival(self):
        mm = MemoryManager()
        state = mm.export_state()
        assert state["archival"] == []

    def test_import_restores_archival(self):
        mm = MemoryManager()
        mm.add_archival("事实 1")
        mm.add_archival("事实 2")
        state = mm.export_state()

        mm2 = MemoryManager()
        mm2.import_state(state)
        assert len(mm2.archival) == 2
        assert mm2.archival[0].content == "事实 1"
        assert mm2.archival[1].content == "事实 2"

    def test_import_resets_archival_when_key_missing(self):
        """import_state 缺少 archival 字段时，应重置 archival 防止旧数据泄漏。"""
        mm = MemoryManager()
        mm.add_archival("existing")
        mm.import_state({"working_summary": {}})
        assert len(mm.archival) == 0  # 旧 archival 被重置

    def test_import_empty_dict_resets_working_summary(self):
        """#171: import_state({}) 应重置 stale working_summary。"""
        mm = MemoryManager()
        mm.working_summary = WorkingSummary(
            intent="旧目标", changes="旧变更", decisions="旧决策", next_steps="旧步骤"
        )
        mm.import_state({})
        assert mm.working_summary.is_empty()

    def test_import_none_working_summary_resets(self):
        """#171: working_summary 为 None 时应重置，而非保留旧值。"""
        mm = MemoryManager()
        mm.working_summary = WorkingSummary(intent="stale")
        mm.import_state({"working_summary": None, "archival": []})
        assert mm.working_summary.is_empty()

    def test_import_resets_both_when_data_empty(self):
        """#170/#171: 空数据应同时重置 working_summary 和 archival。"""
        mm = MemoryManager()
        mm.working_summary = WorkingSummary(intent="stale")
        mm.add_archival("stale entry")
        mm.import_state({})
        assert mm.working_summary.is_empty()
        assert len(mm.archival) == 0

    def test_import_filters_invalid_entries(self):
        """import_state 应跳过无效的 archival 条目。"""
        mm = MemoryManager()
        mm.import_state({
            "archival": [
                {"content": "valid"},
                {"content": ""},  # 空内容，应被跳过
                "not a dict",  # 非 dict，应被跳过
                {"no_content": "missing"},  # 无 content 字段，应被跳过
            ]
        })
        assert len(mm.archival) == 1
        assert mm.archival[0].content == "valid"

    def test_roundtrip_preserves_timestamps(self):
        mm = MemoryManager()
        entry = mm.add_archival("有时间戳", source="test")
        original_ts = entry.timestamp
        state = mm.export_state()

        mm2 = MemoryManager()
        mm2.import_state(state)
        assert mm2.archival[0].timestamp == original_ts


# === save_archival 原子写入测试 ===

class TestSaveArchivalAtomic:
    """验证 save_archival 使用原子写入，崩溃时不丢失已有数据。"""

    def test_save_archival_atomic_preserves_on_error(self):
        """写入失败时，已有的 archival 文件不应被破坏"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(archival_dir=tmpdir)
            mm.add_archival("原始数据")
            # add_archival 自动调用 save_archival()，文件已写入

            # 读取原始文件内容
            with open(mm._archival_path, "r", encoding="utf-8") as f:
                original_content = f.read()
            assert "原始数据" in original_content

            from unittest.mock import patch

            def failing_dump(obj, f, **kwargs):
                raise IOError("模拟写入失败")

            # 在 mock 下添加新数据：add_archival 内的自动 save_archival 也会失败
            with patch("json.dump", side_effect=failing_dump):
                mm.add_archival("新数据")
                # 显式再调用一次确认仍然失败
                result = mm.save_archival()

            assert result is False

            # 验证原始文件未被破坏
            with open(mm._archival_path, "r", encoding="utf-8") as f:
                preserved_content = f.read()
            assert preserved_content == original_content

    def test_save_archival_no_leftover_tmp(self):
        """save_archival 成功后不应留下 .tmp 文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(archival_dir=tmpdir)
            mm.add_archival("test")
            assert mm.save_archival()

            tmp_files = [f for f in os.listdir(tmpdir) if f.endswith(".tmp")]
            assert tmp_files == []

    def test_add_archival_auto_persists(self):
        """add_archival 应自动持久化到磁盘（#161）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mm = MemoryManager(archival_dir=tmpdir)
            mm.add_archival("自动持久化测试", source="test_161")

            # 不手动调用 save_archival()，直接用新的 MemoryManager 加载
            mm2 = MemoryManager(archival_dir=tmpdir)
            count = mm2.load_archival()
            assert count == 1
            assert mm2.archival[0].content == "自动持久化测试"
            assert mm2.archival[0].source == "test_161"
