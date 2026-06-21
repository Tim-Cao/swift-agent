"""聊天相关 Pydantic 模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)
    agent_name: str | None = None


class StreamEvent(BaseModel):
    type: Literal["token", "tool_call", "tool_result", "done", "error"]
    content: str | None = None
    meta: dict | None = None
