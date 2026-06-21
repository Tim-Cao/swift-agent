"""/api/chat/stream SSE 聊天接口。"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.db.base import get_session_factory
from app.schemas.chat import ChatRequest, StreamEvent
from app.services.chat_service import ensure_session, stream_chat

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stream")
async def stream_chat_endpoint(body: ChatRequest):
    """SSE 流式聊天。"""
    factory = get_session_factory()

    async def event_generator():
        async with factory() as db:
            # 1. 确保 session 存在
            session_id, _ = await ensure_session(db, body.session_id, body.agent_name)
            await db.commit()

            # 2. 流式产出
            try:
                async for event in stream_chat(db, session_id, body.message):
                    payload = event.model_dump(exclude_none=True)
                    yield {"event": payload.get("type", "message"), "data": json.dumps(payload, ensure_ascii=False)}
                    # 让出事件循环,便于客户端接收
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                logger.info("client disconnected, session=%s", session_id)
                raise
            except Exception as e:  # noqa: BLE001
                logger.exception("stream failed")
                err = StreamEvent(type="error", content=str(e)).model_dump(exclude_none=True)
                yield {"event": "error", "data": json.dumps(err, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
