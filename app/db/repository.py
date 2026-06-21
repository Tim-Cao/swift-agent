"""仓储层:封装 Session / Message CRUD。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session


# ---------- Session ----------

async def create_session(db: AsyncSession, *, title: str = "新会话", agent_name: str | None = None) -> Session:
    obj = Session(title=title, agent_name=agent_name)
    db.add(obj)
    await db.flush()
    return obj


async def get_session(db: AsyncSession, session_id: str) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def list_sessions(db: AsyncSession, *, limit: int = 100) -> list[Session]:
    result = await db.execute(select(Session).order_by(Session.updated_at.desc()).limit(limit))
    return list(result.scalars())


async def rename_session(db: AsyncSession, session_id: str, title: str) -> Session | None:
    obj = await get_session(db, session_id)
    if obj is None:
        return None
    obj.title = title
    obj.updated_at = datetime.utcnow()
    await db.flush()
    return obj


async def touch_session(db: AsyncSession, session_id: str) -> None:
    obj = await get_session(db, session_id)
    if obj is not None:
        obj.updated_at = datetime.utcnow()
        await db.flush()


async def delete_session(db: AsyncSession, session_id: str) -> bool:
    obj = await get_session(db, session_id)
    if obj is None:
        return False
    await db.delete(obj)
    await db.flush()
    return True


# ---------- Message ----------

async def append_message(
    db: AsyncSession,
    *,
    session_id: str,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> Message:
    import json

    obj = Message(
        session_id=session_id,
        role=role,
        content=content,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
    )
    db.add(obj)
    await db.flush()
    await touch_session(db, session_id)
    return obj


async def list_messages(db: AsyncSession, session_id: str) -> list[Message]:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    return list(result.scalars())


async def count_user_messages(db: AsyncSession, session_id: str) -> int:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id, Message.role == "user")
    )
    return len(list(result.scalars()))
