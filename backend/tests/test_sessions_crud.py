"""会话 CRUD 与重命名测试(异步)。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo
from app.services.session_service import (
    MAX_TITLE_LEN,
    TITLE_SUFFIX,
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
    # 16 字符前缀 + "…" 后缀,总长 17
    assert refreshed.title.endswith(TITLE_SUFFIX)
    assert refreshed.title.startswith(long_msg[:MAX_TITLE_LEN])
    assert len(refreshed.title) == MAX_TITLE_LEN + len(TITLE_SUFFIX)


@pytest.mark.asyncio
async def test_short_message_no_ellipsis(db: AsyncSession):
    """短消息(<=16 字符)不应加省略号。"""
    s = await create_default_session(db)
    msg = "短消息"
    await repo.append_message(db, session_id=s.id, role="user", content=msg)
    await rename_if_first_user_message(db, s.id, msg)
    refreshed = await repo.get_session(db, s.id)
    assert refreshed is not None
    assert refreshed.title == "短消息"


@pytest.mark.asyncio
async def test_rename_only_first_user_message(db: AsyncSession):
    s = await create_default_session(db)
    await repo.append_message(db, session_id=s.id, role="user", content="第一条")
    await rename_if_first_user_message(db, s.id, "第一条")
    first_title = (await repo.get_session(db, s.id)).title

    # 用户手动 rename 了一次 → 标题不再是 "新会话"
    await repo.rename_session(db, s.id, "用户改的名")
    await repo.append_message(db, session_id=s.id, role="user", content="第二条")
    await rename_if_first_user_message(db, s.id, "第二条")
    after = (await repo.get_session(db, s.id)).title
    # 第二条既不应该走 count==1 分支(因为现在 count==2),
    # 也不应该覆盖用户改过的标题
    assert after == "用户改的名"


@pytest.mark.asyncio
async def test_second_message_does_not_rename(db: AsyncSession):
    """新会话第 2 条 user message 时,count==2,不应再 rename。"""
    s = await create_default_session(db)
    await repo.append_message(db, session_id=s.id, role="user", content="第一条")
    await rename_if_first_user_message(db, s.id, "第一条")
    title_after_first = (await repo.get_session(db, s.id)).title

    # 第二条(标题仍是"第一条",不是默认的"新会话")
    await repo.append_message(db, session_id=s.id, role="user", content="第二条")
    await rename_if_first_user_message(db, s.id, "第二条")
    title_after_second = (await repo.get_session(db, s.id)).title
    assert title_after_second == title_after_first


@pytest.mark.asyncio
async def test_blank_message_does_not_rename(db: AsyncSession):
    """消息全空白时,不应把标题改成空白。"""
    s = await create_default_session(db)
    await repo.append_message(db, session_id=s.id, role="user", content="   \n\n  ")
    await rename_if_first_user_message(db, s.id, "   \n\n  ")
    refreshed = await repo.get_session(db, s.id)
    assert refreshed is not None
    assert refreshed.title == "新会话"