"""会话业务逻辑:新建默认名、首条消息重命名。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository as repo

DEFAULT_TITLE = "新会话"
MAX_TITLE_LEN = 30


async def create_default_session(db: AsyncSession, agent_name: str | None = None):
    return await repo.create_session(db, title=DEFAULT_TITLE, agent_name=agent_name)


async def rename_if_first_user_message(
    db: AsyncSession, session_id: str, content: str
) -> None:
    """若是该会话的第一条用户消息,截断前 30 字作为标题。"""
    count = await repo.count_user_messages(db, session_id)
    if count == 0:
        title = content.strip().replace("\n", " ")
        if len(title) > MAX_TITLE_LEN:
            title = title[:MAX_TITLE_LEN]
        if title:
            await repo.rename_session(db, session_id, title)
