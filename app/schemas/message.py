"""消息相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    meta: dict[str, Any] | None = None
    created_at: datetime

    class Config:
        from_attributes = True
