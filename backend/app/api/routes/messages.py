"""/api/sessions/{id}/messages 历史消息(改用 Depends(get_db) 注入 session)。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db import repository as repo
from app.schemas.message import MessageOut

router = APIRouter()


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> list[MessageOut]:
    session = await repo.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    msgs = await repo.list_messages(db, session_id)
    out: list[MessageOut] = []
    for m in msgs:
        meta = None
        if m.meta_json:
            try:
                meta = json.loads(m.meta_json)
            except json.JSONDecodeError:
                meta = None
        out.append(
            MessageOut(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                meta=meta,
                created_at=m.created_at,
            )
        )
    return out
