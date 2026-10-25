"""providers 表加「提供商 ID」(slug)列 + 数据迁移回填。

背景(v11.3):
  老库的 providers 表没有 slug 列。新增列用 ALTER TABLE(不重建表)——
  因为 models.provider_id 对 providers.id 有外键,重建 providers 会把
  那个外键的 REFERENCES 改写到临时表名上。

覆盖:
- 老库(没有 slug 列)跑完迁移 → 有列了,存量行回填了 slug
- 幂等:再跑一次,slug 不变
- 新建唯一索引
"""

from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.fixture
async def legacy_db(tmp_path):
    """造一个"老库":providers 表没有 slug 列。"""
    from app.db.base import get_engine

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS providers"))
        await conn.execute(
            text(
                """
                CREATE TABLE providers (
                    id VARCHAR(32) NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    base_url VARCHAR(512) NOT NULL,
                    api_key TEXT NOT NULL DEFAULT '',
                    default_model_id VARCHAR(64),
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
                INSERT INTO providers (id, name, base_url, api_key, enabled)
                VALUES ('p1', 'MiniMax', 'https://api.minimaxi.com/v1', 'sk-x', 1)
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO providers (id, name, base_url, api_key, enabled)
                VALUES ('p2', 'minimax', 'https://other.com/v1', 'sk-y', 1)
                """
            )
        )
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS providers"))


@pytest.mark.asyncio
async def test_migration_adds_slug_and_backfills(legacy_db):
    """迁移后:有 slug 列,存量行回填了 slug,重名的自动加后缀。"""
    from app.db.migrations import run_additive_migrations

    await run_additive_migrations(legacy_db)

    async with legacy_db.begin() as conn:
        cols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(providers)")))}
        assert "slug" in cols, cols

        rows = list(
            await conn.execute(text("SELECT name, slug FROM providers ORDER BY name"))
        )
    slugs = {r[0]: r[1] for r in rows}
    assert slugs["MiniMax"] == "minimax"
    # 第二个也叫 minimax(大小写不同)→ 撞了加后缀
    assert slugs["minimax"] == "minimax-2", slugs
    assert len(set(slugs.values())) == 2, "slug 不能重复"


@pytest.mark.asyncio
async def test_migration_is_idempotent(legacy_db):
    """再跑一次,slug 不变(不覆盖用户改过的值)。"""
    from app.db.migrations import run_additive_migrations

    await run_additive_migrations(legacy_db)

    async with legacy_db.begin() as conn:
        await conn.execute(
            text("UPDATE providers SET slug = 'custom-id' WHERE id = 'p1'")
        )

    await run_additive_migrations(legacy_db)

    async with legacy_db.begin() as conn:
        row = (
            await conn.execute(text("SELECT slug FROM providers WHERE id = 'p1'"))
        ).first()
    assert row[0] == "custom-id", "已回填过的行不该被二次迁移覆盖"


@pytest.mark.asyncio
async def test_migration_creates_unique_index(legacy_db):
    """slug 上要有唯一索引(否则能存两条同 ID 的记录)。"""
    from app.db.migrations import run_additive_migrations

    await run_additive_migrations(legacy_db)

    async with legacy_db.begin() as conn:
        idx = await conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='ix_providers_slug'"
            )
        )
    assert idx.first() is not None, "缺唯一索引 ix_providers_slug"
