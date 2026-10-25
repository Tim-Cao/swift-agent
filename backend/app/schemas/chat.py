"""聊天 Pydantic 模型(StreamEvent 已删除,事件直接以 dict 透传 deepagents 原生事件)。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)
    agent_name: str | None = None
    upload_dir: str | None = None  # 上传后携带,让 Supervisor 知道文件路径
    enable_web_search: bool = False  # 联网搜索开关;由 WebSearchGateMiddleware 按需过滤 MCP 工具
