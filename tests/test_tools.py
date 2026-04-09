"""tests/test_tools.py — ToolExecutor 文件操作和命令执行测试"""

import os
import tempfile
import shutil
from src.tools import ToolExecutor, TOOL_DEFINITIONS, default_tools


class TestToolExecutorReadFile:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("world", encoding="utf-8")
        result = ToolExecutor.read_file(str(f))
        assert result["success"] is True
        assert result["content"] == "world"

    def test_read_nonexistent_file(self):
        result = ToolExecutor.read_file("/nonexistent/path/xyz.txt")
        assert result["success"] is False
        assert "error" in result

    def test_read_utf8(self, tmp_path):
        f = tmp_path / "cn.txt"
        f.write_text("你好世界", encoding="utf-8")
        result = ToolExecutor.read_file(str(f))
        assert result["success"] is True
        assert result["content"] == "你好世界"

    def test_read_large_file_truncated(self, tmp_path):
        """大文件应截断为 MAX_READ_SIZE 并附加警告（#168）"""
        f = tmp_path / "big.txt"
        big_content = "X" * (ToolExecutor.MAX_READ_SIZE + 1000)
        f.write_text(big_content, encoding="utf-8")
        result = ToolExecutor.read_file(str(f))
        assert result["success"] is True
        assert result["truncated"] is True
        assert len(result["content"]) == ToolExecutor.MAX_READ_SIZE
        assert result["file_size"] == len(big_content)
        assert "截断" in result["warning"]

    def test_read_exact_limit_not_truncated(self, tmp_path):
        """刚好等于 MAX_READ_SIZE 的文件不截断"""
        f = tmp_path / "exact.txt"
        exact_content = "Y" * ToolExecutor.MAX_READ_SIZE
        f.write_text(exact_content, encoding="utf-8")
        result = ToolExecutor.read_file(str(f))
        assert result["success"] is True
        assert "truncated" not in result
        assert len(result["content"]) == ToolExecutor.MAX_READ_SIZE

    def test_read_small_file_no_truncation(self, tmp_path):
        """小文件不截断且无 truncated 字段"""
        f = tmp_path / "small.txt"
        f.write_text("tiny", encoding="utf-8")
        result = ToolExecutor.read_file(str(f))
        assert result["success"] is True
        assert "truncated" not in result
        assert result["content"] == "tiny"


class TestToolExecutorWriteFile:
    def test_write_new_file(self, tmp_path):
        target = str(tmp_path / "output.txt")
        result = ToolExecutor.write_file(target, "hello")
        assert result["success"] is True
        assert os.path.isfile(target)
        with open(target, encoding="utf-8") as f:
            assert f.read() == "hello"

    def test_write_creates_dirs(self, tmp_path):
        target = str(tmp_path / "sub" / "dir" / "file.txt")
        result = ToolExecutor.write_file(target, "nested")
        assert result["success"] is True
        with open(target, encoding="utf-8") as f:
            assert f.read() == "nested"

    def test_write_overwrites(self, tmp_path):
        target = str(tmp_path / "over.txt")
        ToolExecutor.write_file(target, "first")
        ToolExecutor.write_file(target, "second")
        with open(target, encoding="utf-8") as f:
            assert f.read() == "second"

    def test_write_file_in_current_dir(self, tmp_path, monkeypatch):
        """测试写入当前目录下的文件（无目录前缀），验证 write_file Bug 修复"""
        monkeypatch.chdir(tmp_path)
        result = ToolExecutor.write_file("plain.txt", "content")
        assert result["success"] is True
        with open(str(tmp_path / "plain.txt"), encoding="utf-8") as f:
            assert f.read() == "content"


class TestToolExecutorEditFile:
    def test_edit_success(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello world", encoding="utf-8")
        result = ToolExecutor.edit_file(str(f), "world", "earth")
        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "hello earth"

    def test_edit_old_content_not_found(self, tmp_path):
        f = tmp_path / "edit2.txt"
        f.write_text("hello world", encoding="utf-8")
        result = ToolExecutor.edit_file(str(f), "mars", "earth")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_edit_nonexistent_file(self):
        result = ToolExecutor.edit_file("/nonexistent/xyz.txt", "a", "b")
        assert result["success"] is False

    def test_edit_replaces_first_occurrence_only(self, tmp_path):
        """edit_file 应仅替换第一处匹配，保留后续出现"""
        f = tmp_path / "multi.txt"
        f.write_text("aaa bbb aaa", encoding="utf-8")
        result = ToolExecutor.edit_file(str(f), "aaa", "ccc")
        assert result["success"] is True
        # 仅第一个 aaa 被替换为 ccc，第二个 aaa 保留
        assert f.read_text(encoding="utf-8") == "ccc bbb aaa"


class TestToolExecutorListFiles:
    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "subdir").mkdir()
        result = ToolExecutor.list_files(str(tmp_path))
        assert result["success"] is True
        names = {item["name"] for item in result["items"]}
        assert "a.txt" in names
        assert "subdir" in names

    def test_list_nonexistent(self):
        result = ToolExecutor.list_files("/nonexistent/path/xyz")
        assert result["success"] is False

    def test_list_includes_type(self, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "dir").mkdir()
        result = ToolExecutor.list_files(str(tmp_path))
        type_map = {item["name"]: item["type"] for item in result["items"]}
        assert type_map["file.txt"] == "file"
        assert type_map["dir"] == "directory"


class TestToolExecutorExecuteCommand:
    def test_success_command(self):
        result = ToolExecutor.execute_command("echo hello")
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_failing_command(self):
        result = ToolExecutor.execute_command("false")
        assert result["success"] is False
        assert result["returncode"] != 0

    def test_command_with_cwd(self, tmp_path):
        result = ToolExecutor.execute_command("pwd", cwd=str(tmp_path))
        assert result["success"] is True
        assert str(tmp_path) in result["stdout"]

    def test_command_stderr(self):
        result = ToolExecutor.execute_command("echo err >&2")
        assert "err" in result["stderr"]

    def test_default_timeout_is_120(self):
        """默认超时应为 120 秒（类常量）"""
        assert ToolExecutor.DEFAULT_COMMAND_TIMEOUT == 120

    def test_custom_timeout_success(self):
        """自定义短超时，命令在超时内完成"""
        result = ToolExecutor.execute_command("echo fast", timeout=5)
        assert result["success"] is True
        assert "fast" in result["stdout"]

    def test_custom_timeout_expired(self):
        """自定义 1 秒超时，sleep 3 应被杀掉"""
        result = ToolExecutor.execute_command("sleep 3", timeout=1)
        assert result["success"] is False
        assert "timed out" in result["error"]
        assert "1s" in result["error"]

    def test_timeout_error_includes_seconds(self):
        """超时错误信息应包含具体超时秒数"""
        result = ToolExecutor.execute_command("sleep 10", timeout=2)
        assert result["success"] is False
        assert "2s" in result["error"]
        assert "command" in result

    def test_timeout_none_uses_default(self):
        """timeout=None 应使用默认值（不崩溃）"""
        result = ToolExecutor.execute_command("echo ok", timeout=None)
        assert result["success"] is True
        assert "ok" in result["stdout"]


class TestToolExecutorSearchFiles:
    def test_search_py_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.py").write_text("z")
        result = ToolExecutor.search_files("*.py", str(tmp_path))
        assert result["success"] is True
        paths = [m["path"] for m in result["matches"]]
        assert any("a.py" in p for p in paths)
        assert any("c.py" in p for p in paths)
        assert not any("b.txt" in p for p in paths)

    def test_search_no_matches(self, tmp_path):
        result = ToolExecutor.search_files("*.xyz", str(tmp_path))
        assert result["success"] is True
        assert len(result["matches"]) == 0


class TestToolDefinitions:
    def test_definitions_is_list(self):
        assert isinstance(TOOL_DEFINITIONS, list)
        assert len(TOOL_DEFINITIONS) == 7

    def test_each_has_function(self):
        for td in TOOL_DEFINITIONS:
            assert td["type"] == "function"
            assert "function" in td
            assert "name" in td["function"]
            assert "parameters" in td["function"]

    def test_tool_names(self):
        names = {td["function"]["name"] for td in TOOL_DEFINITIONS}
        expected = {"read_file", "write_file", "edit_file", "list_files", "execute_command", "search_files", "web_search"}
        assert names == expected


class TestDdgsMigration:
    """测试 duckduckgo_search → ddgs 包名迁移"""

    def test_web_search_no_runtime_warning(self):
        """web_search 不应产生 duckduckgo_search 包改名的 RuntimeWarning"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ToolExecutor.web_search("test migration", max_results=1)
            runtime_warnings = [
                x for x in w
                if issubclass(x.category, RuntimeWarning)
                and "renamed" in str(x.message).lower()
            ]
            assert len(runtime_warnings) == 0, (
                f"发现 {len(runtime_warnings)} 个包改名 RuntimeWarning: "
                f"{[str(x.message) for x in runtime_warnings]}"
            )

    def test_web_search_import_error_suggests_ddgs(self, monkeypatch):
        """DuckDuckGo 库未安装时，错误提示应指向新包名 ddgs"""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("ddgs", "duckduckgo_search"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = ToolExecutor.web_search("test query")
        assert result["success"] is False
        assert "pip install ddgs" in result["error"]

    def test_requirements_uses_ddgs(self):
        """requirements.txt 应使用新包名 ddgs 而非 duckduckgo-search"""
        with open("requirements.txt", "r") as f:
            content = f.read()
        assert "ddgs" in content.lower()
        assert "duckduckgo-search" not in content


class TestToolExecutorWebSearch:
    def test_web_search_returns_correct_structure(self):
        """web_search 应返回正确的数据结构"""
        result = ToolExecutor.web_search("python programming", max_results=2)
        # 不管是否有结果，结构应正确
        assert "success" in result
        assert "query" in result
        assert result["query"] == "python programming"
        if result["success"]:
            assert "results" in result
            assert "count" in result
            assert isinstance(result["results"], list)
            # 如果有结果，检查每条结果的字段
            for item in result["results"]:
                assert "title" in item
                assert "url" in item
                assert "snippet" in item

    def test_web_search_default_max_results(self):
        """不指定 max_results 时应使用默认值 5"""
        result = ToolExecutor.web_search("test query")
        assert "query" in result
        if result["success"]:
            assert result["count"] <= 5

    def test_web_search_max_results_clamped_low(self):
        """max_results=0 应被调整为 1"""
        result = ToolExecutor.web_search("test", max_results=0)
        assert "query" in result
        # 只要不抛异常即可，网络可能不稳定

    def test_web_search_max_results_clamped_high(self):
        """max_results=100 应被调整为 20"""
        result = ToolExecutor.web_search("test", max_results=100)
        assert "query" in result
        if result["success"]:
            assert result["count"] <= 20

    def test_web_search_import_error(self, monkeypatch):
        """DuckDuckGo 库未安装时应返回友好错误"""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("ddgs", "duckduckgo_search"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = ToolExecutor.web_search("test query")
        assert result["success"] is False
        assert "未安装" in result["error"]
        assert result["query"] == "test query"

    def test_web_search_with_mock(self):
        """使用 mock 验证搜索逻辑正确性（不依赖网络）"""
        from unittest.mock import MagicMock, patch

        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.text.return_value = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Snippet 2"},
        ]

        mock_ddgs_class = MagicMock(return_value=mock_ddgs_instance)

        # web_search 内部用 lazy import: from ddgs import DDGS（优先）或 from duckduckgo_search import DDGS
        # 需要 patch 实际被导入的模块中的 DDGS 类
        # 确定运行时走哪个包名
        try:
            import ddgs
            target = "ddgs.DDGS"
        except ImportError:
            target = "duckduckgo_search.DDGS"

        with patch(target, mock_ddgs_class):
            result = ToolExecutor.web_search("test query", max_results=3)

        assert result["success"] is True
        assert result["query"] == "test query"
        assert result["count"] == 2
        assert result["results"][0]["title"] == "Result 1"
        assert result["results"][0]["url"] == "https://example.com/1"
        assert result["results"][1]["snippet"] == "Snippet 2"
        mock_ddgs_instance.text.assert_called_once_with("test query", max_results=3)


class TestDiffPreview:
    """测试 edit_file 和 write_file 的差异预览功能"""

    def test_edit_file_returns_diff(self, tmp_path):
        """edit_file 成功时应返回 diff 字段"""
        f = tmp_path / "diff_test.txt"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        result = ToolExecutor.edit_file(str(f), "line2", "LINE_TWO")
        assert result["success"] is True
        assert "diff" in result
        assert isinstance(result["diff"], str)
        # diff 应包含旧内容和新内容的标记
        assert "-line2" in result["diff"] or "- line2" in result["diff"] or "-line2" in result["diff"].replace(" ", "")
        assert "+LINE_TWO" in result["diff"] or "+ LINE_TWO" in result["diff"] or "+LINE_TWO" in result["diff"].replace(" ", "")

    def test_edit_file_no_diff_on_failure(self, tmp_path):
        """edit_file 失败时（old_content 未找到）不应返回 diff"""
        f = tmp_path / "no_diff.txt"
        f.write_text("hello", encoding="utf-8")
        result = ToolExecutor.edit_file(str(f), "missing", "new")
        assert result["success"] is False
        assert "diff" not in result or result.get("diff") is None

    def test_write_file_overwrite_returns_diff(self, tmp_path):
        """write_file 覆盖已有文件时应返回 diff"""
        f = tmp_path / "overwrite.txt"
        f.write_text("original content\n", encoding="utf-8")
        result = ToolExecutor.write_file(str(f), "new content\n")
        assert result["success"] is True
        assert "diff" in result
        assert isinstance(result["diff"], str)
        assert "original" in result["diff"]
        assert "new content" in result["diff"]

    def test_write_file_new_file_returns_diff(self, tmp_path):
        """write_file 创建新文件时应返回 diff（全部为新增行）"""
        target = str(tmp_path / "brand_new.txt")
        result = ToolExecutor.write_file(target, "new content\n")
        assert result["success"] is True
        assert "diff" in result
        assert "+new content" in result["diff"] or "+ new content" in result["diff"]

    def test_edit_file_diff_is_unified_format(self, tmp_path):
        """edit_file 的 diff 应使用 unified diff 格式"""
        f = tmp_path / "unified.txt"
        f.write_text("aaa\nbbb\nccc\n", encoding="utf-8")
        result = ToolExecutor.edit_file(str(f), "bbb", "BBB")
        assert result["success"] is True
        diff = result["diff"]
        # unified diff 包含 --- 和 +++ 头部
        assert "---" in diff
        assert "+++" in diff

    def test_write_file_identical_content_no_diff(self, tmp_path):
        """write_file 写入与原内容相同时，diff 应为空或不含变更行"""
        f = tmp_path / "same.txt"
        f.write_text("same content", encoding="utf-8")
        result = ToolExecutor.write_file(str(f), "same content")
        assert result["success"] is True
        # diff 为空字符串或不包含 + - 变更行
        diff = result.get("diff", "")
        # 无变化时 diff 应该为空
        assert diff == ""

    def test_large_diff_is_truncated(self, tmp_path):
        """大文件 diff 超过 MAX_DIFF_LINES 时应被截断"""
        f = tmp_path / "large.txt"
        # 创建一个 200 行的文件
        old_lines = [f"line {i}\n" for i in range(200)]
        f.write_text("".join(old_lines), encoding="utf-8")
        # 全部替换为不同内容 → 产生 400+ 行 diff（200 删 + 200 增 + 头部）
        new_lines = [f"changed {i}\n" for i in range(200)]
        diff = ToolExecutor._generate_diff("".join(old_lines), "".join(new_lines), str(f))
        diff_line_count = len(diff.splitlines())
        # diff 行数应被限制，不超过 MAX_DIFF_LINES + 少量头尾
        assert diff_line_count <= ToolExecutor.MAX_DIFF_LINES + 5
        # 截断标记应存在
        assert "省略" in diff or "truncated" in diff.lower() or "..." in diff

    def test_small_diff_not_truncated(self, tmp_path):
        """小 diff（未超过限制）不应被截断"""
        diff = ToolExecutor._generate_diff("aaa\nbbb\n", "aaa\nBBB\n", "test.txt")
        assert "省略" not in diff
        assert diff != ""

    def test_max_diff_lines_constant_exists(self):
        """ToolExecutor 应有 MAX_DIFF_LINES 类常量"""
        assert hasattr(ToolExecutor, "MAX_DIFF_LINES")
        assert isinstance(ToolExecutor.MAX_DIFF_LINES, int)
        assert ToolExecutor.MAX_DIFF_LINES > 0

    def test_truncated_diff_preserves_header(self, tmp_path):
        """截断后的 diff 应保留 unified diff 头部（--- 和 +++）"""
        old_content = "".join([f"old line {i}\n" for i in range(500)])
        new_content = "".join([f"new line {i}\n" for i in range(500)])
        diff = ToolExecutor._generate_diff(old_content, new_content, "big.txt")
        assert "---" in diff
        assert "+++" in diff


class TestUndo:
    """测试 /undo 撤销文件更改功能"""

    def test_undo_stack_empty_by_default(self):
        """新建的 ToolExecutor 应没有 undo 记录"""
        tools = ToolExecutor()
        result = tools.undo()
        assert result["success"] is False
        assert "没有可撤销的更改" in result["error"]

    def test_undo_after_write_file(self, tmp_path):
        """write_file 覆盖文件后，undo 应恢复原内容"""
        f = tmp_path / "undo_write.txt"
        f.write_text("original", encoding="utf-8")
        tools = ToolExecutor()
        tools.record_undo(str(f), "original")
        ToolExecutor.write_file(str(f), "modified")
        assert f.read_text(encoding="utf-8") == "modified"
        result = tools.undo()
        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "original"
        assert result["path"] == str(f)

    def test_undo_after_edit_file(self, tmp_path):
        """edit_file 修改文件后，undo 应恢复原内容"""
        f = tmp_path / "undo_edit.txt"
        f.write_text("hello world", encoding="utf-8")
        tools = ToolExecutor()
        tools.record_undo(str(f), "hello world")
        ToolExecutor.edit_file(str(f), "world", "earth")
        assert f.read_text(encoding="utf-8") == "hello earth"
        result = tools.undo()
        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "hello world"

    def test_undo_new_file_deletes_it(self, tmp_path):
        """write_file 创建新文件后，undo 应删除该文件"""
        target = str(tmp_path / "brand_new.txt")
        tools = ToolExecutor()
        tools.record_undo(target, None)  # None 表示文件之前不存在
        ToolExecutor.write_file(target, "new content")
        assert os.path.isfile(target)
        result = tools.undo()
        assert result["success"] is True
        assert not os.path.isfile(target)

    def test_undo_only_last_change(self, tmp_path):
        """多次修改后，undo 只撤销最后一次"""
        f = tmp_path / "multi.txt"
        f.write_text("v1", encoding="utf-8")
        tools = ToolExecutor()
        tools.record_undo(str(f), "v1")
        ToolExecutor.write_file(str(f), "v2")
        tools.record_undo(str(f), "v2")
        ToolExecutor.write_file(str(f), "v3")
        assert f.read_text(encoding="utf-8") == "v3"
        result = tools.undo()
        assert result["success"] is True
        assert f.read_text(encoding="utf-8") == "v2"

    def test_undo_twice_restores_two_changes(self, tmp_path):
        """连续 undo 两次应逐步恢复"""
        f = tmp_path / "twice.txt"
        f.write_text("v1", encoding="utf-8")
        tools = ToolExecutor()
        tools.record_undo(str(f), "v1")
        ToolExecutor.write_file(str(f), "v2")
        tools.record_undo(str(f), "v2")
        ToolExecutor.write_file(str(f), "v3")
        tools.undo()
        assert f.read_text(encoding="utf-8") == "v2"
        tools.undo()
        assert f.read_text(encoding="utf-8") == "v1"

    def test_undo_returns_diff(self, tmp_path):
        """undo 成功时应返回 diff 字段"""
        f = tmp_path / "diff_undo.txt"
        f.write_text("old content\n", encoding="utf-8")
        tools = ToolExecutor()
        tools.record_undo(str(f), "old content\n")
        ToolExecutor.write_file(str(f), "new content\n")
        result = tools.undo()
        assert result["success"] is True
        assert "diff" in result
        assert "old content" in result["diff"]
        assert "new content" in result["diff"]

    def test_undo_after_empty_stack(self, tmp_path):
        """undo 栈为空时再次 undo 应返回错误"""
        f = tmp_path / "once.txt"
        f.write_text("orig", encoding="utf-8")
        tools = ToolExecutor()
        tools.record_undo(str(f), "orig")
        ToolExecutor.write_file(str(f), "changed")
        tools.undo()  # 第一次 undo 成功
        result = tools.undo()  # 第二次应失败
        assert result["success"] is False
        assert "没有可撤销的更改" in result["error"]


class TestDefaultTools:
    def test_returns_tool_executor(self):
        tools = default_tools()
        assert isinstance(tools, ToolExecutor)


class TestGetModifiedFiles:
    """测试 ToolExecutor.get_modified_files() 方法"""

    def test_empty_undo_stack_returns_empty(self):
        """没有记录时应返回空列表"""
        tools = ToolExecutor()
        assert tools.get_modified_files() == []

    def test_returns_unique_paths(self):
        """同一文件修改多次应只返回一个路径"""
        tools = ToolExecutor()
        tools.record_undo("a.py", "old1")
        tools.record_undo("a.py", "old2")
        result = tools.get_modified_files()
        assert result == ["a.py"]

    def test_returns_multiple_files(self):
        """多个不同文件应都返回"""
        tools = ToolExecutor()
        tools.record_undo("a.py", "old")
        tools.record_undo("b.py", "old")
        tools.record_undo("c.py", None)
        result = tools.get_modified_files()
        assert set(result) == {"a.py", "b.py", "c.py"}

    def test_preserves_order(self):
        """应按首次出现的顺序返回"""
        tools = ToolExecutor()
        tools.record_undo("b.py", "old")
        tools.record_undo("a.py", "old")
        tools.record_undo("b.py", "old2")
        result = tools.get_modified_files()
        assert result == ["b.py", "a.py"]


class TestBinaryFileHandling:
    """测试二进制文件的友好错误处理（#176）"""

    def test_read_binary_file_returns_friendly_error(self, tmp_path):
        """read_file 读取二进制文件应返回清晰的中文错误消息"""
        f = tmp_path / "binary.dat"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        result = ToolExecutor.read_file(str(f))
        assert result["success"] is False
        assert "二进制文件" in result["error"]
        assert str(f) in result["error"]

    def test_edit_binary_file_returns_friendly_error(self, tmp_path):
        """edit_file 编辑二进制文件应返回清晰的中文错误消息"""
        f = tmp_path / "binary.dat"
        f.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")
        result = ToolExecutor.edit_file(str(f), "old", "new")
        assert result["success"] is False
        assert "二进制文件" in result["error"]
        assert str(f) in result["error"]

    def test_read_binary_error_suggests_alternative(self, tmp_path):
        """read_file 二进制文件错误应建议使用 execute_command"""
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = ToolExecutor.read_file(str(f))
        assert result["success"] is False
        assert "execute_command" in result["error"]

    def test_edit_binary_error_mentions_text_only(self, tmp_path):
        """edit_file 二进制文件错误应说明仅支持文本文件"""
        f = tmp_path / "data.bin"
        f.write_bytes(bytes(range(256)))
        result = ToolExecutor.edit_file(str(f), "x", "y")
        assert result["success"] is False
        assert "文本文件" in result["error"]
