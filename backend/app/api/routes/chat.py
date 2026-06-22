"""/api/chat/stream NDJSON 流式聊天(改用 Depends(get_db) 注入 session)。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.chat import ChatRequest
from app.services.chat_service import ensure_session, stream_chat

logger = logging.getLogger(__name__)
router = APIRouter()


def _json_default(obj: Any) -> Any:
    """兜底序列化:LangChain Message / Pydantic → dict。"""
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:  # noqa: BLE001
            return str(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


@router.post("/stream")
async def stream_chat_endpoint(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """NDJSON 流式聊天(每行一个 JSON 对象)。"""

    async def line_generator():
        session_id, _ = await ensure_session(db, body.session_id, body.agent_name)
        await db.commit()
        try:
            async for event in stream_chat(db, session_id, body.message):
                yield json.dumps(
                    event, ensure_ascii=False, default=_json_default
                ) + "\n"
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            logger.info("client disconnected, session=%s", session_id)
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("stream failed")
            yield json.dumps(
                {"event": "error", "data": {"message": str(e)}},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        line_generator(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
