"""/api/chat/stream SSE 流式聊天(改用 Depends(get_db) 注入 session)。

v4:媒体类型改为 text/event-stream,事件按 SSE 标准渲染:
  event: <type>
  data: <json>

事件类型与 chat_service.stream_chat 契约保持一致:
  token / tool_call / tool_result / done / error
"""

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


def _format_sse(event: dict[str, Any]) -> str:
    """把 {event, data} dict 渲染为 SSE 标准行。

    输出形如:
        event: token
        data: {"content":"hi"}

    注意:行尾用 \\n,事件之间用空行 \\n\\n 分隔(SSE 规范)。
    """
    evt_type = event.get("event", "message")
    payload = event.get("data", event)
    encoded = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return f"event: {evt_type}\ndata: {encoded}\n\n"


@router.post("/stream")
async def stream_chat_endpoint(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """SSE 流式聊天(text/event-stream)。"""

    async def event_generator():
        session_id, _ = await ensure_session(db, body.session_id, body.agent_name)
        await db.commit()
        try:
            async for event in stream_chat(db, session_id, body.message):
                yield _format_sse(event)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            logger.info("client disconnected, session=%s", session_id)
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("stream failed")
            yield _format_sse({"event": "error", "data": {"message": str(e)}})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx 等反向代理关闭缓冲
        },
    )