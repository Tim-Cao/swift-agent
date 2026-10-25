"""API routes aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    chat,
    downloads,
    health,
    mcp,
    messages,
    models,
    sessions,
    tools,
    uploads,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(messages.router, prefix="/sessions", tags=["messages"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(downloads.router, prefix="/downloads", tags=["downloads"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(models.providers_router, prefix="/providers", tags=["providers"])
api_router.include_router(models.models_router, prefix="/models", tags=["models"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])

__all__ = ["api_router"]
