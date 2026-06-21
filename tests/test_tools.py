"""tools/__init__.py 行为测试。"""

from __future__ import annotations

from tools import TOOLKIT, get_tools, register_tool


class _DummyTool:
    def __init__(self, name: str):
        self.name = name


def setup_function(_):
    TOOLKIT.clear()


def test_register_and_get_tool():
    t = _DummyTool("a")
    register_tool("a", t)
    assert "a" in TOOLKIT
    assert get_tools(["a"]) == [t]
    assert get_tools(["missing"]) == []


def test_register_overrides():
    t1 = _DummyTool("x")
    t2 = _DummyTool("x")
    register_tool("x", t1)
    register_tool("x", t2)
    assert get_tools(["x"]) == [t2]
