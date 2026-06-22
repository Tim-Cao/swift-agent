"""API routes aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import chat, downloads, health, messages, sessions, uploads

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(messages.router, prefix="/sessions", tags=["messages"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
api_router.include_router(downloads.router, prefix="/downloads", tags=["downloads"])

__all__ = ["api_router"]
