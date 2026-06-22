"""/api/sessions 会话 CRUD(改用 Depends(get_db) 注入 session)。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db import repository as repo
from app.schemas.session import SessionCreate, SessionOut, SessionUpdate

router = APIRouter()


@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionOut]:
    objs = await repo.list_sessions(db)
    return [SessionOut.model_validate(o) for o in objs]


@router.post("", response_model=SessionOut)
async def create_session(
    body: SessionCreate, db: AsyncSession = Depends(get_db)
) -> SessionOut:
    obj = await repo.create_session(db, title=body.title, agent_name=body.agent_name)
    await db.commit()
    await db.refresh(obj)
    return SessionOut.model_validate(obj)


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(
    session_id: str,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    obj = await repo.rename_session(db, session_id, body.title)
    if obj is None:
        raise HTTPException(status_code=404, detail="session not found")
    await db.commit()
    await db.refresh(obj)
    return SessionOut.model_validate(obj)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    ok = await repo.delete_session(db, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    await db.commit()
    return {"ok": True}
