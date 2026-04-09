"""tests/test_prompt.py — 提示词构建模块测试"""

import os
from src.prompt import read_prompt_file, render_prompt_context, build_system_prompt, PROMPT_CONTEXT_FILES, detect_project_info, check_context_truncation, emit_truncation_warnings, _TRUNCATION_WARN_RATIO
from src.skills import SkillSet


class TestReadPromptFile:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("hello world", encoding="utf-8")
        result = read_prompt_file(str(f), 1000)
        assert result == "hello world"

    def test_read_nonexistent_file(self):
        result = read_prompt_file("/nonexistent/xyz.md", 1000)
        assert "不存在" in result

    def test_truncation(self, tmp_path):
        f = tmp_path / "long.md"
        f.write_text("a" * 500, encoding="utf-8")
        result = read_prompt_file(str(f), 100)
        assert len(result) < 200  # 截断 + 标记
        assert "已截断" in result

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        result = read_prompt_file(str(f), 1000)
        assert "空文件" in result

    def test_whitespace_only_file(self, tmp_path):
        f = tmp_path / "ws.md"
        f.write_text("   \n  \n  ", encoding="utf-8")
        result = read_prompt_file(str(f), 1000)
        assert "空文件" in result

    def test_reverse_truncation_takes_tail(self, tmp_path):
        """倒序截断应取文件尾部内容"""
        f = tmp_path / "log.md"
        f.write_text("第一行\n第二行\n第三行\n第四行\n第五行", encoding="utf-8")
        # 19 字符总长，max_chars=10 会触发截断
        result = read_prompt_file(str(f), 10, reverse=True)
        assert "第五行" in result
        assert "前文已截断" in result

    def test_reverse_truncation_cuts_at_newline(self, tmp_path):
        """倒序截断应在换行处切断，不截断段落中间"""
        f = tmp_path / "log.md"
        # 每行约 10 字符
        lines = [f"Line-{i:04d}" for i in range(100)]
        content = "\n".join(lines)
        f.write_text(content, encoding="utf-8")
        result = read_prompt_file(str(f), 50, reverse=True)
        # 应以完整行开头（可能有 "...[前文已截断]" 前缀后跟完整行）
        body = result.replace("...[前文已截断]\n", "")
        # 每行都应该是完整的 Line-XXXX 格式
        for line in body.strip().split("\n"):
            assert line.startswith("Line-"), f"不完整的行: {line!r}"

    def test_reverse_truncation_no_truncation_needed(self, tmp_path):
        """文件足够小时，即使设置 reverse=True 也不应截断"""
        f = tmp_path / "small.md"
        f.write_text("短内容", encoding="utf-8")
        result = read_prompt_file(str(f), 1000, reverse=True)
        assert result == "短内容"
        assert "截断" not in result

    def test_forward_truncation_takes_head(self, tmp_path):
        """正序截断应取文件头部内容"""
        f = tmp_path / "doc.md"
        f.write_text("第一行\n第二行\n第三行\n第四行\n第五行", encoding="utf-8")
        # 19 字符总长，max_chars=10 会触发截断
        result = read_prompt_file(str(f), 10, reverse=False)
        assert "第一行" in result
        assert "已截断" in result

    def test_reverse_truncation_shows_latest_journal_entries(self, tmp_path):
        """模拟真实 JOURNAL.md：倒序截断应展示最新日志条目"""
        entries = []
        for i in range(1, 20):
            entries.append(f"## 第 {i} 次 — 改进 {i}\n\n这是第 {i} 次改进的详细说明。\n")
        content = "\n".join(entries)
        f = tmp_path / "journal.md"
        f.write_text(content, encoding="utf-8")
        result = read_prompt_file(str(f), 200, reverse=True)
        # 应包含最新的条目（第 19 次）
        assert "第 19 次" in result
        # 不应包含最早的条目（第 1 次）
        assert "第 1 次" not in result


class TestPromptContextFiles:
    def test_is_list_of_tuples(self):
        assert isinstance(PROMPT_CONTEXT_FILES, list)
        for item in PROMPT_CONTEXT_FILES:
            assert len(item) == 4
            title, path, max_chars, reverse = item
            assert isinstance(title, str)
            assert isinstance(path, str)
            assert isinstance(max_chars, int)
            assert max_chars > 0
            assert isinstance(reverse, bool)

    def test_learnings_max_chars_sufficient(self):
        """LEARNINGS.md 截断上限应至少为 4000，确保学习记录可见率足够"""
        learnings_entry = [e for e in PROMPT_CONTEXT_FILES if e[1] == "LEARNINGS.md"]
        assert len(learnings_entry) == 1
        _, _, max_chars, _ = learnings_entry[0]
        assert max_chars >= 4000

    def test_claude_md_max_chars_sufficient(self):
        """CLAUDE.md 截断上限应至少为 5000，确保"当前演进重点"章节不被截断"""
        claude_entry = [e for e in PROMPT_CONTEXT_FILES if e[1] == "CLAUDE.md"]
        assert len(claude_entry) == 1
        _, _, max_chars, _ = claude_entry[0]
        assert max_chars >= 5000

    def test_roadmap_max_chars_sufficient(self):
        """ROADMAP.md 截断上限应至少为 6000，确保级别4和终极挑战章节不被截断"""
        roadmap_entry = [e for e in PROMPT_CONTEXT_FILES if e[1] == "ROADMAP.md"]
        assert len(roadmap_entry) == 1
        _, _, max_chars, _ = roadmap_entry[0]
        assert max_chars >= 6000

    def test_readme_max_chars_sufficient(self):
        """README.md 截断上限应至少为 6000，确保完整内容（含项目结构、许可证）不被截断"""
        readme_entry = [e for e in PROMPT_CONTEXT_FILES if e[1] == "README.md"]
        assert len(readme_entry) == 1
        _, _, max_chars, _ = readme_entry[0]
        assert max_chars >= 6000

    def test_journal_uses_forward_truncation(self):
        """JOURNAL.md 最新条目在头部（prepend 方式），应使用正序截断以保留最新日志"""
        entry = [e for e in PROMPT_CONTEXT_FILES if e[1] == "JOURNAL.md"]
        assert len(entry) == 1
        _, _, _, reverse = entry[0]
        assert reverse is False

    def test_learnings_uses_reverse_truncation(self):
        """LEARNINGS.md 应使用倒序截断，确保模型看到最新学习记录"""
        entry = [e for e in PROMPT_CONTEXT_FILES if e[1] == "LEARNINGS.md"]
        assert len(entry) == 1
        _, _, _, reverse = entry[0]
        assert reverse is True

    def test_non_log_files_use_forward_truncation(self):
        """非日志型文件（IDENTITY.md、CLAUDE.md 等）应使用正序截断"""
        non_log_files = ["RUN_COUNT", "requirements.txt", "IDENTITY.md",
                         "CLAUDE.md", "ISSUES_TODAY.md", "ROADMAP.md", "README.md"]
        for filename in non_log_files:
            entry = [e for e in PROMPT_CONTEXT_FILES if e[1] == filename]
            assert len(entry) == 1, f"{filename} not found in PROMPT_CONTEXT_FILES"
            _, _, _, reverse = entry[0]
            assert reverse is False, f"{filename} should use forward truncation"


class TestDetectProjectInfo:
    """测试 detect_project_info 项目检测"""

    def test_python_requirements_txt(self, tmp_path):
        """检测到 requirements.txt 的 Python 项目"""
        (tmp_path / "requirements.txt").write_text("flask>=2.0\npytest", encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "Python" in info["languages"]
        assert "pip" in info["package_managers"]

    def test_python_pyproject_toml(self, tmp_path):
        """检测到 pyproject.toml 的 Python 项目"""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"myapp\"", encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "Python" in info["languages"]

    def test_python_setup_py(self, tmp_path):
        """检测到 setup.py 的 Python 项目"""
        (tmp_path / "setup.py").write_text("from setuptools import setup", encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "Python" in info["languages"]

    def test_node_package_json(self, tmp_path):
        """检测到 package.json 的 Node.js 项目"""
        (tmp_path / "package.json").write_text('{"name": "myapp", "scripts": {"test": "jest"}}', encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "Node.js" in info["languages"]
        assert "npm" in info["package_managers"]

    def test_rust_cargo_toml(self, tmp_path):
        """检测到 Cargo.toml 的 Rust 项目"""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "myapp"', encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "Rust" in info["languages"]
        assert "cargo" in info["package_managers"]

    def test_go_mod(self, tmp_path):
        """检测到 go.mod 的 Go 项目"""
        (tmp_path / "go.mod").write_text("module example.com/myapp", encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "Go" in info["languages"]

    def test_makefile(self, tmp_path):
        """检测到 Makefile"""
        (tmp_path / "Makefile").write_text("all:\n\techo hello", encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "make" in info["build_tools"]

    def test_pytest_ini(self, tmp_path):
        """检测到 pytest.ini 应识别 pytest 测试框架"""
        (tmp_path / "pytest.ini").write_text("[pytest]", encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "pytest" in info["test_frameworks"]

    def test_empty_dir(self, tmp_path):
        """空目录应返回空列表"""
        info = detect_project_info(str(tmp_path))
        assert info["languages"] == []
        assert info["package_managers"] == []
        assert info["test_frameworks"] == []
        assert info["build_tools"] == []

    def test_multi_language_project(self, tmp_path):
        """同时有多种语言的项目"""
        (tmp_path / "requirements.txt").write_text("flask", encoding="utf-8")
        (tmp_path / "package.json").write_text('{"name": "app"}', encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "Python" in info["languages"]
        assert "Node.js" in info["languages"]

    def test_returns_dict_with_expected_keys(self, tmp_path):
        """返回值应包含固定的 key 集合"""
        info = detect_project_info(str(tmp_path))
        assert "languages" in info
        assert "package_managers" in info
        assert "test_frameworks" in info
        assert "build_tools" in info

    def test_dockerfile_detected(self, tmp_path):
        """检测到 Dockerfile"""
        (tmp_path / "Dockerfile").write_text("FROM python:3.11", encoding="utf-8")
        info = detect_project_info(str(tmp_path))
        assert "docker" in info["build_tools"]

    def test_prompt_includes_project_info(self):
        """build_system_prompt 应包含项目检测信息"""
        prompt = build_system_prompt()
        # 当前项目是 Python + pytest，应能检测到
        assert "Python" in prompt
        assert "pytest" in prompt


class TestBuildSystemPrompt:
    def test_returns_string(self):
        prompt = build_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_contains_identity(self):
        prompt = build_system_prompt()
        assert "SimpleAgent" in prompt

    def test_contains_environment(self):
        prompt = build_system_prompt()
        assert "项目目录" in prompt
        assert "操作系统" in prompt
        assert "Python 版本" in prompt

    def test_contains_repo_context(self):
        """验证 build_system_prompt 包含仓库上下文文件"""
        prompt = build_system_prompt()
        # 至少应包含一些上下文文件标题
        assert "运行次数" in prompt or "RUN_COUNT" in prompt

    def test_empty_skills(self):
        prompt = build_system_prompt()
        assert "无已加载技能" in prompt

    def test_with_skills(self, tmp_path):
        skill_dir = tmp_path / "skills"
        d = skill_dir / "test-skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("description: 测试\n\n内容", encoding="utf-8")

        ss = SkillSet()
        ss.load([str(skill_dir)])
        prompt = build_system_prompt(skills=ss)
        assert "test-skill" in prompt
        assert "无已加载技能" not in prompt

    def test_with_extra_instructions(self):
        prompt = build_system_prompt(extra_instructions="请特别注意安全性")
        assert "请特别注意安全性" in prompt
        assert "### 额外指令\n" in prompt

    def test_no_extra_instructions_by_default(self):
        prompt = build_system_prompt()
        assert "### 额外指令\n" not in prompt


class TestCheckContextTruncation:
    """测试 check_context_truncation 截断检测"""

    def test_no_warnings_when_files_small(self, tmp_path, monkeypatch):
        """文件足够小时不应有任何警告"""
        # 创建一个小文件，max_chars=1000 远大于实际内容
        (tmp_path / "RUN_COUNT").write_text("10", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("flask", encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [
                ("运行次数", "RUN_COUNT", 1000, False),
                ("依赖约束", "requirements.txt", 1000, False),
            ],
        )
        warnings = check_context_truncation(str(tmp_path))
        assert warnings == []

    def test_warns_when_file_exceeds_limit(self, tmp_path, monkeypatch):
        """文件实际大小超过 max_chars 时应返回警告"""
        (tmp_path / "big.md").write_text("x" * 2000, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("大文件", "big.md", 500, False)],
        )
        warnings = check_context_truncation(str(tmp_path))
        assert len(warnings) == 1
        title, rel_path, max_chars, actual, visible_pct = warnings[0]
        assert title == "大文件"
        assert rel_path == "big.md"
        assert max_chars == 500
        assert actual == 2000
        assert visible_pct == 25.0  # 500/2000 = 25%

    def test_warns_when_file_near_limit(self, tmp_path, monkeypatch):
        """文件接近上限（超过 85% 阈值）时应返回警告"""
        # 900 字符 vs 1000 上限 = 90%，超过 85% 阈值
        (tmp_path / "near.md").write_text("y" * 900, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("接近上限", "near.md", 1000, False)],
        )
        warnings = check_context_truncation(str(tmp_path))
        assert len(warnings) == 1
        _, _, _, actual, visible_pct = warnings[0]
        assert actual == 900
        assert visible_pct == 100.0  # 文件未超限，可见率仍为 100%

    def test_no_warn_below_threshold(self, tmp_path, monkeypatch):
        """文件大小低于阈值（85%）时不应警告"""
        # 800 字符 vs 1000 上限 = 80%，低于 85% 阈值
        (tmp_path / "ok.md").write_text("z" * 800, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("正常文件", "ok.md", 1000, False)],
        )
        warnings = check_context_truncation(str(tmp_path))
        assert warnings == []

    def test_skips_missing_files(self, tmp_path, monkeypatch):
        """文件不存在时不应报错，跳过即可"""
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("不存在", "nonexistent.md", 1000, False)],
        )
        warnings = check_context_truncation(str(tmp_path))
        assert warnings == []

    def test_skips_empty_files(self, tmp_path, monkeypatch):
        """空文件不应产生警告"""
        (tmp_path / "empty.md").write_text("", encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("空文件", "empty.md", 100, False)],
        )
        warnings = check_context_truncation(str(tmp_path))
        assert warnings == []

    def test_multiple_files_mixed(self, tmp_path, monkeypatch):
        """多个文件混合：有的正常、有的超限、有的接近上限"""
        (tmp_path / "small.md").write_text("a" * 100, encoding="utf-8")
        (tmp_path / "big.md").write_text("b" * 5000, encoding="utf-8")
        (tmp_path / "near.md").write_text("c" * 880, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [
                ("小文件", "small.md", 1000, False),
                ("大文件", "big.md", 1000, False),
                ("接近", "near.md", 1000, False),
            ],
        )
        warnings = check_context_truncation(str(tmp_path))
        # big.md 超限 + near.md 超过 85% = 2 个警告
        assert len(warnings) == 2
        warned_files = [w[1] for w in warnings]
        assert "big.md" in warned_files
        assert "near.md" in warned_files
        assert "small.md" not in warned_files

    def test_visible_pct_capped_at_100(self, tmp_path, monkeypatch):
        """接近上限但未超限的文件，可见率应为 100%（不超过 100%）"""
        (tmp_path / "near.md").write_text("x" * 950, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("接近", "near.md", 1000, False)],
        )
        warnings = check_context_truncation(str(tmp_path))
        assert len(warnings) == 1
        _, _, _, _, visible_pct = warnings[0]
        assert visible_pct == 100.0


class TestEmitTruncationWarnings:
    """测试 emit_truncation_warnings 的 stderr 输出"""

    def test_emits_to_stderr_when_exceeded(self, tmp_path, monkeypatch, capsys):
        """超限文件应输出到 stderr"""
        (tmp_path / "big.md").write_text("x" * 2000, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("大文件", "big.md", 500, False)],
        )
        result = emit_truncation_warnings(str(tmp_path))
        captured = capsys.readouterr()
        assert "已超限" in captured.err
        assert "big.md" in captured.err
        assert "大文件" in captured.err
        assert len(result) == 1

    def test_emits_near_limit_warning(self, tmp_path, monkeypatch, capsys):
        """接近上限时输出'接近上限'级别的警告"""
        (tmp_path / "near.md").write_text("y" * 900, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("接近", "near.md", 1000, False)],
        )
        emit_truncation_warnings(str(tmp_path))
        captured = capsys.readouterr()
        assert "接近上限" in captured.err
        assert "余量" in captured.err

    def test_no_output_when_all_ok(self, tmp_path, monkeypatch, capsys):
        """全部正常时不应有任何 stderr 输出"""
        (tmp_path / "ok.md").write_text("z" * 100, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("正常", "ok.md", 1000, False)],
        )
        result = emit_truncation_warnings(str(tmp_path))
        captured = capsys.readouterr()
        assert captured.err == ""
        assert result == []

    def test_returns_same_as_check(self, tmp_path, monkeypatch):
        """返回值应与 check_context_truncation 一致"""
        (tmp_path / "big.md").write_text("x" * 2000, encoding="utf-8")
        monkeypatch.setattr(
            "src.prompt.PROMPT_CONTEXT_FILES",
            [("大文件", "big.md", 500, False)],
        )
        expected = check_context_truncation(str(tmp_path))
        actual = emit_truncation_warnings(str(tmp_path))
        assert actual == expected


class TestTruncationWarnRatio:
    """测试截断警告阈值常量"""

    def test_ratio_is_between_0_and_1(self):
        """阈值应在 0 到 1 之间"""
        assert 0 < _TRUNCATION_WARN_RATIO < 1

    def test_ratio_default_is_085(self):
        """默认阈值应为 0.85"""
        assert _TRUNCATION_WARN_RATIO == 0.85


# === archival memory 注入测试（第 50 次新增） ===

class TestBuildSystemPromptArchival:
    """测试 build_system_prompt 的 archival_context 参数。

    使用 monkeypatch mock 掉 render_prompt_context，避免真实文件内容
    （如 JOURNAL.md 中恰好包含"长期记忆"字样）干扰断言。
    """

    def _mock_render(self, monkeypatch):
        """Mock render_prompt_context 返回固定内容，隔离文件系统依赖。"""
        monkeypatch.setattr(
            "src.prompt.render_prompt_context",
            lambda cwd=None: "### 项目上下文\n(mocked)\n",
        )

    def test_no_archival_section_without_context(self, monkeypatch):
        self._mock_render(monkeypatch)
        prompt = build_system_prompt()
        assert "长期记忆（跨会话）" not in prompt

    def test_archival_section_with_context(self, monkeypatch):
        self._mock_render(monkeypatch)
        ctx = "- Python 3.12 是当前版本\n- pytest 是测试框架"
        prompt = build_system_prompt(archival_context=ctx)
        assert "### 长期记忆（跨会话）" in prompt
        assert "Python 3.12" in prompt
        assert "pytest 是测试框架" in prompt

    def test_empty_archival_context_no_section(self, monkeypatch):
        self._mock_render(monkeypatch)
        prompt = build_system_prompt(archival_context="")
        assert "长期记忆（跨会话）" not in prompt

    def test_none_archival_context_no_section(self, monkeypatch):
        self._mock_render(monkeypatch)
        prompt = build_system_prompt(archival_context=None)
        assert "长期记忆（跨会话）" not in prompt
