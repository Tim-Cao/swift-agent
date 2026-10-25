"""API routes aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    agents,
    chat,
    downloads,
    health,
    mcp,
    messages,
    models,
    sessions,
    tools,
    trajectory,
    uploads,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(messages.router, prefix="/sessions", tags=["messages"])
# v9:trajectory 路由也挂在 /sessions 下,提供 trajectory + log/export
api_router.include_router(trajectory.router, prefix="/sessions", tags=["trajectory"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(downloads.router, prefix="/downloads", tags=["downloads"])
# v10:元数据管理(智能体 / 工具 / 模型)
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(models.providers_router, prefix="/providers", tags=["providers"])
api_router.include_router(models.models_router, prefix="/models", tags=["models"])
# v11.3:MCP 服务端管理(元数据在 DB 里,页面可增删改)
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])

__all__ = ["api_router"]
