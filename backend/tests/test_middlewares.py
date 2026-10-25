"""middlewares/__init__.py 行为测试。

v11:中间件不再用全局可变列表 ``ALL_MIDDLEWARES``(全局状态会污染其它测试),
改成 ``build_middlewares()`` 每次返回一份新实例。
"""

from __future__ import annotations

from middlewares import build_middlewares
from middlewares.web_search_gate import WebSearchGateMiddleware


def test_build_returns_list_with_gate():
    """默认中间件列表里必须有 WebSearchGateMiddleware。"""
    mws = build_middlewares()
    assert isinstance(mws, list)
    assert any(isinstance(m, WebSearchGateMiddleware) for m in mws)


def test_build_returns_fresh_instances():
    """每次调用返回不同的实例 —— 不同 agent 之间不共享状态。"""
    a = build_middlewares()
    b = build_middlewares()
    assert a is not b
    assert a[0] is not b[0]


def test_gate_reads_config_key():
    """WebSearchGateMiddleware 的 config_key 默认是 web_search_enabled。"""
    mw = build_middlewares()[0]
    assert mw._config_key == "web_search_enabled"
