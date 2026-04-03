"""
测试 models 模块
"""

import os
import tempfile
from src.models import SkillSet


class TestSkillSet:
    """测试 SkillSet 功能"""

    def test_empty_skillset(self):
        """测试空的技能集"""
        skills = SkillSet()
        assert skills.is_empty() is True
        assert len(skills) == 0

    def test_load_skills_from_directory(self):
        """测试从目录加载技能"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个技能目录
            skill_dir = os.path.join(tmpdir, "test_skill")
            os.makedirs(skill_dir)
            
            # 创建 SKILL.md 文件
            skill_file = os.path.join(skill_dir, "SKILL.md")
            with open(skill_file, 'w') as f:
                f.write("# Test Skill\n\nThis is a test skill.")

            skills = SkillSet()
            skills.load([tmpdir])

            assert skills.is_empty() is False
            assert len(skills) == 1

    def test_skill_content(self):
        """测试技能内容"""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "demo")
            os.makedirs(skill_dir)
            
            skill_file = os.path.join(skill_dir, "SKILL.md")
            test_content = "# Demo Skill\nDemo content."
            with open(skill_file, 'w') as f:
                f.write(test_content)

            skills = SkillSet()
            skills.load([tmpdir])

            # 获取技能内容
            content = skills.to_prompt_text()
            assert "Demo Skill" in content
            assert "Demo content" in content

    def test_load_multiple_skills(self):
        """测试加载多个技能"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建第一个技能
            skill1_dir = os.path.join(tmpdir, "skill1")
            os.makedirs(skill1_dir)
            with open(os.path.join(skill1_dir, "SKILL.md"), 'w') as f:
                f.write("# Skill 1")

            # 创建第二个技能
            skill2_dir = os.path.join(tmpdir, "skill2")
            os.makedirs(skill2_dir)
            with open(os.path.join(skill2_dir, "SKILL.md"), 'w') as f:
                f.write("# Skill 2")

            skills = SkillSet()
            skills.load([tmpdir])

            assert len(skills) == 2

    def test_nonexistent_skill_directory(self):
        """测试加载不存在的技能目录"""
        skills = SkillSet()
        # 不应抛出异常
        skills.load(["/nonexistent/path"])
        assert skills.is_empty() is True