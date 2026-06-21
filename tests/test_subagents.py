"""subagents/__init__.py 行为测试。"""

from __future__ import annotations

from subagents import ALL_SUBAGENTS


def test_default_empty():
    assert ALL_SUBAGENTS == []


def test_append_works():
    agent = {"name": "T", "description": "d", "system_prompt": "s"}
    ALL_SUBAGENTS.append(agent)
    assert ALL_SUBAGENTS[-1] is agent
    ALL_SUBAGENTS.clear()
