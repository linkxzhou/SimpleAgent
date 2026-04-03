"""
测试工具模块
"""

import os
import tempfile
import pytest
from src.tools import ToolExecutor


class TestReadFile:
    """测试 read_file 功能"""

    def test_read_existing_file(self):
        """测试读取存在的文件"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test content")
            temp_path = f.name

        try:
            result = ToolExecutor.read_file(temp_path)
            assert result["success"] is True
            assert result["content"] == "test content"
            assert result["path"] == temp_path
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file(self):
        """测试读取不存在的文件"""
        result = ToolExecutor.read_file("/nonexistent/path/file.txt")
        assert result["success"] is False
        assert "error" in result
        assert result["path"] == "/nonexistent/path/file.txt"


class TestWriteFile:
    """测试 write_file 功能"""

    def test_write_new_file(self):
        """测试写入新文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            result = ToolExecutor.write_file(file_path, "new content")

            assert result["success"] is True
            assert os.path.exists(file_path)
            with open(file_path, 'r') as f:
                assert f.read() == "new content"

    def test_write_overwrites_existing(self):
        """测试覆盖现有文件"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("old content")
            temp_path = f.name

        try:
            result = ToolExecutor.write_file(temp_path, "new content")
            assert result["success"] is True
            with open(temp_path, 'r') as f:
                assert f.read() == "new content"
        finally:
            os.unlink(temp_path)


class TestEditFile:
    """测试 edit_file 功能"""

    def test_edit_file_success(self):
        """测试成功编辑文件"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("hello world")
            temp_path = f.name

        try:
            result = ToolExecutor.edit_file(temp_path, "hello", "hi")
            assert result["success"] is True
            with open(temp_path, 'r') as f:
                assert f.read() == "hi world"
        finally:
            os.unlink(temp_path)

    def test_edit_file_only_first_match(self):
        """测试只替换第一个匹配（避免全局替换）"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test test2 test")
            temp_path = f.name

        try:
            result = ToolExecutor.edit_file(temp_path, "test", "TEST")
            assert result["success"] is True
            with open(temp_path, 'r') as f:
                # 应该只替换第一个 "test"，"test2" 保持不变
                assert f.read() == "TEST test2 test"
        finally:
            os.unlink(temp_path)

    def test_edit_file_old_not_found(self):
        """测试旧内容不存在的情况"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("hello world")
            temp_path = f.name

        try:
            result = ToolExecutor.edit_file(temp_path, "nonexistent", "new")
            assert result["success"] is False
            assert "未找到" in result["error"]
        finally:
            os.unlink(temp_path)


class TestExecuteCommand:
    """测试 execute_command 功能"""

    def test_execute_valid_command(self):
        """测试执行有效命令"""
        result = ToolExecutor.execute_command("echo 'hello'")
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_execute_empty_command(self):
        """测试执行空命令应被拒绝"""
        result = ToolExecutor.execute_command("")
        assert result["success"] is False
        assert "不能为空" in result["error"]

    def test_execute_whitespace_command(self):
        """测试执行纯空白命令应被拒绝"""
        result = ToolExecutor.execute_command("   ")
        assert result["success"] is False
        assert "不能为空" in result["error"]

    def test_execute_failing_command(self):
        """测试执行失败的命令"""
        result = ToolExecutor.execute_command("exit 1")
        assert result["success"] is False
        assert result["returncode"] == 1


class TestListFiles:
    """测试 list_files 功能"""

    def test_list_existing_directory(self):
        """测试列出存在的目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一些文件和目录
            os.makedirs(os.path.join(tmpdir, "subdir"))
            with open(os.path.join(tmpdir, "file.txt"), 'w') as f:
                f.write("content")

            result = ToolExecutor.list_files(tmpdir)
            assert result["success"] is True
            assert len(result["items"]) == 2

            names = [item["name"] for item in result["items"]]
            assert "subdir" in names
            assert "file.txt" in names

    def test_list_nonexistent_directory(self):
        """测试列出不存在的目录"""
        result = ToolExecutor.list_files("/nonexistent/path")
        assert result["success"] is False
        assert "error" in result


class TestSearchFiles:
    """测试 search_files 功能"""

    def test_search_by_pattern(self):
        """测试按模式搜索文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一些 Python 文件
            with open(os.path.join(tmpdir, "test1.py"), 'w') as f:
                f.write("# test1")
            with open(os.path.join(tmpdir, "test2.py"), 'w') as f:
                f.write("# test2")
            with open(os.path.join(tmpdir, "readme.txt"), 'w') as f:
                f.write("readme")

            result = ToolExecutor.search_files("*.py", tmpdir)
            assert result["success"] is True
            assert len(result["matches"]) == 2

            paths = [m["path"] for m in result["matches"]]
            assert any("test1.py" in p for p in paths)
            assert any("test2.py" in p for p in paths)