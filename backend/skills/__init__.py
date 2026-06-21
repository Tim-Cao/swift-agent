"""技能目录扫描器。

deepagents 的 skills 参数只接受 list[str](目录路径),由 deepagents 内部
SkillsMiddleware(skills.py:748-1066)读取每个路径下的 SKILL.md。
本模块只负责把目录路径收集起来,真正加载由 deepagents 负责。

注意:deepagents 不导出 Skill 类(grep deepagents/__init__.py 找不到),
之前版本里 from deepagents import Skill 是错的。
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_SKILLS_ROOT = "skills"


def load_skills(root: str | Path = DEFAULT_SKILLS_ROOT) -> list[str]:
    """扫描 root/*/(含 SKILL.md 的)子目录,返回路径列表(供 deepagents skills= 使用)。"""
    root_path = Path(root)
    if not root_path.exists():
        return []
    paths: list[str] = []
    for sub in sorted(root_path.iterdir()):
        if sub.is_dir() and (sub / "SKILL.md").exists():
            paths.append(str(sub.resolve()))
    return paths


__all__ = ["load_skills", "DEFAULT_SKILLS_ROOT"]
