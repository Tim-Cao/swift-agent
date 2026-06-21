"""FastAPI 启动/关闭生命周期。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # 确保 data 目录存在(SQLite 文件)
    db_path = Path("./data")
    if not db_path.exists():
        db_path.mkdir(parents=True, exist_ok=True)

    logger.info("App %s starting (db=%s)", settings.app_name, settings.db.url)
    # 启动时建表(由 db 模块处理)
    from app.db.base import init_db

    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("App %s shutting down", settings.app_name)
