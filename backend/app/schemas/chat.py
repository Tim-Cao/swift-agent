"""聊天 Pydantic 模型(StreamEvent 已删除,事件直接以 dict 透传 deepagents 原生事件)。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)
    agent_name: str | None = None
