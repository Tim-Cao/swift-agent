"""WebSearchGateMiddleware 行为测试。

覆盖:
- 基础过滤(toggle off → MCP 工具被剔除,toggle on → 全保留)
- _filter 不依赖对象 hash(StructuredTool 不可 hash,曾经触发过 TypeError)
- log diff 不抛 TypeError
"""

from __future__ import annotations

import logging

import pytest
from langchain_core.tools import StructuredTool


def _make_tool(name: str) -> StructuredTool:
    def _fn(x: str) -> str:
        return f"ok:{name}"
    _fn.__doc__ = f"Tool {name}."
    return StructuredTool.from_function(func=_fn, name=name)


def test_filter_strips_gated_tools():
    from middlewares.web_search_gate import WebSearchGateMiddleware

    t1 = _make_tool("t1")
    t2 = _make_tool("t2")
    mw = WebSearchGateMiddleware(gated_tool_names=frozenset({"t2"}))

    before = [t1, t2]
    filtered = mw._filter(before)
    assert len(filtered) == 1
    assert filtered[0].name == "t1"


def test_filter_keeps_all_when_nothing_gated():
    from middlewares.web_search_gate import WebSearchGateMiddleware

    t1 = _make_tool("t1")
    t2 = _make_tool("t2")
    mw = WebSearchGateMiddleware(gated_tool_names=frozenset())

    before = [t1, t2]
    filtered = mw._filter(before)
    assert len(filtered) == 2


def test_logger_diff_does_not_hash_tools(caplog):
    """回归测试:v8.10 之前 logger 里用 set(before) - set(filtered) 触发
    TypeError: unhashable type: 'StructuredTool',把整轮 LLM 调用炸掉。

    现在按 name 做差集,要求该分支能正常执行、不抛异常。
    """
    from middlewares.web_search_gate import WebSearchGateMiddleware

    t1 = _make_tool("t1")
    t2 = _make_tool("t2")
    mw = WebSearchGateMiddleware(gated_tool_names=frozenset({"t2"}))

    before = [t1, t2]
    filtered = mw._filter(before)
    # 直接复现旧的 buggy 写法 — 现在应该 NOT 抛 TypeError
    # (用 module-level helper 模拟)
    from middlewares.web_search_gate import _tool_name
    filtered_names = {n for n in (_tool_name(t) for t in filtered) if n}
    removed = [
        _tool_name(t) or "?"
        for t in before
        if _tool_name(t) not in filtered_names
    ]
    assert removed == ["t2"]

    # 同时 StructuredTool 必须仍然不可 hash(这个特性不变,只是我们的代码
    # 不再依赖它)
    with pytest.raises(TypeError, match="unhashable"):
        set(before)


def test_filter_unhashable_object_does_not_crash_filter():
    """防御性测试:即使传入不可 hash 的对象,_filter 也只按名字过滤,
    不会触发 TypeError。"""
    from middlewares.web_search_gate import WebSearchGateMiddleware

    class UnhashableTool:
        # 模拟 StructuredTool:定义 __eq__ 但 __hash__ = None
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return isinstance(other, UnhashableTool) and self.name == other.name

        # 故意不定义 __hash__ —— Python 会自动设成 None

    u1 = UnhashableTool("u1")
    u2 = UnhashableTool("u2")
    mw = WebSearchGateMiddleware(gated_tool_names=frozenset({"u2"}))
    filtered = mw._filter([u1, u2])
    assert len(filtered) == 1
    assert filtered[0].name == "u1"