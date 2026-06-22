"""API routes aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import chat, health, messages, sessions

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(messages.router, prefix="/sessions", tags=["messages"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

__all__ = ["api_router"]
