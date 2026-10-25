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
    from app.db.base import get_session_factory, init_db

    await init_db()
    logger.info("Database initialized")

    # v10:播种内置工具,让「工具管理」页有初始数据
    from app.db.seed import seed_tools

    try:
        factory = get_session_factory()
        async with factory() as db:
            await seed_tools(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("Seed builtin tools failed (continuing): %s", e)
    yield
    logger.info("App %s shutting down", settings.app_name)
