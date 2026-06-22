"""FastAPI 应用入口。"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.logging import setup_logging

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.3.0",
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

    # 路由(单一聚合入口,前缀 /api)
    app.include_router(api_router, prefix="/api")

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
