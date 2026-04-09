"""tests/test_skills.py — SkillSet 加载与渲染测试"""

import os
from src.skills import Skill, SkillSet


class TestSkill:
    def test_basic_creation(self):
        s = Skill(name="test", description="A test skill", path="/tmp/test")
        assert s.name == "test"
        assert s.description == "A test skill"
        assert s.content == ""


class TestSkillSet:
    def test_empty_by_default(self):
        ss = SkillSet()
        assert ss.is_empty() is True
        assert len(ss) == 0

    def test_load_from_directory(self, tmp_path):
        # 创建技能目录结构: tmp_path/skills/my-skill/SKILL.md
        skill_dir = tmp_path / "skills"
        my_skill = skill_dir / "my-skill"
        my_skill.mkdir(parents=True)
        (my_skill / "SKILL.md").write_text(
            "description: 测试技能\n\n这是一个测试技能。", encoding="utf-8"
        )

        ss = SkillSet()
        ss.load([str(skill_dir)])
        assert ss.is_empty() is False
        assert len(ss) == 1
        assert ss.skills[0].name == "my-skill"
        assert ss.skills[0].description == "测试技能"

    def test_load_no_description_line(self, tmp_path):
        """没有 description: 行时，使用内容前 120 字符"""
        skill_dir = tmp_path / "skills"
        my_skill = skill_dir / "plain"
        my_skill.mkdir(parents=True)
        (my_skill / "SKILL.md").write_text("# 纯文本技能\n这里没有 description 行。", encoding="utf-8")

        ss = SkillSet()
        ss.load([str(skill_dir)])
        assert len(ss) == 1
        # description 应为内容前缀
        assert "纯文本技能" in ss.skills[0].description

    def test_load_ignores_non_directories(self, tmp_path):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "not_a_dir.txt").write_text("hello")

        ss = SkillSet()
        ss.load([str(skill_dir)])
        assert ss.is_empty() is True

    def test_load_ignores_missing_skill_file(self, tmp_path):
        skill_dir = tmp_path / "skills"
        (skill_dir / "no-skill-md").mkdir(parents=True)

        ss = SkillSet()
        ss.load([str(skill_dir)])
        assert ss.is_empty() is True

    def test_load_nonexistent_dir(self):
        ss = SkillSet()
        ss.load(["/nonexistent/dir/xyz"])
        assert ss.is_empty() is True

    def test_load_multiple_skills(self, tmp_path):
        skill_dir = tmp_path / "skills"
        for name in ["alpha", "beta", "gamma"]:
            d = skill_dir / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"description: {name} skill", encoding="utf-8")

        ss = SkillSet()
        ss.load([str(skill_dir)])
        assert len(ss) == 3

    def test_to_prompt_text_empty(self):
        ss = SkillSet()
        text = ss.to_prompt_text()
        assert "无已加载技能" in text

    def test_to_prompt_text_with_skills(self, tmp_path):
        skill_dir = tmp_path / "skills"
        d = skill_dir / "demo"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("description: demo skill\n\n# Demo\n内容", encoding="utf-8")

        ss = SkillSet()
        ss.load([str(skill_dir)])
        text = ss.to_prompt_text()
        assert "demo" in text
        assert "demo skill" in text
        assert "无已加载技能" not in text
