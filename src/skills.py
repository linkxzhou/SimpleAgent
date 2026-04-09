"""技能系统 - 加载和管理 SKILL.md 技能文件。"""

import os
from typing import List
from dataclasses import dataclass


@dataclass
class Skill:
    name: str
    description: str
    path: str
    content: str = ""


class SkillSet:
    def __init__(self):
        self.skills: List[Skill] = []
    
    def load(self, skill_dirs: List[str]) -> 'SkillSet':
        for skill_dir in skill_dirs:
            if not os.path.isdir(skill_dir):
                continue
            for item in os.listdir(skill_dir):
                skill_path = os.path.join(skill_dir, item)
                if not os.path.isdir(skill_path):
                    continue
                skill_file = os.path.join(skill_path, "SKILL.md")
                if not os.path.isfile(skill_file):
                    continue
                with open(skill_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                description = ""
                for line in content.splitlines():
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
                        break
                if not description:
                    description = content[:120] + "..." if len(content) > 120 else content
                self.skills.append(Skill(item, description, skill_path, content))
        return self
    
    def is_empty(self) -> bool:
        return len(self.skills) == 0
    
    def __len__(self) -> int:
        return len(self.skills)

    def to_prompt_text(self) -> str:
        if self.is_empty():
            return "### 已加载技能\n(无已加载技能)"

        blocks = ["### 已加载技能"]
        for skill in self.skills:
            content = skill.content.strip()
            blocks.append(
                f"#### {skill.name}\n路径：{skill.path}\n说明：{skill.description}\n\n{content}"
            )
        return "\n\n".join(blocks)
