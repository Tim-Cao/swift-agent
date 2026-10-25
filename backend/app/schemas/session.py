"""会话相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = "新会话"
    agent_name: str | None = None
    # v10:绑定一个 DB agent;为空则走默认 supervisor
    agent_id: str | None = None


class SessionUpdate(BaseModel):
    # title 可选:允许只改 agent_id
    title: str | None = Field(None, min_length=1, max_length=255)
    # v10:切换会话使用的 agent
    agent_id: str | None = None


class SessionOut(BaseModel):
    id: str
    title: str
    agent_name: str | None
    agent_id: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
