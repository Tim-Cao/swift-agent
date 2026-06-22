"""v7:Excel pipeline 4 个 SKILL.md 加载测试。

v7 把 4 个 skill 的 SKILL.md 写完后,load_skills 应当能扫出 4 个目录。
为了不依赖真实 skills/ 目录是否存在,本测试用 tmp_path 自建目录。
"""

from __future__ import annotations

from pathlib import Path

from skills import load_skills


EXPECTED_NAMES = {"intake", "rule-parser", "data-processing", "excel-writer"}


def _make_skill(root, name, body="指令正文"):
    d = root / name
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: 测试技能 {name}\n---\n{body}\n",
        encoding="utf-8",
    )


def test_load_skills_returns_four(tmp_path):
    for n in EXPECTED_NAMES:
        _make_skill(tmp_path, n)
    paths = load_skills(tmp_path)
    names = {Path(p).name for p in paths}
    assert names == EXPECTED_NAMES


def test_each_skill_md_has_frontmatter(tmp_path):
    for n in EXPECTED_NAMES:
        _make_skill(tmp_path, n, body=f"{n} skill body")
    paths = load_skills(tmp_path)
    for p in paths:
        content = (Path(p) / "SKILL.md").read_text(encoding="utf-8")
        assert content.startswith("---"), f"{p} missing YAML frontmatter"
        assert "description:" in content


def test_load_skills_skips_dirs_without_md(tmp_path):
    _make_skill(tmp_path, "intake")
    (tmp_path / "no_md").mkdir()
    paths = load_skills(tmp_path)
    names = {Path(p).name for p in paths}
    assert names == {"intake"}


def test_default_skills_root_returns_zero_or_four():
    """真实 skills/ 目录(若存在)应该正好 4 个或 0 个。"""
    paths = load_skills()
    n = len(paths)
    assert n in (0, 4), f"skills/ 应返回 0(尚未写)或 4(已写),实际 {n}"


def test_paths_are_absolute(tmp_path):
    _make_skill(tmp_path, "intake")
    paths = load_skills(tmp_path)
    for p in paths:
        assert Path(p).is_absolute()