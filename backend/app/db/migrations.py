"""轻量迁移(加列 + 重建表)。

``Base.metadata.create_all`` 只会建**新表**,不会给已存在的表补列。
v10 给 ``sessions`` 加了 ``agent_id`` 列,老库(开发机上已有的 app.db)
启动后会直接报 ``no such column: sessions.agent_id``。

这里补一个幂等的加列迁移:启动时检查列在不在,不在就 ALTER TABLE 加上。

v11:``agents`` 表结构大改(去掉 description / system_prompt / model_id /
builtin,改成 draft_config / published_config 两个 JSON 字段),光加列不够,
需要**重建表**。重建走「建新表 → 拷数据 → 删旧表 → 改名」,SQLite 支持。
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


# 表 → [(列名, DDL 片段)]
# DDL 片段是 "ADD COLUMN xxx" 后面跟的部分。
_ADDITIVE_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "sessions": [
        ("agent_id", "agent_id VARCHAR(32)"),
    ],
}

# 需要额外建的索引(表名, 索引名, DDL)
_INDEX_MIGRATIONS: list[tuple[str, str, str]] = [
    ("sessions", "ix_sessions_agent_id", "CREATE INDEX ix_sessions_agent_id ON sessions (agent_id)"),
]


async def _table_columns(engine: AsyncEngine, table: str) -> set[str] | None:
    """返回表的列名集合;表不存在返回 None。"""
    async with engine.begin() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        rows = result.fetchall()
    if not rows:
        return None
    return {r[1] for r in rows}


async def _index_exists(engine: AsyncEngine, index_name: str) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": index_name},
        )
    return result.fetchone() is not None


async def _table_exists(engine: AsyncEngine, table: str) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": table},
        )
    return result.fetchone() is not None


# ---------- v11:agents 表重建 ----------

# v11 之前 agents 表的列(旧库里有这些列就说明要重建)
_LEGACY_AGENT_COLUMNS = {
    "description",
    "system_prompt",
    "model_id",
    "builtin",
}

# agents 表的新结构(与 app/db/models.py 的 Agent 对应)
# 注意建的是临时表 agents_new,拷完数据后再 RENAME 成 agents。
_AGENTS_NEW_DDL = """
CREATE TABLE agents_new (
    id VARCHAR(32) NOT NULL,
    name VARCHAR(128) NOT NULL,
    draft_config TEXT NOT NULL,
    published_config TEXT NOT NULL,
    published BOOLEAN NOT NULL,
    parent_id VARCHAR(32),
    is_default BOOLEAN NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES agents (id) ON DELETE CASCADE
)
"""


async def _migrate_agents_table(engine: AsyncEngine) -> None:
    """把旧结构的 agents 表重建为 v11 结构。

    旧列( description / system_prompt / model_id / builtin )在 v11 被移除,
    提示词和工具绑定改存 draft_config / published_config 两个 JSON 字段。
    重建时把旧的 system_prompt 搬进 draft_config / published_config,
    尽量不丢用户数据;description / model_id / builtin 直接丢弃
    (description 已从需求里移除,model_id 改用「默认模型」,builtin 概念取消)。
    """
    if not await _table_exists(engine, "agents"):
        return

    columns = await _table_columns(engine, "agents")
    if columns is None:
        return
    if not (_LEGACY_AGENT_COLUMNS & columns):
        # 已经是新结构(或是全新库)
        return

    logger.info("[migrate] agents 表结构过时,开始重建")

    has_prompt = "system_prompt" in columns
    has_published = "published" in columns

    async with engine.begin() as conn:
        # 关掉外键检查(重建期间的自引用 FK 会报错)
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text("DROP TABLE IF EXISTS agents_new"))
        await conn.execute(text(_AGENTS_NEW_DDL))

        if has_prompt:
            # 旧 system_prompt → 两份 config;旧 published 决定 published 标记
            await conn.execute(
                text(
                    """
                    INSERT INTO agents_new
                        (id, name, draft_config, published_config, published,
                         parent_id, is_default, created_at, updated_at)
                    SELECT
                        id,
                        name,
                        json_object('system_prompt', COALESCE(system_prompt, ''),
                                    'tool_ids', json_array()),
                        json_object('system_prompt', COALESCE(system_prompt, ''),
                                    'tool_ids', json_array()),
                        :published,
                        NULL,
                        0,
                        COALESCE(created_at, CURRENT_TIMESTAMP),
                        COALESCE(updated_at, CURRENT_TIMESTAMP)
                    FROM agents
                    """
                ),
                {"published": 1 if has_published else 0},
            )
        else:
            await conn.execute(
                text(
                    """
                    INSERT INTO agents_new
                        (id, name, draft_config, published_config, published,
                         parent_id, is_default, created_at, updated_at)
                    SELECT
                        id, name,
                        json_object('system_prompt', '', 'tool_ids', json_array()),
                        json_object('system_prompt', '', 'tool_ids', json_array()),
                        :published,
                        NULL, 0,
                        COALESCE(created_at, CURRENT_TIMESTAMP),
                        COALESCE(updated_at, CURRENT_TIMESTAMP)
                    FROM agents
                    """
                ),
                {"published": 1 if has_published else 0},
            )

        await conn.execute(text("DROP TABLE agents"))
        await conn.execute(text("ALTER TABLE agents_new RENAME TO agents"))
        await conn.execute(text("CREATE INDEX ix_agents_parent_id ON agents (parent_id)"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))

    # 把 Excel 流水线的子 agent 重新挂回 supervisor 下面
    # (旧结构没有 parent 概念,父子关系原先是写在 subagents/ 代码里的)
    # 名字两边都兼容:旧库叫 "ExcelPipeline.Supervisor" / "ExcelPipeline.XxxAgent",
    # 新库(v11.2 起)去掉了前缀,叫 "Supervisor" / "XxxAgent"。
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE agents
                SET parent_id = (
                    SELECT id FROM agents
                    WHERE name IN ('Supervisor', 'ExcelPipeline.Supervisor')
                    LIMIT 1
                )
                WHERE name IN (
                    'IntakeAgent', 'RuleParserAgent',
                    'DataProcessingAgent', 'ExcelWriterAgent',
                    'ExcelPipeline.IntakeAgent', 'ExcelPipeline.RuleParserAgent',
                    'ExcelPipeline.DataProcessingAgent', 'ExcelPipeline.ExcelWriterAgent'
                )
                  AND EXISTS (
                    SELECT 1 FROM agents
                    WHERE name IN ('Supervisor', 'ExcelPipeline.Supervisor')
                  )
                """
            )
        )

    logger.info("[migrate] agents 表重建完成")


# v11.2:智能体名字去掉 "ExcelPipeline." 前缀
_AGENT_NAME_RENAMES = {
    "ExcelPipeline.Supervisor": "Supervisor",
    "ExcelPipeline.IntakeAgent": "IntakeAgent",
    "ExcelPipeline.RuleParserAgent": "RuleParserAgent",
    "ExcelPipeline.DataProcessingAgent": "DataProcessingAgent",
    "ExcelPipeline.ExcelWriterAgent": "ExcelWriterAgent",
}


async def _migrate_agent_names(engine: AsyncEngine) -> None:
    """把 agents.name 里的 "ExcelPipeline." 前缀去掉。

    只改 Excel 流水线那 5 条记录;用户自己建的智能体名字不动。
    幂等:已经改过的库再跑一次不会有任何变化。
    """
    if not await _table_exists(engine, "agents"):
        return

    async with engine.begin() as conn:
        for old, new in _AGENT_NAME_RENAMES.items():
            # 目标名已被占用(用户自己建了同名 agent)就跳过,别覆盖
            taken = await conn.execute(
                text("SELECT 1 FROM agents WHERE name = :new LIMIT 1"),
                {"new": new},
            )
            if taken.scalar_one_or_none() is not None:
                continue
            await conn.execute(
                text("UPDATE agents SET name = :new WHERE name = :old"),
                {"old": old, "new": new},
            )
    logger.info("[migrate] 智能体名字已去掉 ExcelPipeline. 前缀")


# v11.3:提供商 ID —— users 自己起的短标识
_PROVIDERS_SLUG_DDL = "slug VARCHAR(64) NOT NULL DEFAULT ''"


async def _migrate_provider_slugs(engine: AsyncEngine) -> None:
    """给 providers 表加「提供商 ID」(slug)列并回填。

    为什么不走「重建表」:models.provider_id 对 providers.id 有外键,
    重建 providers 期间那个外键会被 SQLite 改名逻辑搞坏(REFERENCES 会被改写
    到临时表名)。加列 + 建唯一索引更稳,约束效果一样。

    回填规则:用提供商的 name 规整成 slug(小写 + 短横线);撞了就加 -2 / -3。
    幂等:已经有 slug 的行不动。
    """
    if not await _table_exists(engine, "providers"):
        return

    columns = await _table_columns(engine, "providers")
    if columns is None:
        return

    async with engine.begin() as conn:
        added = False
        if "slug" not in columns:
            await conn.execute(
                text(f"ALTER TABLE providers ADD COLUMN {_PROVIDERS_SLUG_DDL}")
            )
            added = True
            logger.info("[migrate] providers 表新增列 slug")

        rows = await conn.execute(
            text("SELECT id, name, slug FROM providers")
        )
        providers = list(rows)

        from app.core.slugify import slugify

        used: set[str] = set()
        for pid, name, slug in providers:
            if slug:
                used.add(slug)
                continue
            base = slugify(name) or "provider"
            candidate = base
            n = 1
            while candidate in used:
                n += 1
                candidate = f"{base}-{n}"
            used.add(candidate)
            await conn.execute(
                text("UPDATE providers SET slug = :slug WHERE id = :id"),
                {"slug": candidate, "id": pid},
            )
            logger.info("[migrate] provider %s 回填 slug=%s", name, candidate)

    # 唯一索引(老库不能给已有列加 UNIQUE 约束,索引等效)。
    # 新库的列本身带 UNIQUE(create_all 建出来的),不用再建一个。
    if added and not await _index_exists(engine, "ix_providers_slug"):
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE UNIQUE INDEX ix_providers_slug ON providers (slug)")
            )
        logger.info("[migrate] providers 表新增唯一索引 ix_providers_slug")


async def run_additive_migrations(engine: AsyncEngine) -> None:
    """执行幂等的迁移。对已是最新的库是 no-op。"""
    for table, columns in _ADDITIVE_MIGRATIONS.items():
        existing = await _table_columns(engine, table)
        if existing is None:
            # 表还不存在 —— create_all 会建出来,不用管
            continue
        for col_name, col_ddl in columns:
            if col_name in existing:
                continue
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_ddl}"))
            logger.info("[migrate] %s 表新增列 %s", table, col_name)

    for table, index_name, index_ddl in _INDEX_MIGRATIONS:
        existing = await _table_columns(engine, table)
        if existing is None:
            continue
        if await _index_exists(engine, index_name):
            continue
        async with engine.begin() as conn:
            await conn.execute(text(index_ddl))
        logger.info("[migrate] %s 表新增索引 %s", table, index_name)

    # v11:agents 表结构重建(放在加列之后 —— 新库先 create_all 出新表,
    # 迁移检测不到旧列就会跳过)
    await _migrate_agents_table(engine)

    # v11.2:智能体名字去掉 "ExcelPipeline." 前缀
    await _migrate_agent_names(engine)

    # v11.3:providers 表加「提供商 ID」(slug)列并回填
    await _migrate_provider_slugs(engine)

    # v11:agent_tools 关联表已废弃(工具绑定改存 config JSON)
    if await _table_exists(engine, "agent_tools"):
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE agent_tools"))
        logger.info("[migrate] 废弃表 agent_tools 已删除")


__all__ = ["run_additive_migrations"]
