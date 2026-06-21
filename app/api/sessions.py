"""/api/sessions 会话 CRUD。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.base import get_session_factory
from app.db import repository as repo
from app.schemas.session import SessionCreate, SessionOut, SessionUpdate

router = APIRouter()


@router.get("", response_model=list[SessionOut])
async def list_sessions() -> list[SessionOut]:
    factory = get_session_factory()
    async with factory() as db:
        objs = await repo.list_sessions(db)
        return [SessionOut.model_validate(o) for o in objs]


@router.post("", response_model=SessionOut)
async def create_session(body: SessionCreate) -> SessionOut:
    factory = get_session_factory()
    async with factory() as db:
        obj = await repo.create_session(db, title=body.title, agent_name=body.agent_name)
        await db.commit()
        await db.refresh(obj)
        return SessionOut.model_validate(obj)


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(session_id: str, body: SessionUpdate) -> SessionOut:
    factory = get_session_factory()
    async with factory() as db:
        obj = await repo.rename_session(db, session_id, body.title)
        if obj is None:
            raise HTTPException(status_code=404, detail="session not found")
        await db.commit()
        await db.refresh(obj)
        return SessionOut.model_validate(obj)


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict:
    factory = get_session_factory()
    async with factory() as db:
        ok = await repo.delete_session(db, session_id)
        if not ok:
            raise HTTPException(status_code=404, detail="session not found")
        await db.commit()
    return {"ok": True}
