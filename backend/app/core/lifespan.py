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
    # 确保 data 目录存在(SQLite 文件 + session log 父目录)
    db_path = Path("./data")
    if not db_path.exists():
        db_path.mkdir(parents=True, exist_ok=True)
    # v9:session log 子目录(每个 session 一个子目录,session.jsonl 在里面)
    if settings.trajectory_log_enabled:
        log_root = Path(settings.trajectory_log_dir)
        if not log_root.exists():
            log_root.mkdir(parents=True, exist_ok=True)

    logger.info("App %s starting (db=%s)", settings.app_name, settings.db.url)
    # 启动时建表(由 db 模块处理)
    from app.db.base import get_engine, init_db

    await init_db()
    logger.info("Database initialized")

    # v10:create_all 只建新表,老库缺列要单独补(幂等)
    from app.db.migrations import run_additive_migrations

    try:
        await run_additive_migrations(get_engine())
    except Exception as e:  # noqa: BLE001
        logger.warning("Additive migrations failed (continuing): %s", e)

    # v10:播种内置元数据(工具 / agent),让「工具管理」「智能体管理」页有初始数据
    from app.db.base import get_session_factory
    from app.db.seed import seed_all

    try:
        factory = get_session_factory()
        async with factory() as db:
            await seed_all(db)
    except Exception as e:  # noqa: BLE001
        logger.warning("Seed builtin metadata failed (continuing): %s", e)

    # 启动 MCP 客户端(必须在 supervisor 第一次构建之前完成)
    from app.core.mcp import init_mcp, shutdown_mcp

    try:
        await init_mcp()
    except Exception as e:  # noqa: BLE001
        # MCP 启动失败不应阻塞 backend 启动;supervisor 会因缺工具而 warn
        logger.warning("MCP init failed (continuing without MCP): %s", e)

    yield

    # 关闭 MCP 客户端
    await shutdown_mcp()
    logger.info("App %s shutting down", settings.app_name)
