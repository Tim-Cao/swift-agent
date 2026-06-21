"""middlewares/__init__.py 行为测试。"""

from __future__ import annotations

from middlewares import ALL_MIDDLEWARES


def test_default_empty():
    assert ALL_MIDDLEWARES == []


def test_append_works():
    class _M:
        async def __call__(self, ctx, call_next):
            return await call_next()

    ALL_MIDDLEWARES.append(_M())
    assert len(ALL_MIDDLEWARES) == 1
    ALL_MIDDLEWARES.clear()
