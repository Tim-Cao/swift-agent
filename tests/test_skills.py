"""skills/__init__.py 行为测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from skills import load_skills


def test_load_skills_missing_root(tmp_path):
    assert load_skills(tmp_path / "nope") == []


def test_load_skills_parses_frontmatter(tmp_path):
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: demo-skill
description: 测试技能
---
这是指令正文,告诉 Agent 怎么做。
""",
        encoding="utf-8",
    )

    skills = load_skills(tmp_path)
    assert len(skills) == 1
    s = skills[0]
    assert s.name == "demo-skill"
    assert s.description == "测试技能"
    assert "指令正文" in s.instructions


def test_load_skills_no_frontmatter(tmp_path):
    skill_dir = tmp_path / "nofront"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("纯文本指令,无 frontmatter", encoding="utf-8")

    skills = load_skills(tmp_path)
    assert len(skills) == 1
    s = skills[0]
    assert s.name == "nofront"
