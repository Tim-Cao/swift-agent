"""会话 CRUD 与重命名测试(异步)。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.services.session_service import (
    create_default_session,
    rename_if_first_user_message,
)


@pytest.fixture
async def db():
    from app.db.base import Base, get_engine, init_db
    from app.db import models  # noqa: F401

    await init_db()
    engine = get_engine()
    factory = engine  # 通过 session_scope 拿 session
    from app.db.session import session_scope

    async with session_scope() as session:
        yield session


@pytest.mark.asyncio
async def test_create_default_session(db: AsyncSession):
    s = await create_default_session(db)
    assert s.title == "新会话"
    assert s.id


@pytest.mark.asyncio
async def test_rename_first_user_message(db: AsyncSession):
    s = await create_default_session(db)
    long_msg = "这是一段非常长的用户消息" * 5
    await repo.append_message(db, session_id=s.id, role="user", content=long_msg)
    await rename_if_first_user_message(db, s.id, long_msg)
    refreshed = await repo.get_session(db, s.id)
    assert refreshed is not None
    assert refreshed.title != "新会话"
    assert len(refreshed.title) <= 30


@pytest.mark.asyncio
async def test_rename_only_first_user_message(db: AsyncSession):
    s = await create_default_session(db)
    await repo.append_message(db, session_id=s.id, role="user", content="第一条")
    await rename_if_first_user_message(db, s.id, "第一条")
    first_title = (await repo.get_session(db, s.id)).title
    await repo.append_message(db, session_id=s.id, role="user", content="第二条")
    await rename_if_first_user_message(db, s.id, "第二条")
    after = (await repo.get_session(db, s.id)).title
    assert after == first_title
