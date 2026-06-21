"""技能目录扫描器(空骨架)。

扫描根目录下 */SKILL.md,解析首段 YAML frontmatter,正文作为指令。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from deepagents import Skill

# 默认扫描根
DEFAULT_SKILLS_ROOT = "skills"


def _parse_skill_md(text: str) -> tuple[dict[str, Any], str]:
    """解析 SKILL.md,返回 (frontmatter dict, 正文)。"""
    text = text.lstrip()
    if not text.startswith("---"):
        return {}, text
    # 找到第二个 --- 结束标记
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    front = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, Any] = {}
    if front:
        try:
            meta = yaml.safe_load(front) or {}
        except yaml.YAMLError:
            meta = {}
    return meta, body


def _build_skill(meta: dict[str, Any], body: str) -> Any:
    """把 (frontmatter, body) 转成 deepagents.Skill。"""
    try:
        from deepagents import Skill  # type: ignore
    except ImportError:
        # deepagents 未安装时,用一个简单的 dataclass 替代,保证可运行
        from dataclasses import dataclass

        @dataclass
        class _FallbackSkill:
            name: str
            description: str
            instructions: str

        return _FallbackSkill(
            name=meta.get("name", "unnamed"),
            description=meta.get("description", ""),
            instructions=body,
        )

    name = meta.get("name", "unnamed")
    description = meta.get("description", "")
    # deepagents.Skill 字段名以 installed 版本为准
    try:
        return Skill(name=name, description=description, instructions=body)  # type: ignore[arg-type]
    except TypeError:
        return Skill(name=name, description=description, instruction=body)  # type: ignore[call-arg]


def load_skills(root: str | Path = DEFAULT_SKILLS_ROOT) -> list[Any]:
    """扫描 root/*/SKILL.md,返回 Skill 列表。"""
    root_path = Path(root)
    if not root_path.exists():
        return []
    skills: list[Any] = []
    for skill_md in sorted(root_path.glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = _parse_skill_md(text)
        if not meta:
            meta = {"name": skill_md.parent.name, "description": ""}
        skills.append(_build_skill(meta, body))
    return skills


__all__ = ["load_skills", "DEFAULT_SKILLS_ROOT"]
