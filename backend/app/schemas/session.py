"""会话相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = "新会话"
    agent_name: str | None = None


class SessionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class SessionOut(BaseModel):
    id: str
    title: str
    agent_name: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
