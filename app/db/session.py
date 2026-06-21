"""异步 Session 工厂(供仓储层使用)。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """事务作用域的 Session(自动 commit/rollback)。"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_db() -> AsyncSession:
    """FastAPI 依赖注入用的 Session 工厂。"""
    factory = get_session_factory()
    return factory()
