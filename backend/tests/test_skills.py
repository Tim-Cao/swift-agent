"""skills/__init__.py 行为测试(v2: 返回 list[str] 路径列表)。"""

from __future__ import annotations

from skills import load_skills


def test_load_skills_missing_root(tmp_path):
    assert load_skills(tmp_path / "nope") == []


def test_load_skills_returns_paths(tmp_path):
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: demo-skill
description: 测试技能
---
这是指令正文。
""",
        encoding="utf-8",
    )

    paths = load_skills(tmp_path)
    assert len(paths) == 1
    assert paths[0].endswith("demo")
    assert (paths[0] + "/SKILL.md").startswith(paths[0][:1])  # sanity


def test_load_skills_skips_dirs_without_skill_md(tmp_path):
    (tmp_path / "no_skill").mkdir()
    skill_dir = tmp_path / "has_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("正文", encoding="utf-8")

    paths = load_skills(tmp_path)
    assert len(paths) == 1
    assert paths[0].endswith("has_skill")
