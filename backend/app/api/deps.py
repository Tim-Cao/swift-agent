"""FastAPI 依赖注入(供 routes/* 使用)。

约定:
  - 所有依赖函数命名以 get_ 开头,通过 Depends(get_xxx) 复用
  - 异步依赖用 async def + yield(请求结束自动关闭资源)
  - 同步依赖用 def
  - 依赖复用 app.core / app.db / app.supervisor 的现有单例,
    不再各自重复创建
"""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import get_session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖:产出 AsyncSession,请求结束后自动关闭。"""
    factory: async_sessionmaker = get_session_factory()
    async with factory() as session:
        yield session
