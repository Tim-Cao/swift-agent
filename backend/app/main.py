"""FastAPI 应用入口。"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.logging import setup_logging

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    from app.api import chat, health, messages, sessions

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(messages.router, prefix="/api/sessions", tags=["messages"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])

    @app.on_event("startup")
    async def _warmup_supervisor() -> None:
        try:
            from app.supervisor.builder import get_supervisor

            get_supervisor()
            logger.info("Supervisor ready")
        except Exception as e:  # noqa: BLE001
            logger.warning("Supervisor warmup skipped: %s", e)

    return app


app = create_app()
