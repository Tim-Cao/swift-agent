"""mcp_servers 表加「工具详情」(tool_details)列。

背景(v11.4):
  原来 tool_names 那一列只存工具名(给计数用)。详情弹窗要显示每个工具的
  描述和入参,装不下,于是另开一列 tool_details 存 JSON,
  不去改 tool_names 的格式(改了会连带打断计数和已有数据)。

覆盖:
- 老库(没有 tool_details 列)跑完迁移 → 有列了
- 存量行的 tool_names 不受影响,新列默认 '[]'
- 幂等:再跑一次,列不重复加
"""

from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture
async def legacy_db():
    """造一个"老库":mcp_servers 表没有 tool_details 列。"""
    from app.db.base import get_engine

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS mcp_servers"))
        await conn.execute(
            text(
                """
                CREATE TABLE mcp_servers (
                    id VARCHAR(32) NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    transport VARCHAR(32) NOT NULL DEFAULT 'stdio',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    tool_names TEXT NOT NULL DEFAULT '[]',
                    status VARCHAR(16) NOT NULL DEFAULT 'unknown',
                    status_detail TEXT NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id)
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO mcp_servers
                    (id, name, transport, config_json, tool_names, status, status_detail, enabled)
                VALUES ('m1', 'legacy-mcp', 'stdio', '{}', '["web_search","ping"]',
                        'connected', '2 个工具', 1)
                """
            )
        )
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS mcp_servers"))


@pytest.mark.asyncio
async def test_migration_adds_tool_details_column(legacy_db):
    """迁移后:多了 tool_details 列,存量行的 tool_names 没被动过。"""
    from app.db.migrations import run_additive_migrations

    await run_additive_migrations(legacy_db)

    async with legacy_db.begin() as conn:
        cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(mcp_servers)")))}
        assert "tool_details" in cols, cols

        row = (
            await conn.execute(
                text("SELECT tool_names, tool_details FROM mcp_servers WHERE id='m1'")
            )
        ).first()

    # 老的名字列表原样保留(前端还在用它数工具)
    assert row[0] == '["web_search","ping"]'
    # 新列默认空列表
    assert row[1] == "[]"


@pytest.mark.asyncio
async def test_migration_is_idempotent(legacy_db):
    """再跑一次不会重复加列(否则第二次会报 "duplicate column name")。"""
    from app.db.migrations import run_additive_migrations

    await run_additive_migrations(legacy_db)
    await run_additive_migrations(legacy_db)

    async with legacy_db.begin() as conn:
        cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(mcp_servers)")))]
    assert cols.count("tool_details") == 1, cols


@pytest.mark.asyncio
async def test_new_column_is_writable(legacy_db):
    """新列能正常写 JSON(不然同步工具接口存不进去)。"""
    from app.db.migrations import run_additive_migrations

    await run_additive_migrations(legacy_db)

    payload = '[{"name":"web_search","description":"搜网页","parameters":{"query":{}}}]'
    async with legacy_db.begin() as conn:
        await conn.execute(
            text("UPDATE mcp_servers SET tool_details = :d WHERE id='m1'"),
            {"d": payload},
        )
    async with legacy_db.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT tool_details FROM mcp_servers WHERE id='m1'")
            )
        ).first()
    assert row[0] == payload
