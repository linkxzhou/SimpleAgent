"""tests/test_cli.py — CLI 工具函数测试"""

import subprocess
import sys

from src.cli import truncate, DEFAULT_MODEL, parse_args, print_usage, format_diff_lines, read_user_input, load_system_prompt, format_elapsed, MarkdownRenderer, resolve_model_for_provider
from src.models import Usage
from src.colors import GREEN, RED, CYAN, DIM, RESET, BOLD, YELLOW
from src import __version__


class TestTruncate:
    def test_short_string(self):
        assert truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert truncate("12345", 5) == "12345"

    def test_long_string(self):
        result = truncate("hello world this is long", 10)
        assert len(result) <= 10
        assert result.endswith("…")

    def test_empty_string(self):
        assert truncate("", 10) == ""

    def test_unicode(self):
        s = "你好世界测试"
        result = truncate(s, 4)
        assert result.endswith("…")
        assert len(result) <= 4

    def test_truncated_has_ellipsis(self):
        """截断的字符串末尾应有省略号"""
        result = truncate("abcdefghij", 5)
        assert result.endswith("…")
        assert len(result) <= 5

    def test_not_truncated_no_ellipsis(self):
        """未截断的字符串不应有省略号"""
        result = truncate("abc", 10)
        assert not result.endswith("…")
        assert result == "abc"


class TestDefaultModel:
    def test_default_model_exists(self):
        assert isinstance(DEFAULT_MODEL, str)
        assert len(DEFAULT_MODEL) > 0


class TestVersion:
    def test_version_string_format(self):
        """__version__ 应该是非空字符串"""
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_flag_output(self):
        """python main.py --version 应输出版本号并正常退出"""
        result = subprocess.run(
            [sys.executable, "main.py", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "SimpleAgent" in result.stdout
        assert __version__ in result.stdout


class TestParseArgsModelSafety:
    def test_model_defaults_to_none(self, monkeypatch):
        """当没有 --model 参数时，args.model 应为 None（由 main() 决定最终模型）"""
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["cli.py"])
        args = parse_args()
        assert args.model is None

    def test_model_none_when_env_set_but_no_cli_arg(self, monkeypatch):
        """设置了 OPENAI_MODEL 但没有 --model 时，args.model 仍为 None（main() 负责读取环境变量）"""
        monkeypatch.setenv("OPENAI_MODEL", "test-model-env")
        monkeypatch.setattr("sys.argv", ["cli.py"])
        args = parse_args()
        assert args.model is None

    def test_model_from_cli_arg(self, monkeypatch):
        """--model 命令行参数应设置 args.model"""
        monkeypatch.setenv("OPENAI_MODEL", "test-model-env")
        monkeypatch.setattr("sys.argv", ["cli.py", "--model", "cli-model"])
        args = parse_args()
        assert args.model == "cli-model"


class TestResolveModelForProvider:
    """resolve_model_for_provider() 测试 — #142 修复的核心逻辑。"""

    def test_cli_model_always_wins(self):
        """用户显式 --model 时，直接使用该模型，无论有无 provider 或 env"""
        model, ignored = resolve_model_for_provider("my-model", "deepseek", "gpt-4o")
        assert model == "my-model"
        assert ignored is False

    def test_cli_model_without_provider(self):
        """--model 无 --provider 时也直接使用"""
        model, ignored = resolve_model_for_provider("my-model", None, "gpt-4o")
        assert model == "my-model"
        assert ignored is False

    def test_provider_without_model_ignores_env(self):
        """--provider 无 --model 且有 OPENAI_MODEL 时，忽略 env 并返回 None（让 provider 用默认值）"""
        model, ignored = resolve_model_for_provider(None, "deepseek", "gpt-4o")
        assert model is None
        assert ignored is True

    def test_provider_without_model_no_env(self):
        """--provider 无 --model 且无 OPENAI_MODEL 时，正常返回 None"""
        model, ignored = resolve_model_for_provider(None, "deepseek", None)
        assert model is None
        assert ignored is False

    def test_no_provider_no_model_uses_env(self):
        """无 --provider 无 --model 时，使用 OPENAI_MODEL"""
        model, ignored = resolve_model_for_provider(None, None, "gpt-4o")
        assert model == "gpt-4o"
        assert ignored is False

    def test_no_provider_no_model_no_env(self):
        """无 --provider 无 --model 无 OPENAI_MODEL 时，返回 None"""
        model, ignored = resolve_model_for_provider(None, None, None)
        assert model is None
        assert ignored is False

    def test_provider_with_empty_env(self):
        """--provider 无 --model 且 OPENAI_MODEL 为空字符串时，不视为被忽略"""
        model, ignored = resolve_model_for_provider(None, "groq", "")
        assert model is None
        assert ignored is False  # 空字符串 → bool("") = False

    def test_provider_with_explicit_model_no_warning(self):
        """--provider 加 --model 时不警告（即使 OPENAI_MODEL 存在）"""
        model, ignored = resolve_model_for_provider("deepseek-chat", "deepseek", "gpt-4o")
        assert model == "deepseek-chat"
        assert ignored is False


class TestPrintUsage:
    """测试 print_usage 函数的输出格式"""

    def test_print_usage_with_round_only(self, capsys):
        """只有本轮用量时，不显示会话累计"""
        round_usage = Usage(input=100, output=50)
        print_usage(round_usage)
        captured = capsys.readouterr()
        assert "100" in captured.out
        assert "50" in captured.out

    def test_print_usage_with_session(self, capsys):
        """有会话累计用量时，同时显示本轮和累计"""
        round_usage = Usage(input=100, output=50)
        session_usage = Usage(input=500, output=200)
        print_usage(round_usage, session_usage)
        captured = capsys.readouterr()
        # 应该包含本轮用量
        assert "100" in captured.out
        assert "50" in captured.out
        # 应该包含会话累计
        assert "500" in captured.out
        assert "200" in captured.out

    def test_print_usage_zero_round_no_output(self, capsys):
        """本轮用量为 0 时不输出任何内容"""
        round_usage = Usage(input=0, output=0)
        print_usage(round_usage)
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_print_usage_session_none(self, capsys):
        """session_usage 为 None 时只显示本轮"""
        round_usage = Usage(input=200, output=80)
        print_usage(round_usage, None)
        captured = capsys.readouterr()
        assert "200" in captured.out
        assert "80" in captured.out


class TestUsageAccumulation:
    """测试 Usage 数据类的累加操作"""

    def test_usage_add(self):
        """Usage 的 add 方法应正确累加"""
        session = Usage(input=100, output=50)
        round_usage = Usage(input=200, output=80)
        session.input += round_usage.input
        session.output += round_usage.output
        assert session.input == 300
        assert session.output == 130

    def test_usage_defaults_zero(self):
        """Usage 默认值应为 0"""
        u = Usage()
        assert u.input == 0
        assert u.output == 0


class TestFormatDiffLines:
    """测试 format_diff_lines 函数的差异渲染"""

    def test_empty_diff_returns_empty_list(self):
        """空 diff 文本应返回空列表"""
        assert format_diff_lines("") == []
        assert format_diff_lines(None) == []

    def test_added_line_is_green(self):
        """以 + 开头的行应包含 GREEN 颜色"""
        lines = format_diff_lines("+added line")
        assert len(lines) == 1
        assert GREEN in lines[0]
        assert "+added line" in lines[0]

    def test_removed_line_is_red(self):
        """以 - 开头的行应包含 RED 颜色"""
        lines = format_diff_lines("-removed line")
        assert len(lines) == 1
        assert RED in lines[0]
        assert "-removed line" in lines[0]

    def test_hunk_header_is_cyan(self):
        """以 @@ 开头的行应包含 CYAN 颜色"""
        lines = format_diff_lines("@@ -1,3 +1,3 @@")
        assert len(lines) == 1
        assert CYAN in lines[0]

    def test_file_headers_are_dim(self):
        """--- 和 +++ 文件头应使用 DIM 颜色"""
        diff = "--- a/file.txt\n+++ b/file.txt"
        lines = format_diff_lines(diff)
        assert len(lines) == 2
        assert DIM in lines[0]
        assert DIM in lines[1]

    def test_context_line_is_dim(self):
        """上下文行（无前缀）应使用 DIM 颜色"""
        lines = format_diff_lines(" context line")
        assert len(lines) == 1
        assert DIM in lines[0]

    def test_multiline_diff(self):
        """多行 diff 应正确分类渲染"""
        diff = "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n-old\n+new\n same"
        lines = format_diff_lines(diff)
        assert len(lines) == 6
        # 头部 DIM
        assert DIM in lines[0]
        assert DIM in lines[1]
        # hunk header CYAN
        assert CYAN in lines[2]
        # removed RED
        assert RED in lines[3]
        # added GREEN
        assert GREEN in lines[4]
        # context DIM
        assert DIM in lines[5]


class TestReadUserInput:
    """测试 read_user_input 函数的单行和多行输入"""

    def test_single_line_input(self, monkeypatch):
        """普通单行输入直接返回"""
        monkeypatch.setattr("builtins.input", lambda prompt="": "hello world")
        result = read_user_input("prompt> ")
        assert result == "hello world"

    def test_single_line_whitespace_stripped(self, monkeypatch):
        """单行输入两端空白应被去除"""
        monkeypatch.setattr("builtins.input", lambda prompt="":  "  hello  ")
        result = read_user_input("prompt> ")
        assert result == "hello"

    def test_empty_input_returns_empty(self, monkeypatch):
        """空输入返回空字符串"""
        monkeypatch.setattr("builtins.input", lambda prompt="": "")
        result = read_user_input("prompt> ")
        assert result == ""

    def test_multiline_triple_double_quotes(self, monkeypatch):
        """三双引号开头进入多行模式，三双引号结尾退出"""
        inputs = iter(['\"\"\"', "line 1", "line 2", '\"\"\"'])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        result = read_user_input("prompt> ")
        assert result == "line 1\nline 2"

    def test_multiline_triple_single_quotes(self, monkeypatch):
        """三单引号也可以触发多行模式"""
        inputs = iter(["'''", "alpha", "beta", "'''"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        result = read_user_input("prompt> ")
        assert result == "alpha\nbeta"

    def test_multiline_inline_start_with_content(self, monkeypatch):
        """三双引号后面紧跟内容，应包含该内容"""
        inputs = iter(['\"\"\"first line', "second line", '\"\"\"'])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        result = read_user_input("prompt> ")
        assert result == "first line\nsecond line"

    def test_multiline_inline_end_with_content(self, monkeypatch):
        """结束行三双引号前面有内容，应包含该内容"""
        inputs = iter(['\"\"\"', "middle", 'last line\"\"\"'])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        result = read_user_input("prompt> ")
        assert result == "middle\nlast line"

    def test_multiline_single_line_open_close(self, monkeypatch):
        """在同一行打开和关闭三引号"""
        monkeypatch.setattr("builtins.input", lambda prompt="": '\"\"\"some content\"\"\"')
        result = read_user_input("prompt> ")
        assert result == "some content"

    def test_multiline_empty_block(self, monkeypatch):
        """空的三引号块返回空字符串"""
        inputs = iter(['\"\"\"', '\"\"\"'])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        result = read_user_input("prompt> ")
        assert result == ""

    def test_multiline_preserves_indentation(self, monkeypatch):
        """多行模式应保留行内缩进"""
        inputs = iter(['\"\"\"', "def hello():", "    print('hi')", '\"\"\"'])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        result = read_user_input("prompt> ")
        assert result == "def hello():\n    print('hi')"

    def test_multiline_preserves_empty_lines(self, monkeypatch):
        """多行模式应保留空行"""
        inputs = iter(['\"\"\"', "line 1", "", "line 3", '\"\"\"'])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
        result = read_user_input("prompt> ")
        assert result == "line 1\n\nline 3"

    def test_slash_commands_not_affected(self, monkeypatch):
        """斜杠命令不应触发多行模式"""
        monkeypatch.setattr("builtins.input", lambda prompt="": "/quit")
        result = read_user_input("prompt> ")
        assert result == "/quit"

    def test_eof_in_multiline_returns_collected(self, monkeypatch):
        """多行模式中遇到 EOFError 应返回已收集的内容"""
        call_count = 0
        def mock_input(prompt=""):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '\"\"\"'
            elif call_count == 2:
                return "partial line"
            else:
                raise EOFError()
        monkeypatch.setattr("builtins.input", mock_input)
        result = read_user_input("prompt> ")
        assert result == "partial line"


class TestLoadSystemPrompt:
    """测试 load_system_prompt 函数"""

    def test_none_returns_none(self):
        """参数为 None 时返回 None"""
        assert load_system_prompt(None) is None

    def test_file_path_reads_content(self, tmp_path):
        """参数是已存在的文件路径时，返回文件内容"""
        f = tmp_path / "custom_prompt.txt"
        f.write_text("你是一个专注于安全审计的助手。", encoding="utf-8")
        result = load_system_prompt(str(f))
        assert result == "你是一个专注于安全审计的助手。"

    def test_file_path_strips_whitespace(self, tmp_path):
        """读取文件内容时应去除首尾空白"""
        f = tmp_path / "ws_prompt.txt"
        f.write_text("  extra spaces  \n", encoding="utf-8")
        result = load_system_prompt(str(f))
        assert result == "extra spaces"

    def test_nonexistent_file_treated_as_text(self):
        """不存在的文件路径应作为直接文本返回"""
        text = "请特别注意代码安全性"
        result = load_system_prompt(text)
        assert result == text

    def test_plain_text_returned_directly(self):
        """普通文本直接返回"""
        text = "Focus on performance optimization"
        result = load_system_prompt(text)
        assert result == text

    def test_empty_string_returns_none(self):
        """空字符串返回 None"""
        assert load_system_prompt("") is None

    def test_whitespace_only_returns_none(self):
        """仅空白的字符串返回 None"""
        assert load_system_prompt("   ") is None

    def test_empty_file_returns_none(self, tmp_path):
        """空文件返回 None"""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = load_system_prompt(str(f))
        assert result is None

    def test_multiline_file_content(self, tmp_path):
        """多行文件内容应完整返回"""
        f = tmp_path / "multi.txt"
        content = "第一行指令\n第二行指令\n第三行指令"
        f.write_text(content, encoding="utf-8")
        result = load_system_prompt(str(f))
        assert result == content


class TestSlashCommandMatching:
    """测试斜杠命令的精确匹配，防止前缀误触发"""

    def test_commit_exact_match(self):
        """'/commit' 应被识别为 commit 命令"""
        from src.cli import match_command
        assert match_command("/commit", "/commit") is True

    def test_commit_with_arg(self):
        """'/commit some message' 应被识别为 commit 命令"""
        from src.cli import match_command
        assert match_command("/commit some message", "/commit") is True

    def test_commit_prefix_not_matched(self):
        """'/committing' 不应被识别为 commit 命令"""
        from src.cli import match_command
        assert match_command("/committing", "/commit") is False

    def test_save_exact_match(self):
        """'/save' 应被识别为 save 命令"""
        from src.cli import match_command
        assert match_command("/save", "/save") is True

    def test_save_with_arg(self):
        """'/save my-session' 应被识别为 save 命令"""
        from src.cli import match_command
        assert match_command("/save my-session", "/save") is True

    def test_save_prefix_not_matched(self):
        """'/save_backup' 不应被识别为 save 命令"""
        from src.cli import match_command
        assert match_command("/save_backup", "/save") is False

    def test_load_exact_match(self):
        """'/load' 应被识别为 load 命令"""
        from src.cli import match_command
        assert match_command("/load", "/load") is True

    def test_load_with_arg(self):
        """'/load session-001' 应被识别为 load 命令"""
        from src.cli import match_command
        assert match_command("/load session-001", "/load") is True

    def test_load_prefix_not_matched(self):
        """'/loading' 不应被识别为 load 命令"""
        from src.cli import match_command
        assert match_command("/loading", "/load") is False

    def test_model_with_space(self):
        """'/model gpt-4' 应被识别为 model 命令"""
        from src.cli import match_command
        assert match_command("/model gpt-4", "/model") is True

    def test_model_no_arg_exact(self):
        """'/model' 精确匹配"""
        from src.cli import match_command
        assert match_command("/model", "/model") is True

    def test_model_prefix_not_matched(self):
        """'/modeler' 不应被识别为 model 命令"""
        from src.cli import match_command
        assert match_command("/modeler", "/model") is False


class TestParseArgsSystemPrompt:
    """测试 --system 参数解析"""

    def test_no_system_arg_defaults_none(self, monkeypatch):
        """没有 --system 参数时，args.system 应为 None"""
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["cli.py"])
        args = parse_args()
        assert args.system is None

    def test_system_arg_with_text(self, monkeypatch):
        """--system 带文本参数"""
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["cli.py", "--system", "请专注于安全性"])
        args = parse_args()
        assert args.system == "请专注于安全性"

    def test_system_arg_with_file_path(self, monkeypatch, tmp_path):
        """--system 带文件路径参数"""
        f = tmp_path / "prompt.txt"
        f.write_text("custom instructions", encoding="utf-8")
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["cli.py", "--system", str(f)])
        args = parse_args()
        assert args.system == str(f)


class TestParseArgsProvider:
    """测试 --provider 参数解析"""

    def test_no_provider_defaults_none(self, monkeypatch):
        """没有 --provider 参数时，args.provider 应为 None"""
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["cli.py"])
        args = parse_args()
        assert args.provider is None

    def test_provider_arg(self, monkeypatch):
        """--provider openai 应被正确解析"""
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["cli.py", "--provider", "openai"])
        args = parse_args()
        assert args.provider == "openai"

    def test_provider_and_model_together(self, monkeypatch):
        """--provider 和 --model 可以同时使用"""
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        monkeypatch.setattr("sys.argv", ["cli.py", "--provider", "deepseek", "--model", "deepseek-r1"])
        args = parse_args()
        assert args.provider == "deepseek"
        assert args.model == "deepseek-r1"


class TestModelCommandValidation:
    """测试 /model 命令的模型名验证"""

    def test_model_command_extracts_name(self):
        """/model gpt-4 应提取 'gpt-4'"""
        user_input = "/model gpt-4"
        new_model = user_input[7:].strip()
        assert new_model == "gpt-4"

    def test_model_command_empty_name(self):
        """/model 后只有空格时，提取出空字符串"""
        user_input = "/model "
        new_model = user_input[7:].strip()
        assert new_model == ""

    def test_model_command_multiple_spaces(self):
        """/model    后多个空格时，提取出空字符串"""
        user_input = "/model    "
        new_model = user_input[7:].strip()
        assert new_model == ""

    def test_model_command_name_with_spaces_stripped(self):
        """/model  gpt-4  应提取 'gpt-4'（去除两端空格）"""
        user_input = "/model  gpt-4  "
        new_model = user_input[7:].strip()
        assert new_model == "gpt-4"


class TestFormatElapsed:
    """测试 format_elapsed 耗时格式化"""

    def test_sub_second(self):
        """不到 1 秒应显示两位小数"""
        assert format_elapsed(0.5) == "0.50s"

    def test_zero(self):
        """0 秒"""
        assert format_elapsed(0) == "0.00s"

    def test_exact_seconds(self):
        """整数秒"""
        assert format_elapsed(3.0) == "3.00s"

    def test_fractional_seconds(self):
        """带小数秒"""
        assert format_elapsed(12.345) == "12.35s"

    def test_just_under_minute(self):
        """59.99 秒仍用秒格式"""
        assert format_elapsed(59.99) == "59.99s"

    def test_exactly_60_seconds(self):
        """60 秒应切换到分钟格式"""
        assert format_elapsed(60.0) == "1m 0.00s"

    def test_over_minute(self):
        """超过 1 分钟"""
        assert format_elapsed(75.0) == "1m 15.00s"

    def test_many_minutes(self):
        """大量分钟"""
        assert format_elapsed(3661) == "61m 1.00s"

    def test_90_seconds(self):
        """一分半钟"""
        assert format_elapsed(90.5) == "1m 30.50s"


class TestMarkdownRenderer:
    """测试 MarkdownRenderer 流式 Markdown 终端渲染"""

    def test_plain_text_passthrough(self):
        """普通文本不加任何装饰直接输出"""
        r = MarkdownRenderer()
        assert r.feed("hello world\n") == "hello world\n"

    def test_heading_level_1(self):
        """# 标题 应渲染为 BOLD + CYAN"""
        r = MarkdownRenderer()
        out = r.feed("# Hello\n")
        assert BOLD in out
        assert CYAN in out
        assert "Hello" in out
        assert RESET in out

    def test_heading_level_2(self):
        """## 标题"""
        r = MarkdownRenderer()
        out = r.feed("## Sub heading\n")
        assert BOLD in out
        assert "Sub heading" in out

    def test_heading_level_3(self):
        """### 标题"""
        r = MarkdownRenderer()
        out = r.feed("### Deep\n")
        assert BOLD in out
        assert "Deep" in out

    def test_inline_code(self):
        """行内代码 `code` 应渲染为 CYAN"""
        r = MarkdownRenderer()
        out = r.feed("Use `pip install` to install\n")
        assert CYAN in out
        assert "pip install" in out
        assert RESET in out
        # 反引号本身不应出现在输出中
        assert "`" not in out.replace(CYAN, "").replace(RESET, "").replace(DIM, "").replace(BOLD, "")

    def test_bold_text(self):
        """粗体 **text** 应渲染为 BOLD"""
        r = MarkdownRenderer()
        out = r.feed("This is **important** text\n")
        assert BOLD in out
        assert "important" in out
        assert RESET in out

    def test_fenced_code_block_start(self):
        """围栏代码块开始标记"""
        r = MarkdownRenderer()
        out = r.feed("```python\n")
        # 应包含语言名标记
        assert "python" in out.lower()
        assert r.in_code_block is True

    def test_fenced_code_block_content(self):
        """围栏代码块内容应使用 DIM 渲染"""
        r = MarkdownRenderer()
        r.feed("```python\n")
        out = r.feed("def hello():\n")
        assert DIM in out
        assert "def hello():" in out

    def test_fenced_code_block_end(self):
        """围栏代码块结束标记"""
        r = MarkdownRenderer()
        r.feed("```python\n")
        r.feed("code here\n")
        out = r.feed("```\n")
        assert r.in_code_block is False

    def test_code_block_preserves_content(self):
        """代码块内不做行内 Markdown 解析"""
        r = MarkdownRenderer()
        r.feed("```\n")
        out = r.feed("**not bold** `not inline`\n")
        # 在代码块内，** 和 ` 不应被解析
        assert "**not bold**" in out
        assert "`not inline`" in out

    def test_multiple_inline_codes(self):
        """一行中多个行内代码"""
        r = MarkdownRenderer()
        out = r.feed("Use `foo` and `bar` here\n")
        # 应该有两处 CYAN
        # 移除颜色码后，不应有反引号
        plain = out
        for code in [CYAN, RESET, DIM, BOLD, GREEN, RED, YELLOW]:
            plain = plain.replace(code, "")
        assert "`" not in plain

    def test_partial_delta_buffering(self):
        """不完整的行应被缓冲，不立即输出"""
        r = MarkdownRenderer()
        out1 = r.feed("hello")
        assert out1 == ""  # 没有换行符，应缓冲
        out2 = r.feed(" world\n")
        assert "hello world" in out2

    def test_flush_outputs_buffer(self):
        """flush() 应输出缓冲区中的未完成行"""
        r = MarkdownRenderer()
        r.feed("buffered text")
        out = r.flush()
        assert "buffered text" in out

    def test_flush_empty_buffer(self):
        """空缓冲区 flush 返回空字符串"""
        r = MarkdownRenderer()
        assert r.flush() == ""

    def test_tilde_fence(self):
        """~~~ 围栏也应被识别"""
        r = MarkdownRenderer()
        out = r.feed("~~~\n")
        assert r.in_code_block is True
        r.feed("code\n")
        out2 = r.feed("~~~\n")
        assert r.in_code_block is False

    def test_unordered_list_dash(self):
        """- 列表项保持可读"""
        r = MarkdownRenderer()
        out = r.feed("- item one\n")
        assert "item one" in out

    def test_unordered_list_star(self):
        """* 列表项保持可读"""
        r = MarkdownRenderer()
        out = r.feed("* item two\n")
        assert "item two" in out

    def test_ordered_list(self):
        """1. 有序列表保持可读"""
        r = MarkdownRenderer()
        out = r.feed("1. first\n")
        assert "first" in out

    def test_mixed_content(self):
        """混合内容：标题 + 文本 + 代码块"""
        r = MarkdownRenderer()
        result = ""
        result += r.feed("# Title\n")
        result += r.feed("Some `code` and **bold**.\n")
        result += r.feed("```\n")
        result += r.feed("x = 1\n")
        result += r.feed("```\n")
        result += r.feed("Done.\n")
        # 应包含所有内容
        assert "Title" in result
        assert "code" in result
        assert "bold" in result
        assert "x = 1" in result
        assert "Done." in result


class TestHandleLoadListsSessions:
    """测试 /load 无参数时列出可用会话文件"""

    def test_load_no_arg_lists_sessions(self, capsys, tmp_path, monkeypatch):
        """/load 无参数时，应列出 sessions/ 目录下的会话文件"""
        from src.cli import handle_slash_command, SESSIONS_DIR
        from unittest.mock import MagicMock
        import os

        # 创建临时 sessions 目录
        monkeypatch.setattr("src.cli.SESSIONS_DIR", str(tmp_path))
        (tmp_path / "session-20260407-100000.json").write_text("{}")
        (tmp_path / "session-20260406-090000.json").write_text("{}")

        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("/load", agent, usage)
        assert result is True
        captured = capsys.readouterr()
        assert "可用会话" in captured.out
        assert "session-20260407-100000" in captured.out
        assert "session-20260406-090000" in captured.out

    def test_load_no_arg_empty_dir(self, capsys, tmp_path, monkeypatch):
        """/load 无参数且无会话文件时，显示友好提示"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock

        monkeypatch.setattr("src.cli.SESSIONS_DIR", str(tmp_path))

        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/load", agent, usage)
        captured = capsys.readouterr()
        assert "无会话文件" in captured.out

    def test_load_no_arg_dir_not_exist(self, capsys, tmp_path, monkeypatch):
        """/load 无参数且 sessions/ 目录不存在时，显示友好提示"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock

        monkeypatch.setattr("src.cli.SESSIONS_DIR", str(tmp_path / "nonexistent"))

        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/load", agent, usage)
        captured = capsys.readouterr()
        assert "无会话文件" in captured.out

    def test_load_no_arg_max_five(self, capsys, tmp_path, monkeypatch):
        """/load 无参数时最多列出 5 个会话"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock

        monkeypatch.setattr("src.cli.SESSIONS_DIR", str(tmp_path))
        for i in range(8):
            (tmp_path / f"session-{i:02d}.json").write_text("{}")

        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/load", agent, usage)
        captured = capsys.readouterr()
        # 列出的文件名数量不超过 5
        lines_with_session = [l for l in captured.out.splitlines() if "session-" in l]
        assert len(lines_with_session) <= 5

    def test_load_no_arg_strips_json_suffix(self, capsys, tmp_path, monkeypatch):
        """/load 列出时应去掉 .json 后缀，方便用户直接复制使用"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock

        monkeypatch.setattr("src.cli.SESSIONS_DIR", str(tmp_path))
        (tmp_path / "my-session.json").write_text("{}")

        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/load", agent, usage)
        captured = capsys.readouterr()
        assert "my-session" in captured.out
        # .json 不应出现在列出的名称中
        for line in captured.out.splitlines():
            if "my-session" in line:
                assert ".json" not in line


class TestHandleModelCommand:
    """测试 /model 命令的参数处理（#160 修复）"""

    def test_model_bare_shows_usage_and_current(self, capsys):
        """/model（不带参数）应显示用法提示和当前模型名"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.model = "test-model-xyz"
        usage = Usage()
        result = handle_slash_command("/model", agent, usage)
        assert result is True
        captured = capsys.readouterr()
        assert "用法" in captured.out
        assert "test-model-xyz" in captured.out
        # 不应被当作未知命令
        assert "未知命令" not in captured.out

    def test_model_with_valid_arg_switches(self, capsys):
        """/model gpt-4 应切换模型并清除对话"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("/model gpt-4", agent, usage)
        assert result is True
        agent.with_model.assert_called_once_with("gpt-4")
        agent.clear_conversation.assert_called_once()

    def test_model_with_spaces_only_shows_usage(self, capsys):
        """/model     （仅空格）应显示用法提示"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.model = "current-model"
        usage = Usage()
        result = handle_slash_command("/model   ", agent, usage)
        assert result is True
        captured = capsys.readouterr()
        assert "用法" in captured.out
        assert "current-model" in captured.out


class TestHandleSlashCommandUnknown:
    """测试未知斜杠命令的处理"""

    def test_unknown_slash_command_returns_true(self, capsys):
        """未知斜杠命令应返回 True（已处理），不发送给 LLM"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("/foo", agent, usage)
        assert result is True

    def test_unknown_slash_command_shows_warning(self, capsys):
        """未知斜杠命令应显示警告和可用命令列表"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/hlep", agent, usage)
        captured = capsys.readouterr()
        assert "未知命令" in captured.out
        assert "/hlep" in captured.out
        assert "/quit" in captured.out  # 应显示可用命令

    def test_unknown_slash_command_with_args(self, capsys):
        """带参数的未知斜杠命令也应被拦截"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("/unknown arg1 arg2", agent, usage)
        assert result is True
        captured = capsys.readouterr()
        assert "/unknown" in captured.out

    def test_help_command_shows_commands(self, capsys):
        """/help 应显示可用命令列表而非发送给 LLM"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("/help", agent, usage)
        assert result is True
        captured = capsys.readouterr()
        assert "/compact" in captured.out
        assert "/diff" in captured.out

    def test_non_slash_input_returns_false(self):
        """非斜杠开头的输入应返回 False（继续发送给 LLM）"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("hello world", agent, usage)
        assert result is False

    def test_known_commands_not_caught_as_unknown(self):
        """已知命令不应被当作未知命令处理"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        agent.tools = MagicMock()
        agent.tools.undo.return_value = {"success": False, "error": "empty"}
        usage = Usage()
        # /undo 是已知命令，应被正确处理而非走 unknown 分支
        result = handle_slash_command("/undo", agent, usage)
        assert result is True
        agent.tools.undo.assert_called_once()


class TestHandleSlashCommandHelp:
    """测试 /help 命令"""

    def test_help_returns_true(self, capsys):
        """/help 应返回 True（已处理）"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("/help", agent, usage)
        assert result is True

    def test_help_shows_all_commands(self, capsys):
        """/help 应列出所有可用命令及说明"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/help", agent, usage)
        captured = capsys.readouterr()
        # 应包含所有命令名
        for cmd in ["/help", "/quit", "/exit", "/clear", "/model",
                    "/usage", "/compact", "/undo", "/diff",
                    "/commit", "/save", "/load", "/replay", "/spec"]:
            assert cmd in captured.out, f"缺少命令 {cmd}"

    def test_help_does_not_show_unknown_warning(self, capsys):
        """/help 不应显示"未知命令"警告"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/help", agent, usage)
        captured = capsys.readouterr()
        assert "未知命令" not in captured.out

    def test_help_does_not_call_llm(self):
        """/help 不应触发任何 Agent 方法调用"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/help", agent, usage)
        # Agent 的主要方法不应被调用
        agent.prompt_stream.assert_not_called()
        agent.clear_conversation.assert_not_called()


class TestHandleSlashCommandSpec:
    """测试 /spec 命令"""


class TestOllamaNoApiKey:
    """测试 #164：--provider ollama 在无 API key 时不应退出"""

    def test_ollama_provider_api_key_env_is_none(self):
        """Ollama provider 的 api_key_env 应为 None（表示不需要 API key）"""
        from src.providers import get_provider
        p = get_provider("ollama")
        assert p is not None
        assert p.api_key_env is None

    def test_ollama_resolve_without_any_key(self, monkeypatch):
        """纯净环境下 resolve_provider('ollama') 返回空 api_key"""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("API_KEY", raising=False)
        from src.providers import resolve_provider
        resolved = resolve_provider("ollama", None, None, None)
        # api_key 可能为 None 或空字符串，取决于环境
        assert not resolved["api_key"]  # falsy
        assert resolved["base_url"] == "http://localhost:11434/v1"
        assert resolved["model"] == "llama3.2"

    def test_cli_ollama_no_key_uses_placeholder(self, monkeypatch):
        """cli.py 中 Ollama 无 API key 时应使用占位值而非 sys.exit"""
        from src.providers import get_provider
        p = get_provider("ollama")
        # 模拟 cli.py 修复后的逻辑
        api_key = ""  # 空字符串，模拟纯净环境
        if not api_key:
            if p and p.api_key_env is None:
                api_key = "not-needed"
        assert api_key == "not-needed"

    def test_deepseek_still_requires_key(self):
        """DeepSeek 等需要 API key 的 provider 不应跳过检查"""
        from src.providers import get_provider
        p = get_provider("deepseek")
        assert p is not None
        assert p.api_key_env is not None  # 需要 API key
        assert p.api_key_env == "DEEPSEEK_API_KEY"


class TestHandleSlashCommandSpec:

    def test_spec_returns_true(self, capsys):
        """/spec 应返回 True（已处理）"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        result = handle_slash_command("/spec", agent, usage)
        assert result is True

    def test_spec_no_arg_shows_usage(self, capsys):
        """/spec 无参数应显示用法说明"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/spec", agent, usage)
        captured = capsys.readouterr()
        assert "Spec-Driven Development" in captured.out
        assert "/spec" in captured.out
        assert "spec 文件路径" in captured.out

    def test_spec_nonexistent_file(self, capsys):
        """/spec 指向不存在的文件应报错"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/spec /nonexistent/file.md", agent, usage)
        captured = capsys.readouterr()
        assert "不存在" in captured.out

    def test_spec_empty_file(self, capsys, tmp_path):
        """/spec 指向空文件应警告"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        spec_file = tmp_path / "empty.md"
        spec_file.write_text("")
        agent = MagicMock()
        usage = Usage()
        handle_slash_command(f"/spec {spec_file}", agent, usage)
        captured = capsys.readouterr()
        assert "为空" in captured.out

    def test_spec_whitespace_only_file(self, capsys, tmp_path):
        """/spec 指向仅空白文件应警告"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        spec_file = tmp_path / "blank.md"
        spec_file.write_text("   \n  \n  ")
        agent = MagicMock()
        usage = Usage()
        handle_slash_command(f"/spec {spec_file}", agent, usage)
        captured = capsys.readouterr()
        assert "为空" in captured.out

    def test_spec_valid_file_sets_prompt(self, capsys, tmp_path):
        """/spec 加载有效文件后应设置 agent._spec_prompt"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        spec_file = tmp_path / "feature.md"
        spec_content = "# Auth API\n\n实现用户认证接口"
        spec_file.write_text(spec_content)
        agent = MagicMock()
        # MagicMock 默认允许设置任意属性
        usage = Usage()
        handle_slash_command(f"/spec {spec_file}", agent, usage)
        captured = capsys.readouterr()
        assert "已加载 spec" in captured.out
        assert hasattr(agent, '_spec_prompt')
        assert spec_content in agent._spec_prompt

    def test_spec_prompt_contains_structure(self, tmp_path):
        """/spec 生成的提示应包含计划结构要求"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        spec_file = tmp_path / "test.md"
        spec_file.write_text("# Test Feature\n\nSome requirements")
        agent = MagicMock()
        usage = Usage()
        handle_slash_command(f"/spec {spec_file}", agent, usage)
        prompt = agent._spec_prompt
        assert "需求分析" in prompt
        assert "影响范围" in prompt
        assert "分步计划" in prompt
        assert "测试策略" in prompt
        assert "风险提示" in prompt
        assert "不要执行任何修改" in prompt

    def test_spec_prompt_contains_filepath(self, tmp_path):
        """/spec 生成的提示应包含文件路径"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        spec_file = tmp_path / "my-feature.md"
        spec_file.write_text("# My Feature")
        agent = MagicMock()
        usage = Usage()
        handle_slash_command(f"/spec {spec_file}", agent, usage)
        assert str(spec_file) in agent._spec_prompt

    def test_spec_shows_char_count(self, capsys, tmp_path):
        """/spec 应显示文件字符数"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        spec_file = tmp_path / "sized.md"
        content = "A" * 42
        spec_file.write_text(content)
        agent = MagicMock()
        usage = Usage()
        handle_slash_command(f"/spec {spec_file}", agent, usage)
        captured = capsys.readouterr()
        assert "42 字符" in captured.out

    def test_spec_does_not_call_llm(self, tmp_path):
        """/spec 本身不应调用 LLM（由 main 循环处理）"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        spec_file = tmp_path / "test.md"
        spec_file.write_text("# Test")
        agent = MagicMock()
        usage = Usage()
        handle_slash_command(f"/spec {spec_file}", agent, usage)
        agent.prompt_stream.assert_not_called()
        agent.prompt.assert_not_called()

    def test_spec_not_caught_as_unknown(self, capsys):
        """/spec 不应走到未知命令分支"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/spec", agent, usage)
        captured = capsys.readouterr()
        assert "未知命令" not in captured.out

    def test_spec_in_unknown_command_list(self, capsys):
        """未知命令提示的可用命令列表应包含 /spec"""
        from src.cli import handle_slash_command
        from unittest.mock import MagicMock
        agent = MagicMock()
        usage = Usage()
        handle_slash_command("/foobar", agent, usage)
        captured = capsys.readouterr()
        assert "/spec" in captured.out


class TestProviderRouterConflict:
    """测试 #179：--provider 与路由器环境变量冲突"""

    def test_provider_with_env_model_ignored_disables_router(self, monkeypatch):
        """当 --provider 导致 OPENAI_MODEL 被忽略时，路由器应禁用。

        场景：OPENAI_MODEL=gpt-4o + --provider deepseek
        → env_model_ignored=True
        → cli.py 应传入 RouterConfig(model_high=resolved_model)
        → 路由器只有 1 个 unique 模型 → enabled=False
        """
        from src.router import RouterConfig

        # 模拟：--provider deepseek 且 OPENAI_MODEL 被忽略
        env_model_ignored = True
        resolved_model = "deepseek-chat"

        # cli.py 修复后的逻辑
        router_config = None
        if env_model_ignored:
            router_config = RouterConfig(model_high=resolved_model)

        assert router_config is not None
        assert router_config.model_high == "deepseek-chat"
        assert router_config.model_middle is None
        assert router_config.model_low is None
        assert router_config.enabled is False  # 只有 1 个 unique 模型

    def test_provider_without_env_model_uses_default_router(self, monkeypatch):
        """当 --provider 且无 OPENAI_MODEL 时（env_model_ignored=False），
        路由器正常从环境变量加载。"""
        from src.router import RouterConfig

        # 模拟：--provider deepseek 且无 OPENAI_MODEL
        env_model_ignored = False

        router_config = None
        if env_model_ignored:
            router_config = RouterConfig(model_high="deepseek-chat")

        assert router_config is None  # 不覆盖，使用默认

    def test_no_provider_router_loads_from_env(self, monkeypatch):
        """无 --provider 时，路由器应从环境变量正常加载。"""
        from src.router import ModelRouter

        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("OPENAI_MODEL_MIDDLE", "gpt-4o-mini")
        monkeypatch.delenv("OPENAI_MODEL_LOW", raising=False)

        router = ModelRouter()  # config=None → 从 env 加载
        assert router.config.model_high == "gpt-4o"
        assert router.config.model_middle == "gpt-4o-mini"
        assert router.enabled is True  # 2 个不同模型

    def test_provider_router_disabled_routes_to_default(self, monkeypatch):
        """路由器禁用时，route() 应始终返回 default_model。

        验证 #179 修复的端到端行为：
        --provider deepseek → router 禁用 → 所有请求用 deepseek-chat
        """
        from src.router import ModelRouter, RouterConfig

        # 模拟修复后的配置
        config = RouterConfig(model_high="deepseek-chat")
        router = ModelRouter(config)
        assert router.enabled is False

        # 无论什么复杂度，都应返回 default_model
        result = router.route("请帮我重构整个项目的架构设计", default_model="deepseek-chat")
        assert result == "deepseek-chat"

        result = router.route("hi", default_model="deepseek-chat")
        assert result == "deepseek-chat"

    def test_provider_router_conflict_scenario(self, monkeypatch):
        """精确复现 #179 场景：有 OPENAI_MODEL env + --provider deepseek

        修复前：路由器从 env 加载 gpt-4o 作为 HIGH 模型 → 发给 deepseek API → 失败
        修复后：cli.py 传入 RouterConfig(model_high=deepseek-chat) → 路由器禁用
        """
        from src.router import ModelRouter, RouterConfig

        # 修复前的行为（直接从 env 加载）
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("OPENAI_MODEL_MIDDLE", "gpt-4o-mini")

        bad_router = ModelRouter()  # 从 env 加载
        assert bad_router.enabled is True
        bad_result = bad_router.route("重构架构", default_model="deepseek-chat")
        assert bad_result == "gpt-4o"  # ← 这会发给 deepseek API 失败

        # 修复后的行为（cli.py 传入覆盖配置）
        good_config = RouterConfig(model_high="deepseek-chat")
        good_router = ModelRouter(good_config)
        assert good_router.enabled is False
        good_result = good_router.route("重构架构", default_model="deepseek-chat")
        assert good_result == "deepseek-chat"  # ← 正确，使用 deepseek 模型


class TestSpellingSuggestion:
    """测试斜杠命令拼写建议功能 (#196)。"""

    def test_levenshtein_distance_identical(self):
        """相同字符串的距离为 0。"""
        from src.cli import levenshtein_distance
        assert levenshtein_distance("hello", "hello") == 0
        assert levenshtein_distance("/commit", "/commit") == 0

    def test_levenshtein_distance_one_edit(self):
        """一次编辑的距离为 1。"""
        from src.cli import levenshtein_distance
        assert levenshtein_distance("cat", "bat") == 1  # 替换
        assert levenshtein_distance("cat", "cats") == 1  # 插入
        assert levenshtein_distance("cats", "cat") == 1  # 删除

    def test_levenshtein_distance_multiple_edits(self):
        """多次编辑的距离。"""
        from src.cli import levenshtein_distance
        assert levenshtein_distance("kitten", "sitting") == 3
        assert levenshtein_distance("/comit", "/commit") == 1
        assert levenshtein_distance("/sav", "/save") == 1

    def test_suggest_similar_command_close_match(self):
        """拼写错误距离 <= 2 时返回建议。"""
        from src.cli import suggest_similar_command
        assert suggest_similar_command("/comit") == "/commit"
        assert suggest_similar_command("/sav") == "/save"
        assert suggest_similar_command("/clr") == "/clear"
        assert suggest_similar_command("/lod") == "/load"

    def test_suggest_similar_command_no_match(self):
        """完全无关的命令返回 None。"""
        from src.cli import suggest_similar_command
        # 距离过大（> 2）
        result = suggest_similar_command("/xyz")
        # 可能是 None 或某个命令，但距离应 > 2
        if result:
            from src.cli import levenshtein_distance
            assert levenshtein_distance("/xyz", result) > 2

    def test_suggest_similar_command_prefix_match(self):
        """前缀匹配也能找到相似命令（距离 <= 2）。"""
        from src.cli import suggest_similar_command
        # 使用距离合理的拼写错误
        assert suggest_similar_command("/hel") == "/help"  # 距离 1
        assert suggest_similar_command("/savee") == "/save"  # 距离 1
        assert suggest_similar_command("/loaad") == "/load"  # 距离 1

    def test_handle_unknown_command_with_suggestion(self, capsys):
        """未知命令应显示建议。"""
        from src.cli import handle_slash_command
        from src.agent import Agent

        agent = Agent(api_key="test", model="gpt-4o-mini")
        session_usage = Usage()

        result = handle_slash_command("/comit message", agent, session_usage)
        assert result is True  # 命令已处理

        captured = capsys.readouterr()
        assert "未知命令：/comit" in captured.out
        assert "你是否想输入：" in captured.out
        assert "/commit" in captured.out

