"""tests/test_git.py — Git 感知模块测试"""

import subprocess
from unittest.mock import patch, MagicMock, call
from src.git import is_git_repo, get_git_branch, get_git_status_summary, git_add_and_commit, git_diff_files


class TestIsGitRepo:
    def test_returns_true_in_git_repo(self):
        """当前项目是 Git 仓库，应返回 True"""
        assert is_git_repo() is True

    def test_returns_false_in_non_git_dir(self, tmp_path):
        """临时目录不是 Git 仓库，应返回 False"""
        assert is_git_repo(str(tmp_path)) is False

    def test_returns_false_when_git_not_installed(self):
        """git 命令不存在时应返回 False 而非抛异常"""
        with patch("src.git.subprocess.run", side_effect=FileNotFoundError):
            assert is_git_repo() is False

    def test_returns_false_on_timeout(self):
        """git 命令超时时应返回 False"""
        with patch("src.git.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            assert is_git_repo() is False


class TestGetGitBranch:
    def test_returns_branch_name(self):
        """在当前仓库中应返回非空分支名"""
        branch = get_git_branch()
        assert branch is not None
        assert len(branch) > 0

    def test_returns_none_in_non_git_dir(self, tmp_path):
        """非 Git 目录应返回 None"""
        assert get_git_branch(str(tmp_path)) is None

    def test_returns_none_when_git_not_installed(self):
        """git 命令不存在时应返回 None 而非抛异常"""
        with patch("src.git.subprocess.run", side_effect=FileNotFoundError):
            assert get_git_branch() is None

    def test_returns_none_on_timeout(self):
        """git 命令超时时应返回 None"""
        with patch("src.git.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            assert get_git_branch() is None

    def test_returns_none_on_empty_output(self):
        """git 返回空输出时（如 detached HEAD）应返回 None"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n"
        with patch("src.git.subprocess.run", return_value=mock_result):
            assert get_git_branch() is None


class TestGetGitStatusSummary:
    def test_returns_string_in_git_repo(self):
        """在 Git 仓库中应返回状态字符串"""
        summary = get_git_status_summary()
        assert summary is not None
        assert isinstance(summary, str)

    def test_returns_none_in_non_git_dir(self, tmp_path):
        """非 Git 目录应返回 None"""
        assert get_git_status_summary(str(tmp_path)) is None

    def test_clean_repo(self):
        """没有更改时应返回 'clean'"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("src.git.subprocess.run", return_value=mock_result):
            assert get_git_status_summary() == "clean"

    def test_modified_files(self):
        """有修改文件时应包含 'modified'"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M file1.py\n M file2.py\n"
        with patch("src.git.subprocess.run", return_value=mock_result):
            summary = get_git_status_summary()
            assert "modified" in summary
            assert "2" in summary

    def test_untracked_files(self):
        """有未跟踪文件时应包含 'untracked'"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "?? newfile.txt\n"
        with patch("src.git.subprocess.run", return_value=mock_result):
            summary = get_git_status_summary()
            assert "untracked" in summary

    def test_am_status_not_double_counted(self):
        """AM 状态应只计入 added，不应同时计入 modified（#148）"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "AM src/test.py\nA  new.py\n M changed.py\n"
        with patch("src.git.subprocess.run", return_value=mock_result):
            summary = get_git_status_summary()
            assert "2 added" in summary  # AM + A
            assert "1 modified" in summary  # only M
            # AM must NOT inflate the modified count
            assert "2 modified" not in summary

    def test_added_files(self):
        """纯 added 文件应正确计数"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "A  new1.py\nA  new2.py\n"
        with patch("src.git.subprocess.run", return_value=mock_result):
            summary = get_git_status_summary()
            assert "2 added" in summary
            assert "modified" not in summary

    def test_deleted_files(self):
        """删除的文件应正确计数"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " D removed.py\nD  staged_del.py\n"
        with patch("src.git.subprocess.run", return_value=mock_result):
            summary = get_git_status_summary()
            assert "2 deleted" in summary

    def test_mixed_status(self):
        """混合状态应各自正确计数"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "A  new.py\n M mod.py\n D del.py\n?? unt.py\n"
        with patch("src.git.subprocess.run", return_value=mock_result):
            summary = get_git_status_summary()
            assert "1 added" in summary
            assert "1 modified" in summary
            assert "1 deleted" in summary
            assert "1 untracked" in summary

    def test_returns_none_when_git_not_installed(self):
        """git 命令不存在时应返回 None"""
        with patch("src.git.subprocess.run", side_effect=FileNotFoundError):
            assert get_git_status_summary() is None


class TestGitAddAndCommit:
    """测试 git_add_and_commit 函数"""

    def test_successful_commit(self):
        """正常提交应返回 success=True 和 commit 消息"""
        mock_add = MagicMock(returncode=0, stdout="", stderr="")
        mock_commit = MagicMock(returncode=0, stdout="[main abc1234] test message\n 1 file changed\n", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_add, mock_commit]):
            result = git_add_and_commit(["file1.py", "file2.py"], "test message")
        assert result["success"] is True
        assert "message" in result
        assert "test message" in result["message"]

    def test_commit_calls_git_add_then_commit(self):
        """应先调用 git add，再调用 git commit"""
        mock_add = MagicMock(returncode=0, stdout="", stderr="")
        mock_commit = MagicMock(returncode=0, stdout="[main abc1234] msg\n", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_add, mock_commit]) as mock_run:
            git_add_and_commit(["a.py", "b.py"], "msg")
            calls = mock_run.call_args_list
            # 第一次调用应是 git add
            assert calls[0][0][0][:2] == ["git", "add"]
            # 第二次调用应是 git commit
            assert calls[1][0][0][:2] == ["git", "commit"]

    def test_commit_passes_file_list_to_git_add(self):
        """git add 应包含所有指定的文件"""
        mock_add = MagicMock(returncode=0, stdout="", stderr="")
        mock_commit = MagicMock(returncode=0, stdout="done\n", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_add, mock_commit]) as mock_run:
            git_add_and_commit(["src/a.py", "src/b.py"], "msg")
            add_cmd = mock_run.call_args_list[0][0][0]
            assert "src/a.py" in add_cmd
            assert "src/b.py" in add_cmd

    def test_git_add_failure(self):
        """git add 失败时应返回错误"""
        mock_add = MagicMock(returncode=1, stdout="", stderr="fatal: not a git repository")
        with patch("src.git.subprocess.run", return_value=mock_add):
            result = git_add_and_commit(["file.py"], "msg")
        assert result["success"] is False
        assert "error" in result


class TestGitDiffFiles:
    """测试 git_diff_files 函数"""

    def test_empty_file_list(self):
        """空文件列表应返回错误"""
        result = git_diff_files([])
        assert result["success"] is False
        assert "error" in result

    def test_successful_diff_with_changes(self):
        """有差异时应返回 diff 文本"""
        mock_diff = MagicMock(returncode=0, stdout="diff --git a/f.py b/f.py\n+x=1\n", stderr="")
        mock_status = MagicMock(returncode=0, stdout="", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_diff, mock_status]):
            result = git_diff_files(["f.py"])
        assert result["success"] is True
        assert "diff --git" in result["diff"]
        assert result["files"] == ["f.py"]

    def test_no_diff_clean_files(self):
        """已提交文件没有差异时 diff 应为空字符串"""
        mock_diff = MagicMock(returncode=0, stdout="", stderr="")
        mock_status = MagicMock(returncode=0, stdout="", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_diff, mock_status]):
            result = git_diff_files(["f.py"])
        assert result["success"] is True
        assert result["diff"] == ""

    def test_untracked_file_detected(self):
        """未跟踪的新文件应被标记"""
        mock_diff = MagicMock(returncode=0, stdout="", stderr="")
        mock_status = MagicMock(returncode=0, stdout="?? new_file.py\n", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_diff, mock_status]):
            result = git_diff_files(["new_file.py"])
        assert result["success"] is True
        assert "new_file.py" in result["diff"]
        assert "未跟踪" in result["diff"]

    def test_mixed_tracked_and_untracked(self):
        """同时有已跟踪修改和未跟踪文件"""
        mock_diff = MagicMock(returncode=0, stdout="diff --git a/a.py b/a.py\n-old\n+new\n", stderr="")
        mock_status = MagicMock(returncode=0, stdout="?? b.py\n", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_diff, mock_status]):
            result = git_diff_files(["a.py", "b.py"])
        assert result["success"] is True
        assert "diff --git" in result["diff"]
        assert "b.py" in result["diff"]

    def test_git_not_installed(self):
        """git 未安装时应返回错误"""
        with patch("src.git.subprocess.run", side_effect=FileNotFoundError):
            result = git_diff_files(["f.py"])
        assert result["success"] is False
        assert "error" in result

    def test_git_timeout(self):
        """git 命令超时时应返回错误"""
        with patch("src.git.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            result = git_diff_files(["f.py"])
        assert result["success"] is False
        assert "error" in result

    def test_multiple_files_passed_to_git(self):
        """应将所有文件传递给 git diff 命令"""
        mock_diff = MagicMock(returncode=0, stdout="", stderr="")
        mock_status = MagicMock(returncode=0, stdout="", stderr="")
        with patch("src.git.subprocess.run", side_effect=[mock_diff, mock_status]) as mock_run:
            git_diff_files(["a.py", "b.py", "c.py"])
            diff_cmd = mock_run.call_args_list[0][0][0]
            assert "a.py" in diff_cmd
            assert "b.py" in diff_cmd
            assert "c.py" in diff_cmd

    def test_git_commit_failure(self):
        """git add 成功但 git commit 失败时应返回错误"""
        mock_add = MagicMock(returncode=0, stdout="", stderr="")
        mock_commit = MagicMock(returncode=1, stdout="", stderr="nothing to commit")
        with patch("src.git.subprocess.run", side_effect=[mock_add, mock_commit]):
            result = git_add_and_commit(["file.py"], "msg")
        assert result["success"] is False
        assert "error" in result

    def test_empty_file_list(self):
        """空文件列表应返回错误"""
        result = git_add_and_commit([], "msg")
        assert result["success"] is False
        assert "error" in result

    def test_git_not_installed(self):
        """git 未安装时应返回错误而非抛异常"""
        with patch("src.git.subprocess.run", side_effect=FileNotFoundError):
            result = git_add_and_commit(["file.py"], "msg")
        assert result["success"] is False
        assert "error" in result

    def test_git_timeout(self):
        """git 命令超时时应返回错误"""
        with patch("src.git.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            result = git_add_and_commit(["file.py"], "msg")
        assert result["success"] is False
        assert "error" in result
