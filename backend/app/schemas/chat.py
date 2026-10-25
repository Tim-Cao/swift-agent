"""聊天 Pydantic 模型(StreamEvent 已删除,事件直接以 dict 透传 deepagents 原生事件)。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)
    agent_name: str | None = None
    upload_dir: str | None = None  # 上传后携带,让 Supervisor 知道文件路径
    enable_web_search: bool = False  # 联网搜索开关;由 WebSearchGateMiddleware 按需过滤 MCP 工具
    # 用户本轮上传的文件描述:{ name, size_bytes, csv_count? }
    # 落进 user 消息的 meta.attachments,前端把它渲染成气泡里的文件卡
    attachment: dict[str, Any] | None = None
    # 客户端调用信息:{ kind, rpcId, clientTimeZone }
    # 落进 user 消息的 meta.source 和 session log 的 user_message 事件,
    # 轨迹视图的「来源」标签页直接展示它。
    source: dict[str, Any] | None = None
