"""中间件管道(空骨架)。

Middleware 协议:async def __call__(ctx, call_next) -> result
"""

from __future__ import annotations

from typing import Any, Awaitable, Protocol

# Middleware 协议(运行时使用 duck typing,这里仅作类型提示)
class Middleware(Protocol):
    """中间件协议。"""

    async def __call__(self, ctx: Any, call_next: Awaitable[Any]) -> Any:  # pragma: no cover
        ...


# 默认空列表,按需增删
ALL_MIDDLEWARES: list[Middleware] = []


__all__ = ["Middleware", "ALL_MIDDLEWARES"]
